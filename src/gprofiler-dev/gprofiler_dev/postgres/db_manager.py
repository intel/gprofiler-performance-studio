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
from collections import defaultdict
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from gprofiler_dev.config import INSTANCE_RUNS_LRU_CACHE_LIMIT, PROFILER_PROCESSES_LRU_CACHE_LIMIT
from gprofiler_dev.lru_cache_impl import LRUCache
from gprofiler_dev.postgres import get_postgres_db
from gprofiler_dev.postgres.postgresdb import DBConflict
from gprofiler_dev.postgres.queries import AggregationSQLQueries, SQLQueries
from gprofiler_dev.postgres.schemas import AgentMetadata, CloudProvider, GetServiceResponse

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
        self.db = get_postgres_db()
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
        additional_args: Optional[Dict] = None,
    ) -> bool:
        """Save a profiling request with support for host-to-PID mapping"""
        # Store additional_args WITHOUT host_pid_mapping (keep that separate)
        clean_additional_args = additional_args.copy() if additional_args else {}

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
        last_command_id: Optional[str] = None,
        status: str = "active",
        heartbeat_timestamp: Optional[datetime] = None,
    ) -> bool:
        """Update or insert host heartbeat information using pure SQL"""
        if heartbeat_timestamp is None:
            heartbeat_timestamp = datetime.now()

        query = """
        INSERT INTO HostHeartbeats (
            hostname, ip_address, service_name, last_command_id,
            status, heartbeat_timestamp, created_at, updated_at
        ) VALUES (
            %(hostname)s, %(ip_address)s::inet, %(service_name)s,
            %(last_command_id)s::uuid, %(status)s::HostStatus,
            %(heartbeat_timestamp)s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (hostname, service_name)
        DO UPDATE SET
            ip_address = EXCLUDED.ip_address,
            last_command_id = EXCLUDED.last_command_id,
            status = EXCLUDED.status,
            heartbeat_timestamp = EXCLUDED.heartbeat_timestamp,
            updated_at = CURRENT_TIMESTAMP
        """

        values = {
            "hostname": hostname,
            "ip_address": ip_address,
            "service_name": service_name,
            "last_command_id": last_command_id,
            "status": status,
            "heartbeat_timestamp": heartbeat_timestamp,
        }

        self.db.execute(query, values, has_value=False)
        return True

    def get_host_heartbeat(self, hostname: str) -> Optional[Dict]:
        """Get the latest heartbeat information for a host"""
        query = """
        SELECT
            hostname, ip_address, service_name, last_command_id,
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

    def get_all_host_heartbeats(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict]:
        """Get all host heartbeat records with optional pagination"""
        query = """
        SELECT
            ID, hostname, ip_address, service_name, last_command_id,
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
