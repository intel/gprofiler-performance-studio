#
# Copyright (C) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import hashlib
import json
import threading
import time
import uuid
import psycopg2.extras
from collections import defaultdict
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from gprofiler_dev.config import (
    ACTIVE_HOST_HEARTBEAT_MAX_DELTA_HOURS,
    INSTANCE_RUNS_LRU_CACHE_LIMIT,
    PROFILER_PROCESSES_LRU_CACHE_LIMIT,
)
from gprofiler_dev.lru_cache_impl import LRUCache
from gprofiler_dev.postgres import get_postgres_db
from gprofiler_dev.postgres.postgresdb import DBConflict
from gprofiler_dev.postgres.queries import AggregationSQLQueries, SQLQueries
from gprofiler_dev.postgres.schemas import AgentMetadata, CloudProvider, GetServiceResponse
from gprofiler_dev.perf_utils import normalize_perf_event_name

AGENT_RETENTION_HOURS = 24
LAST_SEEN_UPDATES_INTERVAL_MINUTES = 5

METRICS_UPDATES_INTERVAL_MINUTES = 5
SERVICES_LIST_HOURS_INTERVAL = 7 * 24
SERVICES_LIST_HOURS_VISIBLE_INTERVAL = 24 * 30


def generate_token(nbytes) -> str:
    while True:
        token = token_urlsafe(nbytes)
        # Preventing a token generation with a dash prefix.
        # Tokens with such prefixes are not supported by the gProfiler Agent.
        if not token.startswith("-"):
            break
    return token


def round_time(dt, round_to_seconds=60):
    seconds = (dt.replace(tzinfo=None) - dt.min).seconds
    rounding = (seconds + round_to_seconds / 2) // round_to_seconds * round_to_seconds
    return dt + timedelta(0, rounding - seconds, -dt.microsecond)


def get_total_seconds_from_intervals(intervals: List[Tuple[datetime, datetime]]) -> float:
    islands = []
    island_index = 0
    prev_end = None
    for interval in sorted(intervals):
        start, end = interval
        if prev_end is None or start > prev_end:
            islands.append([start, end])
            island_index += 1
        else:
            end = max(islands[island_index - 1][1], end)
            islands[island_index - 1][1] = end
        prev_end = end
    total_diff = timedelta()
    for island in islands:
        start, end = island
        diff = end - start
        total_diff += diff
    return total_diff.total_seconds()


class Singleton(type):
    _instances: dict = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class DBManager(metaclass=Singleton):
    def __init__(self):
        self.machine_types: Dict[Tuple[str, str], int] = {}
        self.machine_types_ids: Dict[int, int] = {}
        self.profiler_versions: Dict[Tuple[int, int, int], int] = {}
        self.profiler_run_environments: Dict[Tuple[str, int, str], int] = {}
        self.machines: Dict[Tuple[int, int, int], int] = {}
        self.oses: Dict[Tuple[str, str, str], int] = {}
        self.kernels: Dict[Tuple[int, str, str, str], int] = {}
        self.libcs: Dict[Tuple[str, str], int] = {}
        self.services: Dict[Tuple[int], str] = {}
        self.services_visibility: Dict[Tuple[int, int], str] = {}
        self.deployments: Dict[Tuple[int, str], int] = {}
        self.instance_runs = LRUCache(INSTANCE_RUNS_LRU_CACHE_LIMIT)
        self.profiler_processes = LRUCache(PROFILER_PROCESSES_LRU_CACHE_LIMIT)

        # Cache for host-pid mappings (temporary solution)
        self.request_host_pid_mappings: Dict[str, Dict[str, List[int]]] = {}

        self.last_seen_updates: Dict[str : time.time] = defaultdict(
            lambda: time.time() - (LAST_SEEN_UPDATES_INTERVAL_MINUTES + 1) * 60
        )

    @property
    def db(self):
        # Resolve per access: this Singleton is process-wide, so caching one
        # connection would re-serialize every thread on its lock. get_postgres_db()
        # hands each thread its own connection when GPROFILER_POSTGRES_CONN_PER_THREAD
        # is set (and the shared instance otherwise).
        return get_postgres_db()

    def get_libc(self, libc_type, libc_version):
        key = (libc_type, libc_version)
        if key not in self.libcs:
            libc_id = self.db.add_or_fetch(SQLQueries.SELECT_LIBC, key, SQLQueries.INSERT_LIBC)
            self.libcs[key] = libc_id
        return self.libcs[key]

    def get_profiler_process_id(
        self,
        instance_run: int,
        profiler_version: int,
        pid: int,
        spawn_local_time: datetime,
        spawn_uptime: int,
        public_ip,
        private_ip,
        hostname,
        service_id,
        profiler_run_environment_id,
        run_arguments: dict,
        extra_cache: bool,
    ) -> int:
        key = (instance_run, profiler_version, pid, spawn_local_time)
        value = (
            instance_run,
            profiler_version,
            pid,
            spawn_local_time,
            spawn_uptime,
            public_ip,
            private_ip,
            hostname,
            service_id,
            profiler_run_environment_id,
            json.dumps(run_arguments),
        )
        is_new_process = False
        cmp_value = None
        if extra_cache:
            cmp_value = self.profiler_processes.get(key)
        if cmp_value is None:
            process_id, is_new_process = self.db.execute(
                SQLQueries.ADD_OR_FETCH_PROFILER_PROCESS, value, has_value=True, one_value=False
            )

            if process_id is None:
                raise DBConflict("ProfilerProcesses", key, value, process_id)
            if process_id < 0:
                process_id *= -1
                self._warn_conflict("ProfilerProcesses", process_id, "db")
            cmp_value = (process_id, *value)
            if extra_cache:
                self.profiler_processes.put(key, cmp_value)

        if not is_new_process:
            if time.time() - self.last_seen_updates[cmp_value[0]] > LAST_SEEN_UPDATES_INTERVAL_MINUTES * 60:
                self.db.execute(SQLQueries.UPDATE_PROFILER_PROCESS_LAST_SEEN_TIME, (cmp_value[0],), has_value=False)

                self.last_seen_updates[cmp_value[0]] = time.time()
        if value != cmp_value[1:]:
            self._warn_conflict("ProfilerProcesses", cmp_value[0], "cache")
        return cmp_value[0]

    def get_profiler_version_id(self, major: int, minor: int, patch: int) -> int:
        key = (major, minor, patch)
        value = (major, minor, patch, major * 1000000 + minor * 1000 + patch)
        if key not in self.profiler_versions:
            self.profiler_versions[key] = self.db.add_or_fetch(
                SQLQueries.SELECT_PROFILER_AGENT_VERSION, key, SQLQueries.INSERT_PROFILER_AGENT_VERSION, value
            )
        return self.profiler_versions[key]

    def get_profiler_run_environment_id(self, python_version, libc_id, run_mode) -> int:
        key = (python_version, libc_id, run_mode)
        if key not in self.profiler_versions:
            self.profiler_run_environments[key] = self.db.add_or_fetch(
                SQLQueries.SELECT_PROFILER_RUN_ENVIRONMENTS, key, SQLQueries.INSERT_PROFILER_RUN_ENVIRONMENTS
            )
        return self.profiler_run_environments[key]

    def register_profiler_process(
        self, agent_metadata: AgentMetadata, instance_run: int, service_id: int, extra_cache: bool
    ) -> int:
        libc_id = self.get_libc(agent_metadata.libc_type, agent_metadata.libc_version)
        major, minor, patch = agent_metadata.agent_version.split(".")
        patch = patch.split("-")[0]  # Remove any suffix, a workaround for test builds that broke the data ingestion
        profiler_version = self.get_profiler_version_id(int(major), int(minor), int(patch))
        profiler_run_environment_id = self.get_profiler_run_environment_id(
            agent_metadata.python_version, libc_id, agent_metadata.run_mode
        )
        pid = agent_metadata.pid
        spawn_local_time = agent_metadata.spawn_time
        spawn_uptime = agent_metadata.spawn_uptime_ms
        return self.get_profiler_process_id(
            instance_run,
            profiler_version,
            pid,
            spawn_local_time,
            spawn_uptime,
            agent_metadata.public_ip,
            agent_metadata.private_ip,
            agent_metadata.hostname,
            service_id,
            profiler_run_environment_id,
            agent_metadata.run_arguments,
            extra_cache,
        )

    def _warn_conflict(self, table: str, db_id: int, origin: str):
        message = f"Ignored DB conflict in {table} for db_id {db_id} (in {origin})"
        self.db.logger.warning(message)

    def get_instance_run_id(
        self,
        instance: int,
        boot_time: datetime,
        machine: int,
        kernel: int,
        metadata: Optional[int],
        extra_cache: bool,
    ) -> int:
        key = (instance, boot_time)
        value = (instance, boot_time, machine, kernel, metadata)
        cmp_value = None
        if extra_cache:
            cmp_value = self.instance_runs.get(key)
        if cmp_value is None:
            db_id, is_new_instance_run = self.db.execute(
                SQLQueries.ADD_OR_FETCH_INSTANCE_RUN, value, has_value=True, one_value=False
            )
            if db_id is None:
                raise DBConflict("InstanceRuns", key, value, db_id)
            if db_id < 0:
                db_id *= -1
                self._warn_conflict("InstanceRuns", db_id, "db")
            cmp_value = (db_id, *value)
            if extra_cache:
                self.instance_runs.put(key, cmp_value)

        # we ignore conflicts in metadata, notify conflicts in kernel and fix conflicts in machine
        if value[:-1] != cmp_value[1:-1]:
            other_db_id, other_instance, other_boot_time, other_machine, other_kernel, other_metadata = cmp_value
            if instance == other_instance and boot_time == other_boot_time and kernel == other_kernel:
                machine_type = self.machine_types_ids.get(machine)
                other_machine_type = self.machine_types_ids.get(other_machine)
                if machine_type != 1 and other_machine_type == 1 and other_metadata is None:
                    if extra_cache:
                        self.instance_runs.put(key, (other_db_id, *value))
                    self.db.execute(
                        SQLQueries.FIX_INSTANCE_RUN_MACHINE, (machine, metadata, other_db_id), has_value=False
                    )
                    return other_db_id
                elif machine_type == 1 and other_machine_type != 1 and metadata is None:
                    # silently ignore conflict since DB data is correct and connected agent's metadata failed to fetch
                    return cmp_value[0]
            self._warn_conflict("InstanceRuns", cmp_value[0], "cache")
        return cmp_value[0]

    def get_instance(self, agent_id: str, identifier: Optional[str]) -> int:
        key = (agent_id, identifier)
        db_id = self.db.execute(SQLQueries.ADD_OR_FETCH_INSTANCE, key)
        if db_id is not None and db_id < 0:  # If a new instance was inserted
            db_id *= -1
        return db_id

    def get_service_by_id(self, service_id: int) -> str:
        key = (service_id,)
        if key not in self.services:
            service = self.db.execute(SQLQueries.SELECT_SERVICE_NAME_BY_ID, key)
            self.services[key] = service
        return self.services[key]

    def get_service_sample_threshold_by_id(self, service_id: int) -> float:
        key = (service_id,)
        rv = self.db.execute(SQLQueries.SELECT_SERVICE_SAMPLE_THRESHOLD_BY_ID, key)
        return 0 if rv is None else rv

    def get_or_create_service(
        self,
        service_name: str,
        service_env_type: Optional[str] = None,
        create: bool = True,
        is_new_indication: bool = True,
    ) -> int:
        key = (service_name,)
        value = (service_name, service_env_type)
        if create:
            db_id = self.db.execute(SQLQueries.ADD_OR_FETCH_SERVICE, value)
            if is_new_indication:
                return db_id
            return abs(db_id)
        return self.db.execute(SQLQueries.SELECT_SERVICE, key)

    def get_service(self, service_name: str) -> int:
        return self.db.execute(SQLQueries.SELECT_SERVICE, (service_name,))

    def get_snapshot(self, snapshot_id: int) -> Optional[List[Dict]]:
        values = {"snapshot_id": snapshot_id}
        return self.db.execute(
            AggregationSQLQueries.GET_SNAPSHOT, values, one_value=False, return_dict=True, fetch_all=True
        )

    def create_snapshot(
        self,
        service_id: int,
        filter_content: Optional[str],
        start_time: datetime,
        end_time: datetime,
        frames: List,
    ) -> Optional[str]:

        values = {
            "service_id": service_id,
            "start_time": start_time,
            "end_time": end_time,
            "filter_content": filter_content,
        }
        snapshot_id = self.db.execute(SQLQueries.INSERT_SNAPSHOT, values)
        frame_query_values = [(snapshot_id, frame.level, frame.start, frame.duration) for frame in frames]
        self.db.execute(SQLQueries.INSERT_FRAME, frame_query_values, execute_values=True)
        return snapshot_id

    def get_deployment(self, cluster_id: int, service_name: str, create: bool = True) -> Optional[int]:
        cluster_service_name = self.get_service_by_id(cluster_id)
        if cluster_service_name is None:
            return
        namespace = None
        deployment_name = service_name
        if create:
            if "_" in service_name:
                deployment_name, namespace = service_name.split("_", 1)
        service_name = f"{cluster_service_name}.{deployment_name}"
        key = (cluster_id, service_name)
        values = (cluster_id, service_name, namespace)

        if create:
            if key not in self.deployments:
                db_id = self.db.execute(SQLQueries.ADD_OR_FETCH_DEPLOYMENT, values)
                self.deployments[key] = abs(db_id)
                return self.deployments[key]
        else:
            if key not in self.deployments:
                self.deployments[key] = self.db.execute(SQLQueries.SELECT_DEPLOYMENT, key)
        return self.deployments[key]

    def get_metadata_id(self, meta: dict) -> Union[None, int]:
        if len(meta) == 0:
            return None

        meta_json = json.dumps(meta)
        hash_meta = hashlib.new("md5", meta_json.encode("utf-8"), usedforsecurity=False).hexdigest()
        key = (meta_json, hash_meta)
        return self.db.add_or_fetch(
            SQLQueries.SELECT_INSTANCE_CLOUD_METADATA, key, SQLQueries.INSERT_INSTANCE_CLOUD_METADATA
        )

    def get_kernel_id(self, os: int, release: str, version: str, hardware_type: Optional[str]) -> int:
        key = (os, release, version, hardware_type if hardware_type is not None else "")
        if key not in self.kernels:
            self.kernels[key] = self.db.add_or_fetch(SQLQueries.SELECT_KERNEL, key, SQLQueries.INSERT_KERNEL)
        return self.kernels[key]

    def get_os_id(self, system_name: str, name: str, release: str) -> int:
        key = (system_name, name if name is not None else "", release if release is not None else "")
        if key not in self.oses:
            self.oses[key] = self.db.add_or_fetch(SQLQueries.SELECT_OS, key, SQLQueries.INSERT_OS)
        return self.oses[key]

    def get_machine_type_id(self, provider: str, name: Optional[str]) -> int:
        key = (provider, name if name is not None else "")
        if key not in self.machine_types:
            self.machine_types[key] = self.db.add_or_fetch(
                SQLQueries.SELECT_MACHINE_TYPE, key, SQLQueries.INSERT_MACHINE_TYPE
            )
        return self.machine_types[key]

    def get_machine_id(self, provider: str, name: Optional[str], processors: int, memory: int) -> int:
        machine_type = self.get_machine_type_id(provider, name)
        key = (machine_type, processors, memory)
        if key not in self.machines:
            db_id = self.db.add_or_fetch(SQLQueries.SELECT_MACHINE, key, SQLQueries.INSERT_MACHINE)
            self.machines[key] = db_id
            self.machine_types_ids[db_id] = machine_type
        return self.machines[key]

    def register_instance_run(self, agent_metadata: AgentMetadata, instance, extra_cache: bool):
        time_since_boot = timedelta(milliseconds=agent_metadata.spawn_uptime_ms)
        time_since_agent_spawn = agent_metadata.current_time - agent_metadata.spawn_time
        boot_time = agent_metadata.current_time - time_since_agent_spawn - time_since_boot
        instance_type = self._get_instance_type(agent_metadata)
        machine = self.get_machine_id(
            agent_metadata.cloud_provider, instance_type, agent_metadata.processors, agent_metadata.memory_capacity_mb
        )
        os = self.get_os_id(agent_metadata.system_name, agent_metadata.os_name, agent_metadata.os_release)
        kernel = self.get_kernel_id(
            os, agent_metadata.kernel_release, agent_metadata.kernel_version, agent_metadata.hardware_type
        )
        metadata = {**(agent_metadata.cloud_info or {})}
        if agent_metadata.big_data:
            metadata["big_data"] = agent_metadata.big_data
        metadata_id = self.get_metadata_id(metadata) if metadata else None
        return self.get_instance_run_id(instance, round_time(boot_time), machine, kernel, metadata_id, extra_cache)

    @staticmethod
    def _get_instance_type(agent_metadata: AgentMetadata) -> str:
        instance_type = agent_metadata.instance_type
        if agent_metadata.cloud_provider == CloudProvider.GCP.value:
            components = instance_type.split("/")
            if len(components) == 4 and components[0] == "projects" and components[2] == "machineTypes":
                instance_type = components[3]

        return instance_type

    def get_service_by_profiler_process_id(self, process_id: int) -> int:
        return self.db.execute(SQLQueries.GET_SERVICE_ID_BY_PROCESS_ID, (process_id,))

    def add_service_data(
        self, service_name: str, agent_metadata: AgentMetadata, extra_cache: bool, service_env_type: str
    ) -> GetServiceResponse:
        service_id = self.get_or_create_service(service_name, service_env_type, is_new_indication=True)

        does_service_exist = service_id > 0
        service_id = abs(service_id)
        cloud_instance_id = agent_metadata.cloud_info.get("instance_id")
        instance_id = self.get_instance(agent_metadata.mac_address, cloud_instance_id)
        instance_run = self.register_instance_run(agent_metadata, instance_id, extra_cache)
        profiler_process_id = self.register_profiler_process(agent_metadata, instance_run, service_id, extra_cache)
        return GetServiceResponse(
            service_id=service_id, profiler_process_id=profiler_process_id, does_service_exist=does_service_exist
        )

    def get_nodes_cores_summary(
        self,
        service_id: int,
        start_time: datetime,
        end_time: datetime,
        ignore_zeros: bool,
        hostname: Optional[str],
    ) -> Dict:
        total_seconds = (end_time - start_time).total_seconds()
        values = {"service_id": service_id, "start_time": start_time, "end_time": end_time}
        if ignore_zeros:
            res = self.db.execute(
                AggregationSQLQueries.PROFILER_PROCESS_TIMERANGES_BY_SERVICE,
                values,
                one_value=False,
                return_dict=True,
                fetch_all=True,
            )
            if not res:
                return res
            intervals = [(elem["first_seen"], elem["last_seen"]) for elem in res]
            total_seconds = get_total_seconds_from_intervals(intervals)

        values["total_seconds"] = total_seconds
        if hostname:
            values["hostname"] = hostname
            return self.db.execute(
                AggregationSQLQueries.NODES_CORES_SUMMARY_BY_HOST,
                values,
                one_value=True,
                return_dict=True,
            )
        return self.db.execute(
            AggregationSQLQueries.NODES_CORES_SUMMARY,
            values,
            one_value=True,
            return_dict=True,
        )

    def get_nodes_and_cores_graph(
        self,
        service_id: int,
        start_time: datetime,
        end_time: datetime,
        interval: str,
        hostname: Optional[str] = None,
    ) -> List[Dict]:

        values = {"service_id": service_id, "start_time": start_time, "end_time": end_time, "interval_gap": interval}
        hostname_condition = ""
        if hostname:
            hostname_condition = "AND profilerProcesses.hostname = %(hostname)s"
            values["hostname"] = hostname
        return self.db.execute(
            AggregationSQLQueries.NODES_CORES_SUMMARY_GRAPH.format(hostname=hostname_condition),
            values,
            one_value=False,
            return_dict=True,
            fetch_all=True,
        )

    def get_agents(self, service_id):
        values = (AGENT_RETENTION_HOURS, service_id)
        return self.db.execute(
            AggregationSQLQueries.PROFILER_AGENTS_BY_SERVICE,
            values,
            has_value=True,
            one_value=False,
            return_dict=True,
            fetch_all=True,
        )

    def get_services_with_data_indication(self):
        values = {"hours_interval": SERVICES_LIST_HOURS_INTERVAL}
        return self.db.execute(
            AggregationSQLQueries.SERVICES_SELECTION_WITH_DATA_INDICATION,
            values,
            has_value=True,
            one_value=False,
            return_dict=True,
            fetch_all=True,
        )

    def update_processes(self, processes: List[int]):
        self.db.execute(
            SQLQueries.UPDATE_PROFILER_PROCESSES_LAST_SEEN_TIME,
            [(v,) for v in processes],
            has_value=False,
            execute_values=True,
        )

    def get_filters(self, service_id: int) -> List[Dict]:
        values = {"service_id": service_id}
        return self.db.execute(
            SQLQueries.GET_FILTERS_BY_SERVICE_ID, values, one_value=False, return_dict=True, fetch_all=True
        )

    def add_filter(self, service_id: int, filter_content: str):
        values = {"service_id": service_id, "filter_content": filter_content}
        return self.db.execute(SQLQueries.INSERT_FILTER, values)

    def update_filter(self, filter_id: int, filter_content: str):
        values = {"filter_id": filter_id, "filter_content": filter_content}
        self.db.execute(SQLQueries.UPDATE_FILTER, values, has_value=False)

    def delete_filter(self, filter_id: int):
        values = {"filter_id": filter_id}
        self.db.execute(SQLQueries.DELETE_FILTER, values, has_value=False)

    def get_profiler_token(self) -> str:
        results = self.db.execute(
            SQLQueries.SELECT_PROFILER_TOKEN,
            return_dict=True,
            fetch_all=True,
        )
        if results:
            return results[0]["token"]

        token = generate_token(32)
        self.db.execute(SQLQueries.INSERT_PROFILER_TOKEN, {"token": token}, has_value=False, one_value=False)
        return token

    def get_profiler_token_id(self, token: str) -> int:
        return self.db.execute(
            SQLQueries.SELECT_PROFILER_TOKEN_ID, {"token": token}, return_dict=False, fetch_all=False, one_value=True
        )

    def get_service_id_by_name(self, service_name: str) -> int:
        return self.db.execute(SQLQueries.SELECT_SERVICE_ID_BY_NAME, (service_name,))

    def update_tokens_last_seen(self, tokens: Set[tuple[int, str, int]]):
        self.db.execute(SQLQueries.UPDATE_PROFILER_TOKENS_LAST_SEEN_TIME, tokens, has_value=False, execute_values=True)

    def get_overview_summary(self) -> Dict:
        values = {
            "retention_hours": AGENT_RETENTION_HOURS,
            "visible_hours": SERVICES_LIST_HOURS_VISIBLE_INTERVAL,
        }
        return self.db.execute(
            AggregationSQLQueries.SERVICES_NODES_CORES_SUMMARY, values, one_value=False, return_dict=True
        )

    def get_services_overview_summary(self) -> List[Dict]:
        values = {"retention_hours": AGENT_RETENTION_HOURS, "visible_hours": SERVICES_LIST_HOURS_VISIBLE_INTERVAL}
        return self.db.execute(
            AggregationSQLQueries.SERVICES_SUMMARY, values, one_value=False, return_dict=True, fetch_all=True
        )

    # Profiling Request Management Methods (Simplified)

    def save_profiling_request(
        self,
        request_id: str,
        request_type: str,
        service_name: str,
        continuous: Optional[bool] = False,
        duration: Optional[int] = 60,
        frequency: Optional[int] = 11,
        profiling_mode: Optional[str] = "cpu",
        target_hostnames: Optional[List[str]] = None,
        pids: Optional[List[int]] = None,
        host_pid_mapping: Optional[Dict[str, List[int]]] = None,
        target_scope: str = "host",
        target_entities: Optional[List[Dict[str, Any]]] = None,
        additional_args: Optional[Dict] = None,
    ) -> bool:
        """Save a profiling request with support for host-to-PID mapping"""
        # Store additional_args WITHOUT host_pid_mapping (keep that separate)
        clean_additional_args = additional_args.copy() if additional_args else {}
        clean_additional_args["target_scope"] = target_scope
        if target_entities:
            clean_additional_args["target_entities"] = target_entities

        # Store host_pid_mapping separately in a dedicated field if we add one,
        # for now, we'll handle it during command creation to avoid polluting additional_args

        query = """
        INSERT INTO ProfilingRequests (
            request_id, request_type, service_name, continuous, duration, frequency, profiling_mode,
            target_hostnames, pids, additional_args
        ) VALUES (
            %(request_id)s::uuid, %(request_type)s, %(service_name)s, %(continuous)s, %(duration)s, %(frequency)s,
            %(profiling_mode)s::ProfilingMode, %(target_hostnames)s, %(pids)s, %(additional_args)s
        )
        """

        values = {
            "request_id": request_id,
            "request_type": request_type,
            "service_name": service_name,
            "continuous": continuous,
            "duration": duration,
            "frequency": frequency,
            "profiling_mode": profiling_mode,
            "target_hostnames": target_hostnames,
            "pids": pids,
            "additional_args": json.dumps(clean_additional_args) if clean_additional_args else None,
        }

        self.db.execute(query, values, has_value=False)

        # Store host_pid_mapping in a separate table or handle it during command creation
        if host_pid_mapping:
            self._store_host_pid_mapping(request_id, host_pid_mapping)

        return True

    def _store_host_pid_mapping(self, request_id: str, host_pid_mapping: Dict[str, List[int]]) -> None:
        """Store host-to-PID mapping separately from additional_args"""
        # Store in memory cache for this session
        self.request_host_pid_mappings[request_id] = host_pid_mapping

    def _get_host_pid_mapping(self, request_id: str) -> Dict[str, List[int]]:
        """Get host-to-PID mapping for a request"""
        return self.request_host_pid_mappings.get(request_id, {})

    def get_pending_profiling_request(
        self, hostname: str, service_name: str, exclude_command_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Get pending profiling request for a specific host/service using pure SQL"""
        query = """
        SELECT
            pr.request_id,
            pr.service_name,
            pr.continuous,
            pr.duration,
            pr.frequency,
            pr.profiling_mode,
            pr.target_hostnames,
            pr.pids,
            pr.additional_args,
            pr.status,
            pr.created_at,
            pr.estimated_completion_time
        FROM ProfilingRequests pr
        WHERE pr.service_name = %(service_name)s
          AND pr.status = 'pending'
          AND (
              pr.target_hostnames IS NULL
              OR %(hostname)s = ANY(pr.target_hostnames)
          )
        """

        values = {"hostname": hostname, "service_name": service_name}

        if exclude_command_id:
            query += " AND pr.request_id != %(exclude_command_id)s::uuid"
            values["exclude_command_id"] = exclude_command_id

        query += " ORDER BY pr.created_at ASC LIMIT 1"

        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result if result else None

    def mark_profiling_request_assigned(self, request_id: str, command_id: str, hostname: str) -> bool:
        """
        Create execution record for the command assignment.
        We don't need to update ProfilingRequests status since:
        1. ProfilingCommands already tracks the actual commands via request_ids array
        2. ProfilingExecutions tracks the actual execution status
        3. We can trace back from command to requests via request_ids
        """

        # Just create the execution record - this is what really matters
        exec_query = """
        INSERT INTO ProfilingExecutions (
            command_id, hostname, profiling_request_id, status, started_at
        ) VALUES (
            %(command_id)s::uuid, %(hostname)s, %(request_id)s::uuid, 'assigned', CURRENT_TIMESTAMP
        )
        ON CONFLICT (command_id, hostname) DO UPDATE SET
            profiling_request_id = %(request_id)s::uuid,
            status = 'assigned',
            started_at = CURRENT_TIMESTAMP
        """
        exec_values = {"command_id": command_id, "hostname": hostname, "request_id": request_id}

        try:
            self.db.execute(exec_query, exec_values, has_value=False)
            return True
        except Exception as e:
            self.db.logger.error(f"Error creating profiling execution record: {e}")
            return False

    def update_profiling_request_status(
        self, request_id: str, status: str, completed_at: Optional[datetime] = None, error_message: Optional[str] = None
    ) -> bool:
        """
        Update the status of a profiling request (DEPRECATED - kept for compatibility)

        NOTE: This method is largely unnecessary since:
        - ProfilingCommands tracks the actual command status
        - ProfilingExecutions tracks execution status
        - Request status can be inferred from command/execution status

        Consider using command/execution status instead.
        """
        # For now, just return True to avoid breaking existing code
        # In the future, this method should be removed
        return True

    def auto_update_profiling_request_status_by_request_ids(
        self,
        request_ids: List[str],
    ) -> bool:
        """
        Automatically update the status of profiling requests based on the status of their profiling commands.
        This method checks the status of all commands associated with each request ID,
        and updates the request status accordingly.
        The resulting status is determined by the highest "priority" / "criticality" status from the associated commands.
        """
        if not request_ids:
            return True

        exec_query = """
        WITH
            status_priority AS (
                SELECT
                    status,
                    status_value
                FROM (
                    VALUES
                        ('completed', 0),
                        ('pending', 1),
                        ('sent', 2),
                        ('failed', 3)
                ) AS t(status, status_value)
            ),
            profiling_request_with_command_status AS (
                SELECT
                    pr.request_id,
                    pc.status::text AS command_status
                FROM
                    ProfilingRequests pr
                    LEFT JOIN ProfilingCommands pc ON pr.request_id = ANY(pc.request_ids)
                WHERE
                    pr.request_id = ANY(%(request_ids)s::uuid[])
            ),
            max_status AS (
                SELECT
                    pr.request_id,
                    MAX(sp.status_value) AS max_status_value
                FROM
                    profiling_request_with_command_status pr
                    JOIN status_priority sp ON pr.command_status = sp.status
                GROUP BY
                    pr.request_id
            ),
            final_status AS (
                SELECT
                    ms.request_id,
                    sp.status
                FROM
                    max_status ms
                    JOIN status_priority sp ON ms.max_status_value = sp.status_value
            )
        UPDATE ProfilingRequests
        SET status = fs.status::profilingrequeststatus,
            completed_at = CASE
                WHEN fs.status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP
                ELSE pr.completed_at
            END
        FROM
            ProfilingRequests pr
            JOIN final_status fs ON pr.request_id = fs.request_id
        WHERE
            pr.request_id = ANY(%(request_ids)s::uuid[])
        """

        exec_values = {"request_ids": request_ids}

        self.db.execute(exec_query, exec_values, has_value=False)
        return True

    def update_profiling_execution_status(
        self,
        command_id: str,
        hostname: str,
        status: str,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        execution_time: Optional[int] = None,
        results_path: Optional[str] = None,
    ) -> bool:
        """Update the status of a specific profiling execution by command_id and hostname"""
        exec_query = """
        UPDATE ProfilingExecutions
        SET status = %(status)s::ProfilingRequestStatus,
            completed_at = %(completed_at)s,
            error_message = %(error_message)s,
            execution_time = %(execution_time)s,
            results_path = %(results_path)s
        WHERE command_id = %(command_id)s::uuid
        AND hostname = %(hostname)s
        """

        exec_values = {
            "command_id": command_id,
            "hostname": hostname,
            "status": status,
            "completed_at": completed_at,
            "error_message": error_message,
            "execution_time": execution_time,
            "results_path": results_path,
        }

        self.db.execute(exec_query, exec_values, has_value=False)
        return True

    def upsert_host_heartbeat(
        self,
        hostname: str,
        ip_address: str,
        service_name: str,
        agent_version: Optional[str] = None,
        run_mode: Optional[str] = None,
        namespace: Optional[str] = None,
        pod_name: Optional[str] = None,
        containers: Optional[List[Dict[str, Any]]] = None,
        last_command_id: Optional[str] = None,
        received_command_ids: Optional[List[str]] = None,
        executed_command_ids: Optional[List[str]] = None,
        status: str = "active",
        heartbeat_timestamp: Optional[datetime] = None,
        supported_perf_events: Optional[List[str]] = None,
    ) -> bool:
        """
        Update or insert host heartbeat information using pure SQL.
        Always updates on conflict to ensure latest data is stored, including
        hardware changes (e.g., new PMU events after CPU upgrade).
        """
        if heartbeat_timestamp is None:
            heartbeat_timestamp = datetime.now()

        # Container/process inventory lives entirely in the normalized
        # HeartbeatContainers/HeartbeatProcesses tables (synced below). ``RETURNING ID``
        # gives us the stable host row id (the upsert key is (hostname, service_name))
        # used to attach those child rows.
        query = """
        INSERT INTO HostHeartbeats (
            hostname, ip_address, service_name, agent_version, run_mode, namespace, pod_name, last_command_id,
            received_command_ids, executed_command_ids,
            status, heartbeat_timestamp, supported_perf_events, created_at, updated_at
        ) VALUES (
            %(hostname)s, %(ip_address)s::inet, %(service_name)s, %(agent_version)s, %(run_mode)s,
            %(namespace)s, %(pod_name)s,
            %(last_command_id)s::uuid, %(received_command_ids)s::uuid[],
            %(executed_command_ids)s::uuid[],
            %(status)s::HostStatus,
            %(heartbeat_timestamp)s, %(supported_perf_events)s::text[], CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (hostname, service_name)
        DO UPDATE SET
            ip_address = EXCLUDED.ip_address,
            agent_version = EXCLUDED.agent_version,
            run_mode = EXCLUDED.run_mode,
            namespace = EXCLUDED.namespace,
            pod_name = EXCLUDED.pod_name,
            last_command_id = EXCLUDED.last_command_id,
            received_command_ids = EXCLUDED.received_command_ids,
            executed_command_ids = EXCLUDED.executed_command_ids,
            status = EXCLUDED.status,
            heartbeat_timestamp = EXCLUDED.heartbeat_timestamp,
            supported_perf_events = EXCLUDED.supported_perf_events,
            updated_at = CURRENT_TIMESTAMP
        RETURNING ID
        """

        values = {
            "hostname": hostname,
            "ip_address": ip_address,
            "service_name": service_name,
            "agent_version": agent_version,
            "run_mode": run_mode,
            "namespace": namespace,
            "pod_name": pod_name,
            "last_command_id": last_command_id,
            "received_command_ids": received_command_ids,
            "executed_command_ids": executed_command_ids,
            "status": status,
            "heartbeat_timestamp": heartbeat_timestamp,
            "supported_perf_events": supported_perf_events,
        }

        # Host upsert and the normalized inventory sync share one transaction so a
        # reader never observes a host whose structured inventory is half-written.
        with self.db.transaction() as cursor:
            cursor.execute(query, values)
            row = cursor.fetchone()
            host_id = row[0] if row else None
            if host_id is not None:
                self._sync_host_inventory(cursor, host_id, containers or [])
        return True

    def _sync_host_inventory(self, cursor, host_id: int, containers: List[Dict[str, Any]]) -> None:
        """Diff the normalized inventory for a host against the latest heartbeat snapshot.

        Runs inside the caller's transaction. Rather than deleting and re-inserting every
        row on each heartbeat, it upserts containers/processes on their natural identity
        and rewrites a row only when a value actually changed. At fleet scale most beats
        report an unchanged inventory, so the guarded upserts produce zero row writes
        (no dead tuples, WAL, or index churn) in the steady state.

        Only containerized workloads are stored: the agent sends an empty list for
        non-containerized hosts and never emits a usable NULL container_id, so entries
        without a container_id are skipped — they also can't be diffed via the
        UNIQUE (host_id, container_id) key. Any legacy NULL-id rows are cleaned on the
        next heartbeat by the prune below.
        """
        seen_container_ids: Set[str] = set()
        normalized: List[Dict[str, Any]] = []
        for container in containers:
            if not isinstance(container, dict):
                continue
            container_id = container.get("container_id")
            if container_id is None or container_id in seen_container_ids:
                continue
            seen_container_ids.add(container_id)
            normalized.append(container)

        incoming_ids = [c["container_id"] for c in normalized]

        # Drop containers the host no longer reports (cascades to their processes). The
        # IS NULL clause also reclaims any legacy NULL-id rows left by the old writer.
        cursor.execute(
            "DELETE FROM HeartbeatContainers "
            "WHERE host_id = %s AND (container_id IS NULL OR container_id <> ALL(%s::text[]))",
            (host_id, incoming_ids),
        )

        if not normalized:
            return

        # Container tuples, reused by the insert-new and update-changed passes below.
        container_rows = [
            (
                host_id,
                container["container_id"],
                container.get("container_name"),
                container.get("runtime"),
                container.get("namespace"),
                container.get("pod_name"),
                container.get("workload_name"),
                container.get("workload_kind"),
            )
            for container in normalized
        ]

        # Insert only genuinely-new containers. A blanket INSERT ... ON CONFLICT would
        # evaluate the id DEFAULT (nextval) for every proposed row before resolving the
        # conflict, burning a sequence value per unchanged container re-reported each
        # beat. Filtering to non-existing rows means nextval fires only for real inserts;
        # ON CONFLICT DO NOTHING still guards the rare concurrent-insert race.
        psycopg2.extras.execute_values(
            cursor,
            """
            INSERT INTO HeartbeatContainers (
                host_id, container_id, container_name, runtime, namespace,
                pod_name, workload_name, workload_kind, updated_at
            )
            SELECT v.host_id, v.container_id, v.container_name, v.runtime, v.namespace,
                   v.pod_name, v.workload_name, v.workload_kind, CURRENT_TIMESTAMP
            FROM (VALUES %s) AS v(host_id, container_id, container_name, runtime,
                                  namespace, pod_name, workload_name, workload_kind)
            WHERE NOT EXISTS (
                SELECT 1 FROM HeartbeatContainers hc
                WHERE hc.host_id = v.host_id AND hc.container_id = v.container_id
            )
            ON CONFLICT (host_id, container_id) DO NOTHING
            """,
            container_rows,
            template="(%s::bigint, %s::text, %s::text, %s::text, %s::text, %s::text, %s::text, %s::text)",
        )

        # Rewrite metadata only for containers that actually changed.
        psycopg2.extras.execute_values(
            cursor,
            """
            UPDATE HeartbeatContainers hc SET
                container_name = v.container_name,
                runtime        = v.runtime,
                namespace      = v.namespace,
                pod_name       = v.pod_name,
                workload_name  = v.workload_name,
                workload_kind  = v.workload_kind,
                updated_at     = CURRENT_TIMESTAMP
            FROM (VALUES %s) AS v(host_id, container_id, container_name, runtime,
                                  namespace, pod_name, workload_name, workload_kind)
            WHERE hc.host_id = v.host_id AND hc.container_id = v.container_id
              AND (
                hc.container_name, hc.runtime, hc.namespace, hc.pod_name,
                hc.workload_name, hc.workload_kind
              ) IS DISTINCT FROM (
                v.container_name, v.runtime, v.namespace, v.pod_name,
                v.workload_name, v.workload_kind
              )
            """,
            container_rows,
            template="(%s::bigint, %s::text, %s::text, %s::text, %s::text, %s::text, %s::text, %s::text)",
        )

        # Map every reported container_id to its stable row id (changed or not) so
        # processes can be attached — the guarded upsert above returns nothing for
        # unchanged rows, so we can't rely on RETURNING here.
        cursor.execute(
            "SELECT id, container_id FROM HeartbeatContainers "
            "WHERE host_id = %s AND container_id = ANY(%s::text[])",
            (host_id, incoming_ids),
        )
        row_id_by_container_id = {container_id: row_id for row_id, container_id in cursor.fetchall()}

        for container in normalized:
            container_row_id = row_id_by_container_id.get(container["container_id"])
            if container_row_id is None:
                continue
            self._sync_container_processes(cursor, container_row_id, container.get("processes") or [])

    def _sync_container_processes(self, cursor, container_row_id: int, processes: List[Dict[str, Any]]) -> None:
        """Diff a single container's processes, mirroring the container-level upsert."""
        process_rows = []
        seen_pids: Set[int] = set()
        for process in processes:
            if not isinstance(process, dict):
                continue
            pid = process.get("pid")
            if pid is None or not str(pid).isdigit():
                continue
            pid = int(pid)
            if pid in seen_pids:  # satisfy UNIQUE (container_row_id, pid)
                continue
            seen_pids.add(pid)
            process_rows.append((container_row_id, pid, process.get("process_name")))

        # Drop processes the container no longer reports.
        cursor.execute(
            "DELETE FROM HeartbeatProcesses WHERE container_row_id = %s AND pid <> ALL(%s::int[])",
            (container_row_id, [pid for _, pid, _ in process_rows]),
        )

        if not process_rows:
            return

        # Insert only genuinely-new (container_row_id, pid) rows. A blanket
        # INSERT ... ON CONFLICT evaluates the id DEFAULT (nextval) for every proposed
        # row before resolving the conflict, so the ~all-unchanged processes re-reported
        # each beat burned a sequence value each (~58k nextval/s fleet-wide -> sequence
        # buffer lock contention). Filtering to non-existing rows means nextval fires
        # only for real inserts; ON CONFLICT DO NOTHING guards the concurrent-insert race.
        psycopg2.extras.execute_values(
            cursor,
            """
            INSERT INTO HeartbeatProcesses (container_row_id, pid, process_name)
            SELECT v.container_row_id, v.pid, v.process_name
            FROM (VALUES %s) AS v(container_row_id, pid, process_name)
            WHERE NOT EXISTS (
                SELECT 1 FROM HeartbeatProcesses hp
                WHERE hp.container_row_id = v.container_row_id AND hp.pid = v.pid
            )
            ON CONFLICT (container_row_id, pid) DO NOTHING
            """,
            process_rows,
            template="(%s::bigint, %s::int, %s::text)",
        )

        # Rewrite names only for rows whose process_name actually changed.
        psycopg2.extras.execute_values(
            cursor,
            """
            UPDATE HeartbeatProcesses hp SET process_name = v.process_name
            FROM (VALUES %s) AS v(container_row_id, pid, process_name)
            WHERE hp.container_row_id = v.container_row_id AND hp.pid = v.pid
              AND hp.process_name IS DISTINCT FROM v.process_name
            """,
            process_rows,
            template="(%s::bigint, %s::int, %s::text)",
        )

    def get_host_heartbeat(self, hostname: str) -> Optional[Dict]:
        """Get the latest heartbeat information for a host"""
        query = """
        SELECT
            hostname, ip_address, service_name, last_command_id,
            received_command_ids, executed_command_ids,
            status, heartbeat_timestamp, created_at, updated_at
        FROM HostHeartbeats
        WHERE hostname = %(hostname)s
        """

        values = {"hostname": hostname}
        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result if result else None

    def get_active_hosts(self, service_name: Optional[str] = None) -> List[Dict]:
        """Get list of active hosts, optionally filtered by service"""
        query = """
        SELECT
            hostname, ip_address, service_name, last_command_id,
            received_command_ids, executed_command_ids,
            status, heartbeat_timestamp
        FROM HostHeartbeats
        WHERE status = 'active'
          AND heartbeat_timestamp > NOW() - INTERVAL '10 minutes'
        """

        values = {}
        if service_name:
            query += " AND service_name = %(service_name)s"
            values["service_name"] = service_name

        query += " ORDER BY heartbeat_timestamp DESC"

        return self.db.execute(query, values, one_value=False, return_dict=True, fetch_all=True)

    def get_active_hosts_count(self, service_name: Optional[str] = None, max_delta_hours: int = ACTIVE_HOST_HEARTBEAT_MAX_DELTA_HOURS) -> int:
        """
        Get the count of active hosts based on the provided time window.
        A host is considered active if its last heartbeat is within the specified time window.
        
        Args:
            service_name: Optional service name to filter hosts by
            max_delta_hours: Maximum hours since last heartbeat to consider a host active (default: ACTIVE_HOST_HEARTBEAT_MAX_DELTA_HOURS)
            
        Returns:
            int: Count of active hosts
        """
        query = """
        SELECT COUNT(*) as active_hosts_count
        FROM HostHeartbeats
        WHERE heartbeat_timestamp >= NOW() - INTERVAL '%(max_delta_hours)s hours'
        """
        
        values = {"max_delta_hours": max_delta_hours}
        
        if service_name:
            query += " AND service_name = %(service_name)s"
            values["service_name"] = service_name
        
        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result.get("active_hosts_count", 0) if result else 0

    def validate_perf_events_support(
        self, 
        service_name: str, 
        requested_events: List[str],
        target_hostnames: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validate if the requested perf events are supported by target hosts.
        
        Args:
            service_name: Service name to check
            requested_events: List of requested perf events (e.g., ['cpu-cycles', 'cache-misses'])
            target_hostnames: Optional list of specific hostnames to check (None = all hosts for service)
            
        Returns:
            Dict with validation results:
            {
                "valid": bool,
                "unsupported_hosts": List[Dict], # Hosts that don't support some events
                "error_message": Optional[str]
            }
        """
        # Normalize requested events to match agent's format
        normalized_requested_events = [normalize_perf_event_name(event) for event in requested_events]
        
        # Build query to get hosts and their supported events
        query = """
        SELECT 
            hostname, 
            supported_perf_events
        FROM HostHeartbeats
        WHERE service_name = %(service_name)s
          AND heartbeat_timestamp >= NOW() - INTERVAL '2 minutes'
        """
        
        values = {"service_name": service_name}
        
        # Filter by specific hostnames if provided
        if target_hostnames:
            query += " AND hostname = ANY(%(target_hostnames)s)"
            values["target_hostnames"] = target_hostnames
        
        hosts = self.db.execute(query, values, one_value=False, return_dict=True, fetch_all=True)
        
        if not hosts:
            return {
                "valid": False,
                "unsupported_hosts": [],
                "error_message": f"No active hosts found for service '{service_name}'"
            }
        
        unsupported_hosts = []
        
        for host in hosts:
            hostname = host.get("hostname")
            supported_events = host.get("supported_perf_events") or []
            
            # If host hasn't sent supported events yet, assume compatibility issue
            if not supported_events:
                unsupported_hosts.append({
                    "hostname": hostname,
                    "missing_events": requested_events,  # Use original names in error message
                    "reason": "Host has not reported supported PMU events yet"
                })
                continue
            
            # Check which requested events are NOT supported (using normalized names)
            missing_events = []
            for i, normalized_event in enumerate(normalized_requested_events):
                if normalized_event not in supported_events:
                    missing_events.append(requested_events[i])  # Use original name in error message
            
            if missing_events:
                unsupported_hosts.append({
                    "hostname": hostname,
                    "missing_events": missing_events,
                    "supported_events": supported_events
                })
        
        # Build error message if there are unsupported hosts
        if unsupported_hosts:
            total_unsupported = len(unsupported_hosts)
            host_details = []
            
            # Show up to 10 hosts so users know exactly which hosts have issues
            max_hosts_to_show = 10
            for host_info in unsupported_hosts[:max_hosts_to_show]:
                hostname = host_info["hostname"]
                missing = ", ".join(host_info["missing_events"])
                host_details.append(f"  - {hostname}: missing {missing}")
            
            more_hosts = total_unsupported - max_hosts_to_show
            if more_hosts > 0:
                host_details.append(f"  ...and {more_hosts} more host(s)")
            
            # Include summary for better context
            summary = f"{total_unsupported} host(s) don't support the selected events:"
            error_message = summary + "\n" + "\n".join(host_details)
            
            return {
                "valid": False,
                "unsupported_hosts": unsupported_hosts,
                "error_message": error_message
            }
        
        return {
            "valid": True,
            "unsupported_hosts": [],
            "error_message": None
        }

    def get_actively_profiling_hosts_count(self, service_name: Optional[str] = None, host_exclusion_list: Optional[List[str]] = None, host_inclusion_list: Optional[List[str]] = None) -> int:
        """
        Get the count of hosts that are actively profiling.
        A host is considered actively profiling if it has a completed start command.
        
        Args:
            service_name: Optional service name to filter hosts by
            host_exclusion_list: Optional list of hostnames to exclude from the count
            host_inclusion_list: Optional list of hostnames to include in the count (only these hosts will be counted)
            
        Returns:
            int: Count of actively profiling hosts
        """
        query = """
        SELECT COUNT(DISTINCT hostname) as profiling_hosts_count
        FROM ProfilingCommands
        WHERE command_type = 'start'
          AND status = 'completed'
        """
        
        values = {}
        
        if service_name:
            query += " AND service_name = %(service_name)s"
            values["service_name"] = service_name
        
        if host_inclusion_list:
            query += " AND hostname IN %(host_inclusion_list)s"
            values["host_inclusion_list"] = tuple(host_inclusion_list)
        
        if host_exclusion_list:
            query += " AND hostname NOT IN %(host_exclusion_list)s"
            values["host_exclusion_list"] = tuple(host_exclusion_list)
        
        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result.get("profiling_hosts_count", 0) if result else 0

    def get_all_host_heartbeats(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict]:
        """Get all host heartbeat records with optional pagination"""
        query = """
        SELECT
            ID, hostname, ip_address, service_name, last_command_id,
            received_command_ids, executed_command_ids,
            status, heartbeat_timestamp, created_at, updated_at
        FROM HostHeartbeats
        ORDER BY heartbeat_timestamp DESC
        """

        values = {}
        if limit is not None:
            query += " LIMIT %(limit)s"
            values["limit"] = limit
        if offset is not None:
            query += " OFFSET %(offset)s"
            values["offset"] = offset

        return self.db.execute(query, values, one_value=False, return_dict=True, fetch_all=True)

    def get_host_heartbeats_by_service(self, service_name: str, limit: Optional[int] = None, exact_match: bool = False) -> List[Dict]:
        """Get all host heartbeat records for a specific service with optional partial matching"""
        if exact_match:
            # Use exact match for backward compatibility
            where_clause = "WHERE service_name = %(service_name)s"
            service_param = service_name
        else:
            # Use partial, case-insensitive matching
            where_clause = "WHERE service_name ILIKE %(service_name)s"
            service_param = f"%{service_name}%"

        query = f"""
        SELECT
            ID, hostname, ip_address, service_name, last_command_id,
            received_command_ids, executed_command_ids,
            status, heartbeat_timestamp, created_at, updated_at
        FROM HostHeartbeats
        {where_clause}
        ORDER BY heartbeat_timestamp DESC
        """

        values: dict[str, Any] = {"service_name": service_param}
        if limit is not None:
            query += " LIMIT %(limit)s"
            values["limit"] = limit

        return self.db.execute(query, values, one_value=False, return_dict=True, fetch_all=True)

    def get_host_heartbeats_by_status(self, status: str, limit: Optional[int] = None) -> List[Dict]:
        """Get all host heartbeat records by status"""
        query = """
        SELECT
            ID, hostname, ip_address, service_name, last_command_id,
            received_command_ids, executed_command_ids,
            status, heartbeat_timestamp, created_at, updated_at
        FROM HostHeartbeats
        WHERE status = %(status)s
        ORDER BY heartbeat_timestamp DESC
        """

        values: dict[str, Any] = {"status": status}
        if limit is not None:
            query += " LIMIT %(limit)s"
            values["limit"] = limit

        return self.db.execute(query, values, one_value=False, return_dict=True, fetch_all=True)

    def get_profiler_request_status(self, request_id: str) -> Optional[Dict]:
        """Get the current status of a profiling request by looking at associated commands and executions"""
        query = """
        SELECT
            pr.request_id, pr.service_name, pr.created_at, pr.estimated_completion_time,
            pc.command_id, pc.hostname, pc.status as command_status, pc.created_at as command_created_at,
            pe.status as execution_status, pe.started_at, pe.completed_at, pe.error_message
        FROM ProfilingRequests pr
        LEFT JOIN ProfilingCommands pc ON pr.request_id = ANY(pc.request_ids)
        LEFT JOIN ProfilingExecutions pe ON pc.command_id = pe.command_id
        WHERE pr.request_id = %(request_id)s::uuid
        ORDER BY pc.created_at DESC, pe.started_at DESC
        LIMIT 1
        """

        values = {"request_id": request_id}
        result = self.db.execute(query, values, one_value=True, return_dict=True)

        if result:
            # Infer overall request status from command/execution status
            if result.get("execution_status"):
                result["inferred_status"] = result["execution_status"]
            elif result.get("command_status"):
                result["inferred_status"] = result["command_status"]
            else:
                result["inferred_status"] = "pending"

        return result if result else None

    def create_or_update_profiling_command(
        self,
        command_id: str,
        hostname: Optional[str],
        service_name: str,
        command_type: str,
        new_request_id: str,
        stop_level: Optional[str] = None,
    ) -> bool:
        """Create or update a profiling command for a host with command_type support"""
        if hostname is None:
            active_hosts = self.get_active_hosts(service_name)
            success = True
            for host in active_hosts:
                result = self.create_or_update_profiling_command(
                    command_id, host["hostname"], service_name, command_type, new_request_id, stop_level
                )
                success = success and result
            return success

        # Get the request details to build combined_config
        request_query = """
        SELECT continuous, duration, frequency, profiling_mode, pids, additional_args
        FROM ProfilingRequests
        WHERE request_id = %(request_id)s::uuid
        """
        request_result = self.db.execute(
            request_query, {"request_id": new_request_id}, one_value=True, return_dict=True
        )

        if not request_result:
            return False

        # Get host-specific PIDs from our dedicated storage
        host_pid_mapping = self._get_host_pid_mapping(new_request_id)
        host_specific_pids = host_pid_mapping.get(hostname, []) if host_pid_mapping else []

        # Build base configuration from new request
        new_config = {
            "command_type": command_type,
            "continuous": request_result["continuous"],
            "duration": request_result["duration"],
            "frequency": request_result["frequency"],
            "profiling_mode": request_result["profiling_mode"],
        }
        
        # Merge additional_args directly into new_config
        if request_result["additional_args"]:
            additional_args = request_result["additional_args"]
            if isinstance(additional_args, str):
                try:
                    additional_args = json.loads(additional_args)
                except json.JSONDecodeError:
                    additional_args = {}
            if isinstance(additional_args, dict):
                new_config.update(additional_args)

        # Add stop_level if provided
        if stop_level:
            new_config["stop_level"] = stop_level

        # Use host-specific PIDs if available, otherwise fall back to global PIDs
        if host_specific_pids:
            new_config["pids"] = host_specific_pids
        elif request_result["pids"]:
            new_config["pids"] = request_result["pids"]

        # Use proper upsert with ON CONFLICT to handle race conditions
        # First, check if there's an existing command to merge with
        existing_command_query = """
        SELECT command_id, combined_config, request_ids
        FROM ProfilingCommands
        WHERE hostname = %(hostname)s
          AND service_name = %(service_name)s
          AND status = 'pending'
        """

        existing_command = self.db.execute(
            existing_command_query,
            {"hostname": hostname, "service_name": service_name},
            one_value=True,
            return_dict=True,
        )

        # Only merge the command when there is an existing command and
        # the command status is 'pending' or 'sent'
        if existing_command and existing_command.get("status") in ["pending", "sent"]:
            # Merge with existing command
            existing_config = existing_command["combined_config"]
            if isinstance(existing_config, str):
                try:
                    existing_config = json.loads(existing_config)
                except json.JSONDecodeError:
                    existing_config = {}
            elif existing_config is None:
                existing_config = {}

            # Merge configurations
            merged_config = self._merge_profiling_configs(existing_config, new_config)
            final_config = merged_config
            final_request_ids = existing_command["request_ids"] + [new_request_id]
        else:
            # No existing command, use new config as-is
            final_config = new_config
            final_request_ids = [new_request_id]

        # Use INSERT ... ON CONFLICT for atomic upsert
        upsert_query = """
        INSERT INTO ProfilingCommands (
            command_id, hostname, service_name, command_type, request_ids,
            combined_config, status, created_at
        ) VALUES (
            %(command_id)s::uuid, %(hostname)s, %(service_name)s, %(command_type)s,
            %(final_request_ids)s::uuid[], %(final_config)s::jsonb,
            'pending', CURRENT_TIMESTAMP
        )
        ON CONFLICT (hostname, service_name)
        DO UPDATE SET
            command_id = %(command_id)s::uuid,
            command_type = %(command_type)s,
            request_ids = %(final_request_ids)s::uuid[],
            combined_config = %(final_config)s::jsonb,
            status = 'pending',
            created_at = CURRENT_TIMESTAMP
        """

        values = {
            "command_id": command_id,
            "hostname": hostname,
            "service_name": service_name,
            "command_type": command_type,
            "final_request_ids": final_request_ids,
            "final_config": json.dumps(final_config),
        }

        self.db.execute(upsert_query, values, has_value=False)
        return True

    def get_active_service_subscription(self, service_name: str) -> Optional[str]:
        """Return the request_id of the active service-wide profiling subscription
        for a service, or None.

        A service is "actively subscribed" when its most recent service-scoped
        continuous "start" request is newer than any service-scoped "stop" request
        (and was not cancelled). This is what lets hosts that register *after* a
        service-wide profiling request auto-join the in-progress profile.
        """
        start_query = """
        SELECT request_id, created_at
        FROM ProfilingRequests
        WHERE service_name = %(service_name)s
          AND request_type = 'start'
          AND continuous = TRUE
          AND COALESCE(additional_args->>'target_scope', 'host') = 'service'
          AND status != 'cancelled'
        ORDER BY created_at DESC
        LIMIT 1
        """
        start_row = self.db.execute(
            start_query, {"service_name": service_name}, one_value=True, return_dict=True
        )
        if not start_row:
            return None

        stop_query = """
        SELECT created_at
        FROM ProfilingRequests
        WHERE service_name = %(service_name)s
          AND request_type = 'stop'
          AND COALESCE(additional_args->>'target_scope', 'host') = 'service'
        ORDER BY created_at DESC
        LIMIT 1
        """
        stop_row = self.db.execute(
            stop_query, {"service_name": service_name}, one_value=True, return_dict=True
        )
        if stop_row and stop_row["created_at"] >= start_row["created_at"]:
            return None

        return str(start_row["request_id"])

    def auto_subscribe_host_to_service(self, hostname: str, service_name: str) -> bool:
        """Enroll a host into its service's active service-wide profiling.

        Invoked on every heartbeat. When a service has an active service-wide
        profiling subscription and the reporting host has no current command
        (e.g. a node that was just added to the cluster by autoscaling), a start
        command is created for it from the subscription's configuration. Hosts
        that already have command state are left untouched so explicit per-host
        actions (including stops) are preserved.

        Returns True if a new subscription command was created for the host.
        """
        subscription_request_id = self.get_active_service_subscription(service_name)
        if not subscription_request_id:
            return False

        current_command = self.get_current_profiling_command(hostname, service_name)
        if current_command is not None:
            return False

        command_id = str(uuid.uuid4())
        return self.create_or_update_profiling_command(
            command_id=command_id,
            hostname=hostname,
            service_name=service_name,
            command_type="start",
            new_request_id=subscription_request_id,
        )

    def _merge_profiling_configs(self, existing_config: Dict, new_config: Dict) -> Dict:
        """Merge two profiling configurations, combining parameters appropriately"""
        # Handle case where existing_config might be None or empty
        if not existing_config:
            existing_config = {}

        merged = existing_config.copy()

        # Always use the latest command_type
        merged["command_type"] = new_config["command_type"]

        # For continuous, always make it true if either is true
        merged["continuous"] = existing_config.get("continuous", False) or new_config.get("continuous", False)

        # For duration, use the maximum (longer duration wins)
        if new_config.get("duration") and existing_config.get("duration"):
            merged["duration"] = max(new_config["duration"], existing_config["duration"])
        elif new_config.get("duration"):
            merged["duration"] = new_config["duration"]

        # For frequency, use the maximum (higher frequency wins)
        if new_config.get("frequency") and existing_config.get("frequency"):
            merged["frequency"] = max(new_config["frequency"], existing_config["frequency"])
        elif new_config.get("frequency"):
            merged["frequency"] = new_config["frequency"]

        # For profiling mode, use the latest one
        if new_config.get("profiling_mode"):
            merged["profiling_mode"] = new_config["profiling_mode"]

        # For PIDs, combine them (remove duplicates)
        existing_pids = set(existing_config.get("pids", []))
        new_pids = set(new_config.get("pids", []))
        combined_pids = list(existing_pids | new_pids)
        if combined_pids:
            merged["pids"] = combined_pids

        # For additional_args, merge the dictionaries (they should be clean now)
        if new_config.get("additional_args"):
            if existing_config.get("additional_args"):
                merged["additional_args"] = {**existing_config["additional_args"], **new_config["additional_args"]}
            else:
                merged["additional_args"] = new_config["additional_args"]

        # For stop_level, use the latest one
        if new_config.get("stop_level"):
            merged["stop_level"] = new_config["stop_level"]

        return merged

    def create_stop_command_for_host(
        self, command_id: str, hostname: str, service_name: str, request_id: str, stop_level: str = "host"
    ) -> bool:
        """Create a stop command for an entire host"""
        query = """
        INSERT INTO ProfilingCommands (
            command_id, hostname, service_name, command_type, request_ids,
            combined_config, status, created_at
        ) VALUES (
            %(command_id)s::uuid, %(hostname)s, %(service_name)s, 'stop',
            ARRAY[%(request_id)s::uuid],
            %(combined_config)s::jsonb,
            'pending', CURRENT_TIMESTAMP
        )
        ON CONFLICT (hostname, service_name)
        DO UPDATE SET
            command_id = %(command_id)s::uuid,
            command_type = 'stop',
            request_ids = array_append(ProfilingCommands.request_ids, %(request_id)s::uuid),
            combined_config = %(combined_config)s::jsonb,
            status = 'pending',
            created_at = CURRENT_TIMESTAMP
        """

        combined_config = {"stop_level": stop_level}

        values = {
            "command_id": command_id,
            "hostname": hostname,
            "service_name": service_name,
            "request_id": request_id,
            "combined_config": json.dumps(combined_config),
        }

        self.db.execute(query, values, has_value=False)
        return True

    def handle_process_level_stop(
        self,
        command_id: str,
        hostname: str,
        service_name: str,
        pids_to_stop: Optional[List[int]],
        request_id: str,
        stop_level: str = "process",
    ) -> bool:
        # Get current command for this host to check existing PIDs
        current_command = self.get_current_profiling_command(hostname, service_name)

        if current_command and current_command.get("command_type") == "start":
            current_pids = current_command.get("combined_config", {}).get("pids", [])

            if current_pids:
                # Remove specified PIDs from current command
                remaining_pids = [pid for pid in current_pids if pid not in pids_to_stop] if pids_to_stop else []

                if len(remaining_pids) < 1:
                    # Convert to host-level stop if no PIDs remain
                    return self.create_stop_command_for_host(command_id, hostname, service_name, request_id)
                else:
                    # Update command with remaining PIDs
                    query = """
                    UPDATE ProfilingCommands
                    SET command_id = %(command_id)s::uuid,
                        combined_config = jsonb_set(
                            jsonb_set(combined_config, '{pids}', %(remaining_pids)s::jsonb),
                            '{stop_level}', %(stop_level)s::jsonb
                        ),
                        request_ids = array_append(request_ids, %(request_id)s::uuid),
                        status = 'pending',
                        created_at = CURRENT_TIMESTAMP
                    WHERE hostname = %(hostname)s AND service_name = %(service_name)s
                    """

                    values = {
                        "command_id": command_id,
                        "hostname": hostname,
                        "service_name": service_name,
                        "request_id": request_id,
                        "remaining_pids": json.dumps(remaining_pids),
                        "stop_level": json.dumps(stop_level),
                    }

                    self.db.execute(query, values, has_value=False)
                    return True

        # Default: create stop command with specific PIDs
        query = """
        INSERT INTO ProfilingCommands (
            command_id, hostname, service_name, command_type, request_ids,
            combined_config, status, created_at
        ) VALUES (
            %(command_id)s::uuid, %(hostname)s, %(service_name)s, 'stop',
            ARRAY[%(request_id)s::uuid],
            %(combined_config)s::jsonb,
            'pending', CURRENT_TIMESTAMP
        )
        ON CONFLICT (hostname, service_name)
        DO UPDATE SET
            command_id = %(command_id)s::uuid,
            command_type = 'stop',
            request_ids = array_append(ProfilingCommands.request_ids, %(request_id)s::uuid),
            combined_config = %(combined_config)s::jsonb,
            status = 'pending',
            created_at = CURRENT_TIMESTAMP
        """

        combined_config = {"stop_level": stop_level, "pids": pids_to_stop}

        values = {
            "command_id": command_id,
            "hostname": hostname,
            "service_name": service_name,
            "request_id": request_id,
            "combined_config": json.dumps(combined_config),
        }

        self.db.execute(query, values, has_value=False)
        return True

    def get_current_profiling_command(self, hostname: str, service_name: str) -> Optional[Dict]:
        """Get the current profiling command for a host/service"""
        query = """
        SELECT command_id, command_type, combined_config, request_ids, status, created_at
        FROM ProfilingCommands
        WHERE hostname = %(hostname)s AND service_name = %(service_name)s
        ORDER BY created_at DESC
        LIMIT 1
        """

        values = {"hostname": hostname, "service_name": service_name}

        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result if result else None

    @staticmethod
    def _parse_json_field(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value

    @staticmethod
    def _normalize_profiling_status(command_type: Optional[str], command_status: Optional[str]) -> str:
        if command_status is None:
            return "stopped"
        if command_type == "start" and command_status in ["pending", "sent", "completed"]:
            return "active"
        return command_status

    @staticmethod
    def _summarize_enabled_profilers(combined_config: Dict[str, Any]) -> str:
        profiler_configs = combined_config.get("profiler_configs", {}) or {}
        if not profiler_configs:
            return "Default"

        profiler_labels = {
            "perf": "Perf",
            "async_profiler": "Java",
            "pyperf": "Pyperf",
            "pyspy": "Pyspy",
            "rbspy": "Rbspy",
            "phpspy": "PHPspy",
            "dotnet_trace": ".NET",
            "nodejs_perf": "NodeJS",
        }
        enabled = []
        for key, label in profiler_labels.items():
            value = profiler_configs.get(key)
            if value is None:
                continue
            if isinstance(value, dict):
                if value.get("enabled") is False or value.get("mode") == "disabled":
                    continue
            elif value == "disabled":
                continue
            enabled.append(label)
        return ", ".join(enabled) if enabled else "Disabled"

    def _extract_command_metadata(self, combined_config: Any, command_type: Optional[str], command_status: Optional[str]) -> Dict[str, Any]:
        config = self._parse_json_field(combined_config, {}) or {}
        current_pids = []
        for pid in config.get("pids", []) or []:
            if str(pid).isdigit():
                current_pids.append(int(pid))

        return {
            "combined_config": config,
            "pids": current_pids,
            "frequency": config.get("frequency"),
            "profiling_mode": "Continuous" if config.get("continuous") else "Ad Hoc",
            "profiler_summary": self._summarize_enabled_profilers(config),
            "command_type": command_type or "N/A",
            "profiling_status": self._normalize_profiling_status(command_type, command_status),
        }

    # Group keys per scope; the first element is always the grouping granularity and is
    # also used to build the stable row "id". Scopes that key on an optional column skip
    # records where that column is NULL (matching the previous Python behavior).
    _WORKLOAD_SCOPE_KEYS: Dict[str, List[str]] = {
        "service": ["service_name"],
        "namespace": ["service_name", "namespace"],
        "host": ["service_name", "hostname"],
        "pod": ["service_name", "namespace", "pod_name"],
        "container": ["service_name", "hostname", "namespace", "pod_name", "container_name"],
        "process": ["service_name", "hostname", "pid"],
    }
    _WORKLOAD_SCOPE_NULL_GUARD: Dict[str, str] = {
        "namespace": "namespace IS NOT NULL",
        "pod": "pod_name IS NOT NULL",
        "container": "container_name IS NOT NULL",
        "process": "pid IS NOT NULL",
    }
    # Join depth at which each logical column becomes available in the flatten base:
    # 0 = HostHeartbeats (+ its latest command), 1 = HeartbeatContainers, 2 = HeartbeatProcesses.
    _WORKLOAD_COLUMN_DEPTH: Dict[str, int] = {
        "hostname": 0,
        "ip_address": 0,
        "service_name": 0,
        "agent_version": 0,
        "run_mode": 0,
        "heartbeat_timestamp": 0,
        "command_type": 0,
        "namespace": 1,
        "pod_name": 1,
        "container_name": 1,
        "workload_name": 1,
        "workload_kind": 1,
        "process_name": 2,
        "pid": 2,
        "profiling_status": 2,
    }
    # Minimum base join depth needed to enumerate the distinct entities for each scope.
    _WORKLOAD_SCOPE_DEPTH: Dict[str, int] = {
        "service": 0,
        "host": 0,
        "namespace": 1,
        "pod": 1,
        "container": 1,
        "process": 2,
    }
    # Key column -> base-table qualified expression, used to push the per-entity
    # correlation down onto the indexed base tables in the hydrate LATERAL.
    _WORKLOAD_KEY_ALIAS: Dict[str, str] = {
        "service_name": "fh.service_name",
        "hostname": "fh.hostname",
        "namespace": "hc.namespace",
        "pod_name": "hc.pod_name",
        "container_name": "hc.container_name",
        "pid": "hp.pid",
    }
    # Whitelist of sortable columns that are NOT scope key columns -> (aggregate expression
    # over the entity's rows on the wrapped alias ``b``, required base depth). Scope key
    # columns are sorted directly on the key set and are handled separately. Client input is
    # matched against these keys only, so no caller string reaches the SQL.
    _WORKLOAD_SORT_AGG: Dict[str, Tuple[str, int]] = {
        "hostname": ("(array_agg(b.hostname ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 0),
        "ip_address": ("(array_agg(b.ip_address ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 0),
        "namespace": ("(array_agg(b.namespace ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 1),
        "pod_name": ("(array_agg(b.pod_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 1),
        "container_name": ("(array_agg(b.container_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 1),
        "process_name": ("(array_agg(b.process_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 2),
        "pid": ("(array_agg(b.pid ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 2),
        "heartbeat_timestamp": ("MAX(b.heartbeat_timestamp)", 0),
        "profiling_status": ("(array_agg(b.profiling_status ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 2),
        "agent_version": ("(array_agg(b.agent_version ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1]", 0),
        "host_count": ("COUNT(DISTINCT b.hostname)", 0),
        "namespace_count": ("COUNT(DISTINCT b.namespace) FILTER (WHERE b.namespace IS NOT NULL)", 1),
        "pod_count": ("COUNT(DISTINCT b.pod_name) FILTER (WHERE b.pod_name IS NOT NULL)", 1),
        "container_count": ("COUNT(DISTINCT b.container_name) FILTER (WHERE b.container_name IS NOT NULL)", 1),
        "process_count": ("COUNT(DISTINCT (b.pid, b.process_name)) FILTER (WHERE b.pid IS NOT NULL)", 2),
    }
    # Sortable column -> output column/alias produced by the grouped aggregation, used by
    # the single-pass (whole-scope GROUP BY) query path for its ORDER BY.
    _WORKLOAD_SORT_ALIAS: Dict[str, str] = {
        "hostname": "l_hostname",
        "ip_address": "l_ip_address",
        "namespace": "l_namespace",
        "pod_name": "l_pod_name",
        "container_name": "l_container_name",
        "process_name": "l_process_name",
        "pid": "l_pid",
        "heartbeat_timestamp": "l_heartbeat_timestamp",
        "profiling_status": "l_profiling_status",
        "agent_version": "l_agent_version",
        "host_count": "host_count",
        "namespace_count": "namespace_count",
        "pod_count": "pod_count",
        "container_count": "container_count",
        "process_count": "process_count",
    }

    # Row-level PID-aware profiling status. Only valid at depth >= 2 (needs ``hp.pid``);
    # references the latest command columns (``c.*``) exposed by ``current_commands``.
    _WORKLOAD_PROFILING_STATUS_CASE = """CASE
                    WHEN c.status IS NULL THEN 'stopped'
                    WHEN c.command_type = 'start' AND c.status IN ('pending', 'sent', 'completed') THEN
                        -- PID-aware: an active "start" command may target only a subset of
                        -- PIDs on the host (e.g. a single container/pod). A row is only
                        -- "active" when the command targets all PIDs on the host (no/empty
                        -- "pids" list == whole host) OR this row's PID is in the target set.
                        CASE
                            WHEN c.combined_config IS NULL
                                 OR (c.combined_config -> 'pids') IS NULL
                                 OR jsonb_typeof(c.combined_config -> 'pids') <> 'array'
                                 OR jsonb_array_length(c.combined_config -> 'pids') = 0
                                THEN 'active'
                            WHEN hp.pid IS NOT NULL AND EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements_text(c.combined_config -> 'pids') AS target(pid)
                                WHERE target.pid = hp.pid::text
                            ) THEN 'active'
                            ELSE 'stopped'
                        END
                    ELSE c.status::text
                END AS profiling_status"""

    def _workload_filter_spec(
        self,
        service_names: Optional[List[str]],
        exact_match: bool,
        hostnames: Optional[List[str]],
        ip_addresses: Optional[List[str]],
        namespaces: Optional[List[str]],
        pod_names: Optional[List[str]],
        container_names: Optional[List[str]],
        workload_names: Optional[List[str]],
        process_names: Optional[List[str]],
        profiling_statuses: Optional[List[str]],
        command_types: Optional[List[str]],
        pids: Optional[List[int]],
    ) -> Dict[str, Any]:
        """Translate the caller-supplied filters into SQL fragments.

        Returns a spec with:
          * ``service_filter`` – predicate on the raw ``HostHeartbeats h`` alias, pushed
            into the materialized ``fresh_hosts`` CTE.
          * ``conditions`` – list of ``(sql, depth)`` predicates on the wrapped base alias
            ``b`` (standard column names). ``depth`` is the minimum join depth at which the
            referenced column becomes available.
          * ``filter_depth`` – deepest ``depth`` among the active predicates.
          * ``params`` – bound query parameters.

        Every filter is applied identically wherever the base is used (tab counts, the
        entity key set, and the per-entity aggregation), preserving the previous semantics
        where all filters lived in a single ``filtered`` CTE.
        """
        params: Dict[str, Any] = {}
        conditions: List[Tuple[str, int]] = []

        def add_partial(column: str, values: Optional[List[Any]], prefix: str) -> None:
            if not values:
                return
            depth = self._WORKLOAD_COLUMN_DEPTH[column]
            ors = []
            for idx, value in enumerate(values):
                key = f"{prefix}_{idx}"
                ors.append(f"b.{column}::text ILIKE %({key})s")
                params[key] = f"%{value}%"
            conditions.append(("(" + " OR ".join(ors) + ")", depth))

        def add_exact(column: str, values: Optional[List[Any]], prefix: str) -> None:
            if not values:
                return
            depth = self._WORKLOAD_COLUMN_DEPTH[column]
            ors = []
            for idx, value in enumerate(values):
                key = f"{prefix}_{idx}"
                ors.append(f"LOWER(b.{column}::text) = LOWER(%({key})s)")
                params[key] = str(value)
            conditions.append(("(" + " OR ".join(ors) + ")", depth))

        service_filter = "TRUE"
        if service_names:
            if exact_match:
                service_filter = "fh.service_name = ANY(%(service_names)s)"
                params["service_names"] = service_names
            else:
                ors = []
                for idx, service_name in enumerate(service_names):
                    key = f"svc_{idx}"
                    ors.append(f"fh.service_name ILIKE %({key})s")
                    params[key] = f"%{service_name}%"
                service_filter = "(" + " OR ".join(ors) + ")"

        add_partial("hostname", hostnames, "host")
        add_partial("ip_address", ip_addresses, "ip")
        add_partial("namespace", namespaces, "ns")
        add_partial("pod_name", pod_names, "pod")
        add_partial("container_name", container_names, "cont")
        add_partial("workload_name", workload_names, "wl")
        add_partial("process_name", process_names, "proc")
        add_exact("profiling_status", profiling_statuses, "pstat")
        add_exact("command_type", command_types, "ctype")
        if pids:
            conditions.append(("b.pid = ANY(%(pids)s)", self._WORKLOAD_COLUMN_DEPTH["pid"]))
            params["pids"] = pids

        filter_depth = max((depth for _, depth in conditions), default=0)
        return {
            "params": params,
            "conditions": conditions,
            "service_filter": service_filter,
            "filter_depth": filter_depth,
        }

    def _workload_cte_prefix(self, service_filter: str) -> str:
        """Shared ``WITH`` prefix: the materialized active fleet and its latest commands."""
        return f"""
        WITH fresh_hosts AS MATERIALIZED (
            -- Restrict to the active fleet FIRST and materialize it, so grouping/sorting
            -- downstream can never drive a full-index scan over the (heavily stale)
            -- HostHeartbeats table. This is the difference between ~1s and a timeout.
            SELECT
                fh.id,
                fh.hostname,
                host(fh.ip_address) AS ip_address,
                fh.service_name,
                fh.agent_version,
                fh.run_mode,
                fh.heartbeat_timestamp
            FROM HostHeartbeats fh
            WHERE fh.heartbeat_timestamp > NOW() - INTERVAL '2 minutes'
              AND {service_filter}
        ),
        current_commands AS (
            -- ProfilingCommands is UNIQUE (hostname, service_name), so it is already
            -- one row per host/service; no window/dedup needed.
            SELECT hostname, service_name, command_type, status, combined_config
            FROM ProfilingCommands
        )"""

    def _workload_base_sql(
        self,
        depth: int,
        where_extra: Optional[List[str]] = None,
        driving: str = "cte",
        service_filter: str = "TRUE",
    ) -> str:
        """Build the flatten sub-SELECT down to ``depth`` (0=host, 1=+container, 2=+process).

        Columns are exposed under stable, unqualified names so a single set of filter and
        correlation predicates works at any depth. The container/process joins are only
        added when the depth requires them, so shallow scopes never pay for the full
        cross-product fan-out.

        ``driving`` selects the host source:
          * ``"cte"`` – scan the materialized ``fresh_hosts`` CTE once. Used for the
            (single-pass) entity key set and tab counts.
          * ``"direct"`` – read ``HostHeartbeats`` directly with the freshness + service
            predicate inline. Used inside the hydrate LATERAL so a correlated
            ``fh.service_name = p.service_name`` / ``fh.hostname = p.hostname`` predicate
            in ``where_extra`` uses the HostHeartbeats indexes instead of re-scanning the
            whole materialized CTE for every page entity.
        """
        ip_expr = "host(fh.ip_address) AS ip_address" if driving == "direct" else "fh.ip_address"
        cols = [
            "fh.id AS host_id",
            "fh.hostname",
            ip_expr,
            "fh.service_name",
            "fh.agent_version",
            "fh.run_mode",
            "fh.heartbeat_timestamp",
            "COALESCE(c.command_type, 'N/A') AS command_type",
            "c.status AS command_status",
            "c.combined_config AS combined_config",
        ]
        joins = [
            "LEFT JOIN current_commands c ON fh.hostname = c.hostname AND fh.service_name = c.service_name",
        ]
        if depth >= 1:
            cols += ["hc.container_name", "hc.namespace", "hc.pod_name", "hc.workload_name", "hc.workload_kind"]
            joins.append("LEFT JOIN HeartbeatContainers hc ON hc.host_id = fh.id")
        if depth >= 2:
            cols += ["hp.pid", "hp.process_name"]
            joins.append("LEFT JOIN HeartbeatProcesses hp ON hp.container_row_id = hc.id")
            cols.append(self._WORKLOAD_PROFILING_STATUS_CASE)
        select_list = ",\n                ".join(cols)
        join_list = "\n            ".join(joins)

        where_terms: List[str] = []
        if driving == "direct":
            from_clause = "HostHeartbeats fh"
            where_terms.append("fh.heartbeat_timestamp > NOW() - INTERVAL '2 minutes'")
            where_terms.append(service_filter)
        else:
            from_clause = "fresh_hosts fh"
        if where_extra:
            where_terms.extend(where_extra)
        where_sql = ("\n            WHERE " + " AND ".join(where_terms)) if where_terms else ""
        return f"""SELECT
                {select_list}
            FROM {from_clause}
            {join_list}{where_sql}"""

    @staticmethod
    def _workload_where(conditions: List[Tuple[str, int]], extra: Optional[List[str]] = None) -> str:
        terms = [sql for sql, _ in conditions]
        if extra:
            terms.extend(extra)
        return (" WHERE " + " AND ".join(terms)) if terms else ""

    @staticmethod
    def _workload_agg_columns() -> str:
        """The per-group aggregate SELECT list (references the wrapped base alias ``b``).

        Shared by both the entity-first LATERAL hydrate and the single-pass GROUP BY, so
        the two code paths return byte-identical row shapes. ``l_*`` columns are the latest
        (by heartbeat) representative for the group; the counts are per-scope cardinalities.
        """
        return """
                COUNT(DISTINCT b.hostname) AS host_count,
                COUNT(DISTINCT b.namespace) FILTER (WHERE b.namespace IS NOT NULL) AS namespace_count,
                COUNT(DISTINCT b.pod_name) FILTER (WHERE b.pod_name IS NOT NULL) AS pod_count,
                COUNT(DISTINCT b.container_name) FILTER (WHERE b.container_name IS NOT NULL) AS container_count,
                COUNT(DISTINCT (b.pid, b.process_name)) FILTER (WHERE b.pid IS NOT NULL) AS process_count,
                array_agg(DISTINCT b.pid) FILTER (WHERE b.pid IS NOT NULL) AS pids,
                (array_agg(b.hostname ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_hostname,
                (array_agg(b.ip_address ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_ip_address,
                (array_agg(b.namespace ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_namespace,
                (array_agg(b.pod_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_pod_name,
                (array_agg(b.container_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_container_name,
                (array_agg(b.workload_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_workload_name,
                (array_agg(b.workload_kind ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_workload_kind,
                (array_agg(b.process_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_process_name,
                (array_agg(b.pid ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_pid,
                (array_agg(b.command_type ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_command_type,
                (array_agg(b.command_status ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_command_status,
                (array_agg(b.combined_config ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_combined_config,
                bool_or(b.profiling_status = 'active') AS any_active,
                (array_agg(b.profiling_status ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_profiling_status,
                (array_agg(b.agent_version ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_agent_version,
                (array_agg(b.run_mode ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_run_mode,
                MAX(b.heartbeat_timestamp) AS l_heartbeat_timestamp"""

    def _workload_tab_counts(self, spec: Dict[str, Any]) -> Tuple[Dict[str, int], int]:
        """Compute the six scope tab counts + active host total using tiered queries.

        Instead of one pass of seven ``COUNT(DISTINCT tuple)`` over the full
        host x container x process flatten (which times out once the child tables are
        populated), each count is computed from the shallowest base that exposes its
        columns, using ``COUNT(*) FROM (SELECT DISTINCT ...)`` (a hash-distinct that is far
        cheaper than ``COUNT(DISTINCT tuple)``). All filters are still applied at every
        tier, so the counts match the previous single-pass semantics.
        """
        prefix = self._workload_cte_prefix(spec["service_filter"])
        params = spec["params"]
        conditions = spec["conditions"]
        filter_depth = spec["filter_depth"]

        # Tier A (host/service/active): base at host depth (or deeper if filters require it).
        base_a = self._workload_base_sql(max(0, filter_depth))
        where_a = self._workload_where(conditions)
        query_a = prefix + f""",
        fa AS MATERIALIZED (
            SELECT b.service_name, b.hostname FROM ({base_a}) b{where_a}
        )
        SELECT
            (SELECT COUNT(DISTINCT service_name) FROM fa) AS c_service,
            (SELECT COUNT(*) FROM (SELECT DISTINCT service_name, hostname FROM fa) d) AS c_host,
            (SELECT COUNT(DISTINCT hostname) FROM fa) AS active_hosts
        """
        row_a = (self.db.execute(query_a, params, one_value=False, return_dict=True, fetch_all=True) or [{}])[0] or {}

        # Tier B (namespace/pod/container): base at container depth.
        base_b = self._workload_base_sql(max(1, filter_depth))
        where_b = self._workload_where(conditions)
        query_b = prefix + f""",
        fb AS MATERIALIZED (
            SELECT b.service_name, b.hostname, b.namespace, b.pod_name, b.container_name
            FROM ({base_b}) b{where_b}
        )
        SELECT
            (SELECT COUNT(*) FROM (SELECT DISTINCT service_name, namespace FROM fb WHERE namespace IS NOT NULL) d) AS c_namespace,
            (SELECT COUNT(*) FROM (SELECT DISTINCT service_name, namespace, pod_name FROM fb WHERE pod_name IS NOT NULL) d) AS c_pod,
            (SELECT COUNT(*) FROM (SELECT DISTINCT service_name, hostname, namespace, pod_name, container_name FROM fb WHERE container_name IS NOT NULL) d) AS c_container
        """
        row_b = (self.db.execute(query_b, params, one_value=False, return_dict=True, fetch_all=True) or [{}])[0] or {}

        # Tier C (process): base at process depth. ``(host_id, pid)`` is 1:1 with
        # ``(service_name, hostname, pid)`` (unique_host_heartbeat) but distinct on the two
        # integer columns is dramatically cheaper than on the wide text tuple.
        base_c = self._workload_base_sql(max(2, filter_depth))
        where_c = self._workload_where(conditions, extra=["b.pid IS NOT NULL"])
        query_c = prefix + f""",
        fc AS MATERIALIZED (
            SELECT b.host_id, b.pid FROM ({base_c}) b{where_c}
        )
        SELECT (SELECT COUNT(*) FROM (SELECT DISTINCT host_id, pid FROM fc) d) AS c_process
        """
        row_c = (self.db.execute(query_c, params, one_value=False, return_dict=True, fetch_all=True) or [{}])[0] or {}

        tab_counts = {
            "service": row_a.get("c_service") or 0,
            "namespace": row_b.get("c_namespace") or 0,
            "host": row_a.get("c_host") or 0,
            "pod": row_b.get("c_pod") or 0,
            "container": row_b.get("c_container") or 0,
            "process": row_c.get("c_process") or 0,
        }
        active_hosts = row_a.get("active_hosts") or 0
        return tab_counts, active_hosts

    def _build_workload_row(
        self, db_row: Dict[str, Any], scope: str, key_cols: List[str]
    ) -> Dict[str, Any]:
        """Build one API row dict from a grouped/summary DB row.

        Shared by the live grouped query and the precomputed-summary reader; both
        expose the same column names (key cols + ``l_*``/count aggregates).
        """
        key_values = [db_row.get(col) for col in key_cols]
        row_id = "|".join("" if value is None else str(value) for value in key_values)
        command_metadata = self._extract_command_metadata(
            db_row.get("l_combined_config"),
            db_row.get("l_command_type"),
            db_row.get("l_command_status"),
        )
        # Prefer the PID-aware, row-level status computed in SQL over the host-level
        # command status. A group is "active" when any of its rows are actively
        # targeted (whole-host command or a matching PID); otherwise fall back to the
        # latest row status so entities on a host that is only partially profiled
        # (e.g. one container) are not incorrectly shown as active.
        profiling_status = "active" if db_row.get("any_active") else db_row.get("l_profiling_status")
        if not profiling_status:
            profiling_status = command_metadata.get("profiling_status")
        host_count = db_row.get("host_count") or 0
        return {
            "id": row_id,
            "scope": scope,
            "service_name": db_row.get("service_name"),
            "namespace": db_row.get("l_namespace"),
            "hostname": db_row.get("l_hostname"),
            "ip_address": db_row.get("l_ip_address"),
            "pod_name": db_row.get("l_pod_name"),
            "container_name": db_row.get("l_container_name"),
            "workload_name": db_row.get("l_workload_name"),
            "workload_kind": db_row.get("l_workload_kind"),
            "process_name": db_row.get("l_process_name"),
            "pid": db_row.get("l_pid"),
            "pids": sorted(db_row.get("pids") or []),
            "active_hosts": host_count,
            "host_count": host_count,
            "namespace_count": db_row.get("namespace_count") or 0,
            "pod_count": db_row.get("pod_count") or 0,
            "container_count": db_row.get("container_count") or 0,
            "process_count": db_row.get("process_count") or 0,
            "command_type": command_metadata.get("command_type"),
            "profiling_status": profiling_status,
            "profiling_mode": command_metadata.get("profiling_mode"),
            "frequency": command_metadata.get("frequency"),
            "profiler_summary": command_metadata.get("profiler_summary"),
            "heartbeat_timestamp": db_row.get("l_heartbeat_timestamp"),
            "agent_version": db_row.get("l_agent_version"),
            "run_mode": db_row.get("l_run_mode"),
        }

    # Scopes whose grouped rows are precomputed into workload_scope_summary.
    _WORKLOAD_SUMMARY_SCOPES = frozenset({"service", "namespace", "pod"})

    def _precomputed_tab_counts(self) -> Optional[Tuple[Dict[str, int], int]]:
        """Read the six tab counts + active_hosts from the precomputed store.

        Returns ``None`` when the store is unavailable -- not built yet (fresh
        deploy before the first refresh) or the migration has not been applied --
        so callers transparently fall back to the live computation.
        """
        try:
            rows = self.db.execute(
                "SELECT scope, count FROM workload_tab_counts",
                {}, one_value=False, return_dict=True, fetch_all=True,
            )
        except Exception:
            # Store missing/unavailable -> fall back to the live path.
            return None
        if not rows:
            return None
        by_scope = {r["scope"]: r["count"] for r in rows}
        tab_counts = {
            "service": by_scope.get("service") or 0,
            "namespace": by_scope.get("namespace") or 0,
            "host": by_scope.get("host") or 0,
            "pod": by_scope.get("pod") or 0,
            "container": by_scope.get("container") or 0,
            "process": by_scope.get("process") or 0,
        }
        return tab_counts, (by_scope.get("active_hosts") or 0)

    def _precomputed_scope_rows(
        self, scope: str, page: int, page_size: int, sort_by: Optional[str], sort_order: str
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Read a page of grouped rows for a coarse scope from workload_scope_summary."""
        key_cols = self._WORKLOAD_SCOPE_KEYS.get(scope, self._WORKLOAD_SCOPE_KEYS["service"])
        direction = "DESC" if str(sort_order).lower() == "desc" else "ASC"
        sort_col = None
        if sort_by and sort_by in key_cols:
            sort_col = sort_by
        elif sort_by and sort_by in self._WORKLOAD_SORT_ALIAS:
            sort_col = self._WORKLOAD_SORT_ALIAS[sort_by]
        # Deterministic order: requested sort (if any) then the precomputed key order.
        order_by = (f"{sort_col} {direction} NULLS LAST, sort_seq ASC" if sort_col else "sort_seq ASC")
        query = f"""
        SELECT *, COUNT(*) OVER () AS total_groups
        FROM workload_scope_summary
        WHERE scope = %(scope)s
        ORDER BY {order_by}
        LIMIT %(page_size)s OFFSET %(offset)s
        """
        params = {"scope": scope, "page_size": page_size, "offset": page * page_size}
        db_rows = self.db.execute(query, params, one_value=False, return_dict=True, fetch_all=True)
        total_count = db_rows[0]["total_groups"] if db_rows else 0
        rows = [self._build_workload_row(db_row, scope, key_cols) for db_row in db_rows or []]
        return rows, total_count

    def _query_workload_groups(
        self,
        scope: str,
        spec: Dict[str, Any],
        page: int = 0,
        page_size: int = 50,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        key_cols = self._WORKLOAD_SCOPE_KEYS.get(scope, self._WORKLOAD_SCOPE_KEYS["process"])
        scope_depth = self._WORKLOAD_SCOPE_DEPTH.get(scope, 2)
        conditions = spec["conditions"]
        filter_depth = spec["filter_depth"]
        params = dict(spec["params"])

        # ------------------------------------------------------------------ strategy
        # Two aggregation strategies, chosen by whether the scope keys on a specific host:
        #   * hostname IN key (host/container/process): "entity-first". Enumerate the page
        #     of entities from the shallow key set, then hydrate ONLY that page via a
        #     LATERAL that is bounded to a single host (indexed) per row. Great for the many
        #     small entities of these scopes (the default host view is ~0.1s of query time).
        #   * hostname NOT IN key (service/namespace/pod): "single-pass". These scopes have
        #     comparatively few, large entities that each span many hosts, so a per-entity
        #     LATERAL would re-scan whole services repeatedly. Instead compute every group
        #     in one GROUP BY over the flatten (a couple of seconds) and paginate the result.
        direction = "DESC" if str(sort_order).lower() == "desc" else "ASC"
        agg_columns = self._workload_agg_columns()
        guard_col = key_cols[-1] if scope in self._WORKLOAD_SCOPE_NULL_GUARD else None
        use_entity_first = "hostname" in key_cols
        # `service` has no host key and few/large groups, but (unlike namespace/pod) its
        # groups span whole hosts, so its per-group counts can be computed at the cheap
        # container grain and its `any_active` at the host grain -- for service scope that
        # is provably identical to the PID-aware value (a command's target PIDs always
        # belong to the service's own hosts). Only when no process-tier filter is present
        # (which would need the process grain to stay correct).
        use_two_grain = scope == "service" and filter_depth < 2

        if use_entity_first:
            # ---------- ordering: page the key set, sorting on a key or (materialized) aggregate
            sort_agg_expr: Optional[str] = None
            sort_depth = 0
            order_pairs: List[Tuple[str, str]] = []
            if sort_by and sort_by in key_cols:
                order_pairs.append((sort_by, direction))
                order_pairs.extend((col, "ASC") for col in key_cols if col != sort_by)
            elif sort_by and sort_by in self._WORKLOAD_SORT_AGG:
                sort_agg_expr, sort_depth = self._WORKLOAD_SORT_AGG[sort_by]
                order_pairs.append(("__sort", direction))
                order_pairs.extend((col, "ASC") for col in key_cols)
            else:
                order_pairs.extend((col, "ASC") for col in key_cols)

            # ---------- entity key/summary set (shallowest base that exposes key + filters + sort)
            page_depth = max(scope_depth, filter_depth, sort_depth)
            guard_extra = [f"b.{guard_col} IS NOT NULL"] if guard_col else []
            base_page = self._workload_base_sql(page_depth)
            summary_where = self._workload_where(conditions, extra=guard_extra)
            summary_select = ", ".join(f"b.{col}" for col in key_cols)
            if sort_agg_expr:
                summary_select += f", {sort_agg_expr} AS __sort"
            group_by = ", ".join(f"b.{col}" for col in key_cols)
            page_order = ", ".join(f"{col} {dir_} NULLS LAST" for col, dir_ in order_pairs)

            # ---------- per-entity hydrate. Only host-level keys are correlated (with ``=``)
            # inside the base sub-SELECT so the plan drives from the HostHeartbeats
            # service_name/hostname indexes; finer keys are NULL-safe residual filters on the
            # host-bounded set (never pushed onto child tables, which would let the planner
            # drive from a global index scan and explode on common namespaces).
            host_key_corr: List[str] = []
            residual_corr: List[str] = []
            for col in key_cols:
                if self._WORKLOAD_COLUMN_DEPTH[col] == 0:
                    host_key_corr.append(f"{self._WORKLOAD_KEY_ALIAS[col]} = p.{col}")
                else:
                    residual_corr.append(f"b.{col} IS NOT DISTINCT FROM p.{col}")
            base_full = self._workload_base_sql(
                2, where_extra=host_key_corr, driving="direct", service_filter=spec["service_filter"]
            )
            lateral_terms = residual_corr + [sql for sql, _ in conditions]
            lateral_where = ("\n            WHERE " + " AND ".join(lateral_terms)) if lateral_terms else ""
            final_order = ", ".join(f"p.{col} {dir_} NULLS LAST" for col, dir_ in order_pairs)
            page_key_select = ", ".join(f"p.{col}" for col in key_cols)

            query = self._workload_cte_prefix(spec["service_filter"]) + f""",
        entity_summary AS MATERIALIZED (
            SELECT {summary_select}
            FROM ({base_page}) b{summary_where}
            GROUP BY {group_by}
        ),
        page AS (
            SELECT * FROM entity_summary
            ORDER BY {page_order}
            LIMIT %(page_size)s OFFSET %(offset)s
        )
        SELECT
            {page_key_select},
            agg.*,
            (SELECT COUNT(*) FROM entity_summary) AS total_groups
        FROM page p
        LEFT JOIN LATERAL (
            SELECT{agg_columns}
            FROM ({base_full}) b
            {lateral_where}
        ) agg ON true
        ORDER BY {final_order}
        """
        elif use_two_grain:
            # ---------- two-grain single-pass (service scope). Counts + latest metadata at
            # the container grain (~316K rows), process_count via the cheap
            # COUNT(*) FROM (SELECT DISTINCT ...) trick, and any_active at the host grain
            # (identical to PID-aware for service scope). Avoids aggregating the full
            # ~1.08M process flatten -> ~16s down to ~4s on prod. Process-grain
            # representatives (l_process_name/l_pid/pids) are not shown at service scope and
            # are returned NULL/empty.
            sort_out_col = None
            if sort_by and sort_by in key_cols:
                sort_out_col = sort_by
            elif sort_by and sort_by in self._WORKLOAD_SORT_ALIAS:
                sort_out_col = self._WORKLOAD_SORT_ALIAS[sort_by]
            order_terms = [f"{sort_out_col} {direction} NULLS LAST"] if sort_out_col else []
            order_terms.extend(f"{col} ASC NULLS LAST" for col in key_cols if col != sort_out_col)
            two_order = ", ".join(order_terms)

            cbase = self._workload_base_sql(1)
            cwhere = self._workload_where(conditions)
            pbase = self._workload_base_sql(2)
            pwhere = self._workload_where(conditions, extra=["b.pid IS NOT NULL"])

            query = self._workload_cte_prefix(spec["service_filter"]) + f""",
        cagg AS (
            SELECT
                b.service_name,
                COUNT(DISTINCT b.hostname) AS host_count,
                COUNT(DISTINCT b.namespace) FILTER (WHERE b.namespace IS NOT NULL) AS namespace_count,
                COUNT(DISTINCT b.pod_name) FILTER (WHERE b.pod_name IS NOT NULL) AS pod_count,
                COUNT(DISTINCT b.container_name) FILTER (WHERE b.container_name IS NOT NULL) AS container_count,
                NULL::integer[] AS pids,
                (array_agg(b.hostname ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_hostname,
                (array_agg(b.ip_address ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_ip_address,
                (array_agg(b.namespace ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_namespace,
                (array_agg(b.pod_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_pod_name,
                (array_agg(b.container_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_container_name,
                (array_agg(b.workload_name ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_workload_name,
                (array_agg(b.workload_kind ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_workload_kind,
                NULL::text AS l_process_name,
                NULL::integer AS l_pid,
                (array_agg(b.command_type ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_command_type,
                (array_agg(b.command_status ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_command_status,
                (array_agg(b.combined_config ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_combined_config,
                bool_or(b.command_type = 'start' AND b.command_status IN ('pending', 'sent', 'completed')) AS any_active,
                NULL::text AS l_profiling_status,
                (array_agg(b.agent_version ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_agent_version,
                (array_agg(b.run_mode ORDER BY b.heartbeat_timestamp DESC NULLS LAST))[1] AS l_run_mode,
                MAX(b.heartbeat_timestamp) AS l_heartbeat_timestamp,
                COUNT(*) OVER () AS total_groups
            FROM ({cbase}) b{cwhere}
            GROUP BY b.service_name
        ),
        pcount AS (
            SELECT service_name, COUNT(*) AS process_count
            FROM (SELECT DISTINCT b.service_name, b.pid, b.process_name FROM ({pbase}) b{pwhere}) d
            GROUP BY service_name
        )
        SELECT
            c.service_name,
            c.host_count, c.namespace_count, c.pod_count, c.container_count,
            COALESCE(pc.process_count, 0) AS process_count,
            c.pids, c.l_hostname, c.l_ip_address, c.l_namespace, c.l_pod_name, c.l_container_name,
            c.l_workload_name, c.l_workload_kind, c.l_process_name, c.l_pid,
            c.l_command_type, c.l_command_status, c.l_combined_config, c.any_active,
            c.l_profiling_status, c.l_agent_version, c.l_run_mode, c.l_heartbeat_timestamp,
            c.total_groups
        FROM cagg c
        LEFT JOIN pcount pc ON pc.service_name = c.service_name
        ORDER BY {two_order}
        LIMIT %(page_size)s OFFSET %(offset)s
        """
        else:
            # ---------- single-pass: one GROUP BY over the flatten, paginated. ORDER BY
            # references the grouped output columns (key columns or ``l_*``/count aliases).
            sort_out_col = None
            if sort_by and sort_by in key_cols:
                sort_out_col = sort_by
            elif sort_by and sort_by in self._WORKLOAD_SORT_ALIAS:
                sort_out_col = self._WORKLOAD_SORT_ALIAS[sort_by]
            order_terms = [f"{sort_out_col} {direction} NULLS LAST"] if sort_out_col else []
            order_terms.extend(f"{col} ASC NULLS LAST" for col in key_cols if col != sort_out_col)
            single_order = ", ".join(order_terms)

            guard_extra = [f"b.{guard_col} IS NOT NULL"] if guard_col else []
            base_single = self._workload_base_sql(2)
            single_where = self._workload_where(conditions, extra=guard_extra)
            key_select = ", ".join(f"b.{col}" for col in key_cols)
            group_by = ", ".join(f"b.{col}" for col in key_cols)

            query = self._workload_cte_prefix(spec["service_filter"]) + f"""
        SELECT
            {key_select},{agg_columns},
            COUNT(*) OVER () AS total_groups
        FROM ({base_single}) b{single_where}
        GROUP BY {group_by}
        ORDER BY {single_order}
        LIMIT %(page_size)s OFFSET %(offset)s
        """

        group_params = {**params, "page_size": page_size, "offset": page * page_size}
        db_rows = self.db.execute(query, group_params, one_value=False, return_dict=True, fetch_all=True)
        total_count = db_rows[0]["total_groups"] if db_rows else 0
        rows = [self._build_workload_row(db_row, scope, key_cols) for db_row in db_rows or []]
        # Ordering and pagination are done in SQL (see order_by/LIMIT above).
        return rows, total_count

    def get_workload_inventory_status(
        self,
        scope: str,
        service_names: Optional[List[str]] = None,
        hostnames: Optional[List[str]] = None,
        ip_addresses: Optional[List[str]] = None,
        namespaces: Optional[List[str]] = None,
        pod_names: Optional[List[str]] = None,
        container_names: Optional[List[str]] = None,
        workload_names: Optional[List[str]] = None,
        process_names: Optional[List[str]] = None,
        profiling_statuses: Optional[List[str]] = None,
        command_types: Optional[List[str]] = None,
        pids: Optional[List[int]] = None,
        exact_match: bool = False,
        page: int = 0,
        page_size: int = 50,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
    ) -> Dict[str, Any]:
        spec = self._workload_filter_spec(
            service_names=service_names,
            exact_match=exact_match,
            hostnames=hostnames,
            ip_addresses=ip_addresses,
            namespaces=namespaces,
            pod_names=pod_names,
            container_names=container_names,
            workload_names=workload_names,
            process_names=process_names,
            profiling_statuses=profiling_statuses,
            command_types=command_types,
            pids=pids,
        )

        # Fast path: with no filters, serve from the precomputed store (rebuilt every
        # ~30s by the periodic worker). Counts + coarse-scope rows come from the Layer 2
        # summaries; host/container/process rows still use the (fast) live grouped query.
        # Falls back to the fully live path when the store has not been built yet.
        no_filters = not spec["conditions"] and spec["service_filter"] == "TRUE"
        if no_filters:
            precomputed = self._precomputed_tab_counts()
            if precomputed is not None:
                tab_counts, active_hosts = precomputed
                if scope in self._WORKLOAD_SUMMARY_SCOPES:
                    rows, total_count = self._precomputed_scope_rows(
                        scope, page, page_size, sort_by, sort_order
                    )
                else:
                    rows, total_count = self._query_workload_groups(
                        scope, spec, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order
                    )
                return {
                    "scope": scope,
                    "rows": rows,
                    "tab_counts": tab_counts,
                    "active_hosts": active_hosts,
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size,
                }

        # Filtered (or store-not-built) path: tiered counts + live grouped query.
        tab_counts, active_hosts = self._workload_tab_counts(spec)

        rows, total_count = self._query_workload_groups(
            scope, spec, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order
        )

        return {
            "scope": scope,
            "rows": rows,
            "tab_counts": tab_counts,
            "active_hosts": active_hosts,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
        }

    def resolve_workload_targets(
        self,
        service_name: str,
        target_scope: str,
        target_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Optional[List[int]]]:
        """Resolve workload selectors into concrete host/PID profiling targets.

        Matching is pushed down to SQL joins over HostHeartbeats / HeartbeatContainers /
        HeartbeatProcesses so we never materialize the full inventory in Python.
        Service- and host-scope resolve to host-level targets (PID list = None); the
        finer scopes resolve to per-host PID sets.
        """
        entities = target_entities or [{"service_name": service_name}]
        recency = "h.heartbeat_timestamp > NOW() - INTERVAL '2 minutes'"

        if target_scope in ("service", "host"):
            query = (
                f"SELECT DISTINCT h.hostname FROM HostHeartbeats h "
                f"WHERE {recency} AND h.service_name = %(service_name)s"
            )
            params: Dict[str, Any] = {"service_name": service_name}
            if target_scope == "host":
                wanted_hosts = sorted(
                    {
                        entity.get("hostname")
                        for entity in entities
                        if entity.get("hostname")
                        and (not entity.get("service_name") or entity.get("service_name") == service_name)
                    }
                )
                if not wanted_hosts:
                    return {}
                query += " AND h.hostname = ANY(%(wanted_hosts)s)"
                params["wanted_hosts"] = wanted_hosts

            rows = self.db.execute(query, params, one_value=False, return_dict=True, fetch_all=True)
            hostnames = sorted({row["hostname"] for row in (rows or []) if row.get("hostname")})
            return {hostname: None for hostname in hostnames}

        # Finer scopes require a concrete process, so inner-join through to processes.
        base_from = (
            "FROM HostHeartbeats h "
            "JOIN HeartbeatContainers hc ON hc.host_id = h.id "
            "JOIN HeartbeatProcesses hp ON hp.container_row_id = hc.id "
            f"WHERE {recency} AND h.service_name = %(service_name)s"
        )

        host_pid_mapping: Dict[str, Set[int]] = defaultdict(set)
        for entity in entities:
            if entity.get("service_name") and entity.get("service_name") != service_name:
                continue

            conditions: List[str] = []
            params = {"service_name": service_name}

            if target_scope == "namespace":
                conditions.append("hc.namespace IS NOT DISTINCT FROM %(e_namespace)s")
                params["e_namespace"] = entity.get("namespace")
            elif target_scope == "workload":
                conditions.append("hc.workload_name IS NOT DISTINCT FROM %(e_workload)s")
                params["e_workload"] = entity.get("workload_name")
                if entity.get("namespace") is not None:
                    conditions.append("hc.namespace = %(e_namespace)s")
                    params["e_namespace"] = entity.get("namespace")
            elif target_scope == "pod":
                conditions.append("hc.pod_name IS NOT DISTINCT FROM %(e_pod)s")
                params["e_pod"] = entity.get("pod_name")
                if entity.get("namespace") is not None:
                    conditions.append("hc.namespace = %(e_namespace)s")
                    params["e_namespace"] = entity.get("namespace")
            elif target_scope == "container":
                conditions.append("hc.container_name IS NOT DISTINCT FROM %(e_container)s")
                params["e_container"] = entity.get("container_name")
                if entity.get("pod_name") is not None:
                    conditions.append("hc.pod_name = %(e_pod)s")
                    params["e_pod"] = entity.get("pod_name")
                if entity.get("namespace") is not None:
                    conditions.append("hc.namespace = %(e_namespace)s")
                    params["e_namespace"] = entity.get("namespace")
            elif target_scope == "process":
                # (pid match) OR (process_name match + optional container/pod/namespace),
                # mirroring the original disjunction.
                or_parts: List[str] = []
                if entity.get("pid") is not None:
                    or_parts.append("hp.pid = %(e_pid)s")
                    params["e_pid"] = entity.get("pid")
                if entity.get("process_name") is not None:
                    name_conditions = ["hp.process_name = %(e_process)s"]
                    params["e_process"] = entity.get("process_name")
                    if entity.get("container_name") is not None:
                        name_conditions.append("hc.container_name = %(e_container)s")
                        params["e_container"] = entity.get("container_name")
                    if entity.get("pod_name") is not None:
                        name_conditions.append("hc.pod_name = %(e_pod)s")
                        params["e_pod"] = entity.get("pod_name")
                    if entity.get("namespace") is not None:
                        name_conditions.append("hc.namespace = %(e_namespace)s")
                        params["e_namespace"] = entity.get("namespace")
                    or_parts.append("(" + " AND ".join(name_conditions) + ")")
                if not or_parts:
                    continue
                conditions.append("(" + " OR ".join(or_parts) + ")")
            else:
                continue

            where_extra = (" AND " + " AND ".join(conditions)) if conditions else ""
            query = f"SELECT h.hostname, hp.pid {base_from}{where_extra}"
            rows = self.db.execute(query, params, one_value=False, return_dict=True, fetch_all=True)
            for row in rows or []:
                if row.get("hostname") is not None and row.get("pid") is not None:
                    host_pid_mapping[row["hostname"]].add(row["pid"])

        return {hostname: sorted(pid_set) for hostname, pid_set in host_pid_mapping.items()}

    def get_profiling_host_status_optimized(
        self,
        service_names: Optional[List[str]] = None,
        hostnames: Optional[List[str]] = None,
        ip_addresses: Optional[List[str]] = None,
        profiling_statuses: Optional[List[str]] = None,
        command_types: Optional[List[str]] = None,
        pids: Optional[List[int]] = None,
        exact_match: bool = False
    ) -> List[Dict]:
        """
        Get profiling host status with all filters applied in a single optimized query.
        Uses JOIN to combine HostHeartbeats and ProfilingCommands data efficiently.

        This method solves the N+1 query problem by using a single SQL query with:
        - Common Table Expressions (CTEs) for readability
        - LEFT JOIN to combine HostHeartbeats and ProfilingCommands
        - Window functions (ROW_NUMBER()) to get latest command per host
        - Database-side filtering for all parameters

        Args:
            service_names: List of service names to filter by
            hostnames: List of hostnames to filter by (partial match)
            ip_addresses: List of IP addresses to filter by (partial match)
            profiling_statuses: List of profiling statuses to filter by
            command_types: List of command types to filter by
            pids: List of PIDs to filter by
            exact_match: Whether to use exact match for service names

        Returns:
            List of dictionaries with host status information
        """
        # Build the query with CTEs for better readability and performance
        query = """
        WITH latest_commands AS (
            SELECT
                pc.hostname,
                pc.service_name,
                pc.command_type,
                pc.status,
                pc.combined_config,
                pc.created_at,
                ROW_NUMBER() OVER (PARTITION BY pc.hostname, pc.service_name ORDER BY pc.created_at DESC) as rn
            FROM ProfilingCommands pc
        ),
        current_commands AS (
            SELECT
                hostname,
                service_name,
                command_type,
                status,
                combined_config
            FROM latest_commands
            WHERE rn = 1
        )
        SELECT
            h.id,
            h.hostname,
            h.ip_address,
            h.service_name,
            h.heartbeat_timestamp,
            c.command_type,
            c.status,
            c.combined_config
        FROM HostHeartbeats h
        LEFT JOIN current_commands c
            ON h.hostname = c.hostname AND h.service_name = c.service_name
        WHERE 1=1
            -- Only show hosts that sent heartbeat in last 2 minutes (recently active)
            -- This improves page load performance by filtering out stale/inactive hosts
            AND h.heartbeat_timestamp > NOW() - INTERVAL '2 minutes'
        """

        values: Dict[str, Any] = {}

        # Apply service_name filter
        if service_names:
            if exact_match:
                query += " AND h.service_name = ANY(%(service_names)s)"
                values["service_names"] = service_names
            else:
                # Use ILIKE with OR for partial matching across multiple service names
                service_conditions = []
                for idx, service_name in enumerate(service_names):
                    param_name = f"service_name_{idx}"
                    service_conditions.append(f"h.service_name ILIKE %({param_name})s")
                    values[param_name] = f"%{service_name}%"
                query += f" AND ({' OR '.join(service_conditions)})"

        # Apply hostname filter (partial match with ILIKE)
        if hostnames:
            hostname_conditions = []
            for idx, hostname in enumerate(hostnames):
                param_name = f"hostname_{idx}"
                hostname_conditions.append(f"h.hostname ILIKE %({param_name})s")
                values[param_name] = f"%{hostname}%"
            query += f" AND ({' OR '.join(hostname_conditions)})"

        # Apply IP address filter (partial match)
        # Note: ip_address is inet type, so we cast to text for LIKE matching
        if ip_addresses:
            ip_conditions = []
            for idx, ip_addr in enumerate(ip_addresses):
                param_name = f"ip_address_{idx}"
                ip_conditions.append(f"h.ip_address::text LIKE %({param_name})s")
                values[param_name] = f"%{ip_addr}%"
            query += f" AND ({' OR '.join(ip_conditions)})"

        # Apply profiling status filter
        if profiling_statuses:
            # Convert to lowercase for case-insensitive comparison
            # Handle 'stopped' as NULL status (no command exists)
            status_conditions = []
            has_stopped = False
            for idx, status in enumerate(profiling_statuses):
                if status.lower() == 'stopped':
                    has_stopped = True
                else:
                    param_name = f"status_{idx}"
                    status_conditions.append(f"LOWER(c.status::text) = LOWER(%({param_name})s)")
                    values[param_name] = status

            if has_stopped:
                status_conditions.append("c.status IS NULL")

            if status_conditions:
                query += f" AND ({' OR '.join(status_conditions)})"

        # Apply command type filter
        if command_types:
            command_type_conditions = []
            has_na = False
            for idx, cmd_type in enumerate(command_types):
                if cmd_type.lower() == 'n/a':
                    has_na = True
                else:
                    param_name = f"command_type_{idx}"
                    command_type_conditions.append(f"LOWER(c.command_type) = LOWER(%({param_name})s)")
                    values[param_name] = cmd_type

            if has_na:
                command_type_conditions.append("c.command_type IS NULL")

            if command_type_conditions:
                query += f" AND ({' OR '.join(command_type_conditions)})"

        # For PIDs filter, we need to check inside the JSONB combined_config
        # This is more complex and might still need some post-processing
        if pids:
            # Check if any of the requested PIDs exist in the combined_config->pids array
            query += " AND c.combined_config IS NOT NULL"
            query += " AND c.combined_config ? 'pids'"

        query += " ORDER BY h.heartbeat_timestamp DESC"

        results = self.db.execute(query, values, one_value=False, return_dict=True, fetch_all=True)

        # Post-process for PID filtering if needed (this is still more efficient than N queries)
        if pids and results:
            filtered_results = []
            for row in results:
                combined_config = row.get("combined_config")
                if combined_config:
                    if isinstance(combined_config, str):
                        try:
                            combined_config = json.loads(combined_config)
                        except json.JSONDecodeError:
                            combined_config = {}

                    if isinstance(combined_config, dict):
                        pids_in_config = combined_config.get("pids", [])
                        if isinstance(pids_in_config, list):
                            command_pids = [int(pid) for pid in pids_in_config if str(pid).isdigit()]
                            # Check if any filter PID matches command PIDs
                            if any(filter_pid in command_pids for filter_pid in pids):
                                filtered_results.append(row)
                        else:
                            # No PIDs in config, skip
                            continue
                    else:
                        # Invalid config, skip
                        continue
                else:
                    # No config, skip when filtering by PIDs
                    continue
            return filtered_results

        return results

    def get_total_host_count(
        self,
        service_names: Optional[List[str]] = None,
        exact_match: bool = False,
    ) -> int:
        """
        Get total host count for the selected service(s).
        This count IS filtered by service_name - shows total hosts for the selected service.
        Fast query using COUNT with indexed columns.
        
        Args:
            service_names: Optional list of service names to filter by
            exact_match: If True, use exact match for service names; if False, use partial match (ILIKE)
        
        Returns:
            Total count of distinct hosts for the selected service(s)
        """
        query = """
            SELECT COUNT(DISTINCT hostname) as total_count
            FROM HostHeartbeats
            WHERE 1=1
        """
        
        values: Dict[str, Any] = {}
        
        # Apply service_name filter if provided
        if service_names:
            if exact_match:
                query += " AND service_name = ANY(%(service_names)s)"
                values["service_names"] = service_names
            else:
                # Use ILIKE with OR for partial matching across multiple service names
                service_conditions = []
                for idx, service_name in enumerate(service_names):
                    param_name = f"service_name_{idx}"
                    service_conditions.append(f"service_name ILIKE %({param_name})s")
                    values[param_name] = f"%{service_name}%"
                query += f" AND ({' OR '.join(service_conditions)})"
        
        result = self.db.execute(query, values, one_value=False, return_dict=True, fetch_all=True)
        return result[0]["total_count"] if result and len(result) > 0 else 0

    def get_pending_profiling_command(
        self, hostname: str, service_name: str, exclude_command_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Get pending profiling command for a specific host/service"""
        query = """
        SELECT command_id, command_type, combined_config, request_ids, status, created_at
        FROM ProfilingCommands
        WHERE hostname = %(hostname)s
          AND service_name = %(service_name)s
          AND status = 'pending'
        """

        values = {"hostname": hostname, "service_name": service_name}

        if exclude_command_id:
            query += " AND command_id != %(exclude_command_id)s::uuid"
            values["exclude_command_id"] = exclude_command_id

        query += " ORDER BY created_at DESC LIMIT 1"

        result = self.db.execute(query, values, one_value=True, return_dict=True)

        # Parse the combined_config JSON if it exists
        if result and result.get("combined_config"):
            try:
                if isinstance(result["combined_config"], str):
                    result["combined_config"] = json.loads(result["combined_config"])
            except json.JSONDecodeError:
                self.db.logger.warning(f"Failed to parse combined_config for command {result.get('command_id')}")
                result["combined_config"] = {}

        # Parse the request_ids array if it exists
        if result and result.get("request_ids"):
            try:
                if isinstance(result["request_ids"], str):
                    # PostgreSQL array format: {uuid1,uuid2,uuid3}
                    # Remove braces and split by comma
                    request_ids_str = result["request_ids"].strip("{}")
                    if request_ids_str:
                        result["request_ids"] = [uuid.strip() for uuid in request_ids_str.split(",")]
                    else:
                        result["request_ids"] = []
            except Exception:
                self.db.logger.warning(f"Failed to parse request_ids for command {result.get('command_id')}")
                result["request_ids"] = []

        return result if result else None

    def mark_profiling_command_sent(self, command_id: str, hostname: str) -> bool:
        """Mark a profiling command as sent to a host"""
        query = """
        UPDATE ProfilingCommands
        SET status = 'sent', sent_at = CURRENT_TIMESTAMP
        WHERE command_id = %(command_id)s::uuid AND hostname = %(hostname)s
        """

        values = {"command_id": command_id, "hostname": hostname}

        self.db.execute(query, values, has_value=False)
        return True

    def update_profiling_command_status(
        self,
        command_id: str,
        hostname: str,
        status: str,
        execution_time: Optional[int] = None,
        error_message: Optional[str] = None,
        results_path: Optional[str] = None,
    ) -> bool:
        """Update the status of a profiling command"""
        query = """
        UPDATE ProfilingCommands
        SET status = %(status)s,
            completed_at = CASE WHEN %(status)s IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END,
            execution_time = %(execution_time)s,
            error_message = %(error_message)s,
            results_path = %(results_path)s
        WHERE command_id = %(command_id)s::uuid AND hostname = %(hostname)s
        """

        values = {
            "command_id": command_id,
            "hostname": hostname,
            "status": status,
            "execution_time": execution_time,
            "error_message": error_message,
            "results_path": results_path,
        }

        self.db.execute(query, values, has_value=False)
        return True

    def get_profiling_command_by_hostname(
        self,
        hostname: str,
    ) -> Optional[Dict]:
        """Get the latest profiling command for a specific hostname"""
        query = """
        SELECT command_id, hostname, service_name, command_type, combined_config,
               request_ids, status, created_at, sent_at, completed_at
        FROM ProfilingCommands
        WHERE hostname = %(hostname)s
        ORDER BY created_at DESC
        LIMIT 1
        """

        values = {"hostname": hostname}
        result = self.db.execute(query, values, one_value=True, return_dict=True)

        # Parse the combined_config JSON if it exists
        if result and result.get("combined_config"):
            try:
                if isinstance(result["combined_config"], str):
                    result["combined_config"] = json.loads(result["combined_config"])
            except json.JSONDecodeError:
                self.db.logger.warning(f"Failed to parse combined_config for command {result.get('command_id')}")
                result["combined_config"] = {}

        if result and result.get("request_ids"):
            try:
                if isinstance(result["request_ids"], str):
                    # PostgreSQL array format: {uuid1,uuid2,uuid3}
                    # Remove braces and split by comma
                    request_ids_str = result["request_ids"].strip("{}")
                    if request_ids_str:
                        result["request_ids"] = [uuid.strip() for uuid in request_ids_str.split(",")]
                    else:
                        result["request_ids"] = []
            except Exception:
                self.db.logger.warning(f"Failed to parse request_ids for command {result.get('command_id')}")
                result["request_ids"] = []

        return result if result else None

    def validate_command_completion_eligibility(self, command_id: str, hostname: str) -> tuple[bool, str]:
        """
        Validate if a command can be completed for a specific hostname.
        The logic joins ProfilingCommands and ProfilingExecutions to guarantee the command id existed at some point.
        Returns (is_valid: bool, error_message: str).
        """
        query = """
        SELECT
            COALESCE(pc.command_id, pe.command_id) as command_id,
            pe.status as execution_status
        FROM
            ProfilingCommands pc
            FULL OUTER JOIN ProfilingExecutions pe ON pc.command_id = pe.command_id
            AND pc.hostname =  pe.hostname
        WHERE
            COALESCE(pc.command_id, pe.command_id) = %(command_id)s::uuid
            AND pe.hostname = %(hostname)s
        """

        values = {"command_id": command_id, "hostname": hostname}

        result = self.db.execute(query, values, one_value=True, return_dict=True)

        if result is None:
            return False, f"Command {command_id} not found for host {hostname}"

        execution_status = result.get("execution_status")
        if execution_status is None:
            return False, f"No execution record found for command {command_id} on host {hostname}"

        if execution_status != "assigned":
            return (
                False,
                f"Command {command_id} for host {hostname} is in status '{execution_status}', expected 'assigned'",
            )

        return True, ""

    def update_host_heartbeat(
        self,
        hostname: str,
        ip_address: str,
        service_name: str,
        status: str,
        last_command_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Update host heartbeat information (wrapper around upsert_host_heartbeat)"""
        self.upsert_host_heartbeat(
            hostname=hostname,
            ip_address=ip_address,
            service_name=service_name,
            last_command_id=last_command_id,
            status=status,
        )

    def _get_profiling_request_details(self, request_id: str) -> Optional[Dict]:
        """Get details of a specific profiling request"""
        query = """
        SELECT request_id, continuous, duration, frequency, profiling_mode, pids, target_hostnames, additional_args
        FROM ProfilingRequests
        WHERE request_id = %(request_id)s::uuid
        """

        values = {"request_id": request_id}
        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result if result else None

    def _build_combined_config(self, request_ids: List[str], hostname: str, service_name: str) -> Dict:
        """Build combined configuration from multiple profiling requests"""
        if not request_ids:
            return {}

        # Get all request details
        request_details = []
        for req_id in request_ids:
            details = self._get_profiling_request_details(req_id)
            if details:
                request_details.append(details)

        if not request_details:
            return {}

        # Use the most recent request's basic settings
        latest_request = request_details[-1]
        combined_config = {
            "continuous": latest_request.get("continuous", False),
            "duration": latest_request.get("duration", 60),
            "frequency": latest_request.get("frequency", 11),
            "profiling_mode": latest_request.get("profiling_mode", "cpu"),
        }

        # Merge PIDs from all requests that target this hostname
        all_pids = set()
        for req in request_details:
            if req.get("pids"):
                # Check if this request targets this hostname or all hostnames
                target_hostnames = req.get("target_hostnames")
                if not target_hostnames or hostname in target_hostnames:
                    all_pids.update(req["pids"])

        if all_pids:
            combined_config["pids"] = ",".join(map(str, sorted(all_pids)))

        # Merge additional_args from all requests
        merged_additional_args = {}
        for req in request_details:
            if req.get("additional_args"):
                # Parse JSON string if needed
                additional_args = req["additional_args"]
                if isinstance(additional_args, str):
                    try:
                        additional_args = json.loads(additional_args)
                    except json.JSONDecodeError:
                        continue
                if isinstance(additional_args, dict):
                    merged_additional_args.update(additional_args)

        if merged_additional_args:
            combined_config.update(merged_additional_args)  # Merge directly into combined_config

        return combined_config

    def get_adhoc_flamegraphs_metadata(
        self,
        service_id: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        hostname_filters: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve adhoc flamegraph metadata with optional filters.
        
        Args:
            service_id: ID of the service
            start_time: Optional filter for profiles after this time
            end_time: Optional filter for profiles before this time
            hostname_filters: Optional list of hostnames to filter by
            
        Returns:
            List of metadata dictionaries containing s3_key, hostname, perf_events, and start_time
        """
        conditions = ["service_id = %s"]
        params: List[Any] = [service_id]
        
        if start_time:
            conditions.append("start_time >= %s")
            params.append(start_time)
        
        if end_time:
            conditions.append("end_time <= %s")
            params.append(end_time)
        
        if hostname_filters:
            placeholders = ", ".join(["%s"] * len(hostname_filters))
            conditions.append(f"hostname IN ({placeholders})")
            params.extend(hostname_filters)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                s3_key,
                hostname,
                perf_events,
                start_time,
                file_size
            FROM AdhocFlamegraphMetadata
            WHERE {where_clause}
            ORDER BY start_time DESC
        """
        
        results = self.db.execute(query, tuple(params), one_value=False, fetch_all=True)
        
        if not results:
            return []
        
        return [
            {
                "s3_key": row[0],
                "hostname": row[1],
                "perf_events": row[2] if row[2] else [],
                "start_time": row[3].isoformat() if row[3] else None,
                "file_size": row[4] if len(row) > 4 else None,
            }
            for row in results
        ]
