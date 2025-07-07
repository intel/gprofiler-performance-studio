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
from typing import Dict, List, Optional, Set, Tuple, Union

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
        hash_meta = hashlib.md5(meta_json.encode("utf-8")).hexdigest()
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

    # Profiling Request Management Methods

    def create_profiling_request(
        self,
        service_name: str,
        duration: int = 60,
        frequency: int = 11,
        profiling_mode: str = "cpu",
        target_hostnames: Optional[List[str]] = None,
        pids: Optional[List[int]] = None,
        additional_args: Optional[Dict] = None,
        estimated_completion_time: Optional[datetime] = None
    ) -> str:
        """Create a new profiling request and return the request ID"""
        query = """
        INSERT INTO ProfilingRequests (
            service_name, duration, frequency, profiling_mode,
            target_hostnames, pids, additional_args, estimated_completion_time, service_id
        ) VALUES (
            %(service_name)s, %(duration)s, %(frequency)s, %(profiling_mode)s::ProfilingMode,
            %(target_hostnames)s, %(pids)s, %(additional_args)s, %(estimated_completion_time)s,
            (SELECT ID FROM Services WHERE name = %(service_name)s LIMIT 1)
        ) RETURNING request_id
        """

        values = {
            "service_name": service_name,
            "duration": duration,
            "frequency": frequency,
            "profiling_mode": profiling_mode,
            "target_hostnames": target_hostnames,
            "pids": pids,
            "additional_args": json.dumps(additional_args) if additional_args else None,
            "estimated_completion_time": estimated_completion_time
        }

        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return str(result["request_id"])

    def get_pending_profiling_request(
        self,
        hostname: str,
        service_name: str,
        exclude_command_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Get pending profiling request for a specific host/service"""
        query = """
        SELECT * FROM get_pending_profiling_request(
            %(hostname)s, %(service_name)s, %(exclude_command_id)s
        )
        """

        values = {
            "hostname": hostname,
            "service_name": service_name,
            "exclude_command_id": exclude_command_id
        }

        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result if result else None

    def mark_profiling_request_assigned(
        self,
        request_id: str,
        command_id: str,
        hostname: str
    ) -> bool:
        """Mark a profiling request as assigned to a host"""
        query = """
        SELECT mark_profiling_request_assigned(
            %(request_id)s::uuid, %(command_id)s::uuid, %(hostname)s
        ) as success
        """

        values = {
            "request_id": request_id,
            "command_id": command_id,
            "hostname": hostname
        }

        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result["success"] if result else False

    def update_profiling_request_status(
        self,
        request_id: str,
        status: str,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update the status of a profiling request"""
        query = """
        UPDATE ProfilingRequests
        SET status = %(status)s::ProfilingRequestStatus,
            completed_at = %(completed_at)s
        WHERE request_id = %(request_id)s::uuid
        """

        values = {
            "request_id": request_id,
            "status": status,
            "completed_at": completed_at
        }

        rows_affected = self.db.execute(query, values, has_value=False)

        # Also update execution record if exists
        if rows_affected > 0:
            exec_query = """
            UPDATE ProfilingExecutions
            SET status = %(status)s::ProfilingRequestStatus,
                completed_at = %(completed_at)s,
                error_message = %(error_message)s
            WHERE profiling_request_id = (
                SELECT ID FROM ProfilingRequests WHERE request_id = %(request_id)s::uuid
            )
            """
            exec_values = {
                "request_id": request_id,
                "status": status,
                "completed_at": completed_at,
                "error_message": error_message
            }
            self.db.execute(exec_query, exec_values, has_value=False)

        return rows_affected > 0

    def upsert_host_heartbeat(
        self,
        hostname: str,
        ip_address: str,
        service_name: str,
        last_command_id: Optional[str] = None,
        status: str = "active"
    ) -> None:
        """Update or insert host heartbeat information"""
        query = """
        SELECT upsert_host_heartbeat(
            %(hostname)s, %(ip_address)s::inet, %(service_name)s,
            %(last_command_id)s::uuid, %(status)s
        )
        """

        values = {
            "hostname": hostname,
            "ip_address": ip_address,
            "service_name": service_name,
            "last_command_id": last_command_id,
            "status": status
        }

        self.db.execute(query, values, has_value=False)

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

    def get_profiling_request_status(self, request_id: str) -> Optional[Dict]:
        """Get the current status of a profiling request"""
        query = """
        SELECT
            pr.request_id, pr.service_name, pr.status, pr.assigned_to_hostname,
            pr.created_at, pr.assigned_at, pr.completed_at, pr.estimated_completion_time,
            pe.command_id, pe.hostname as execution_hostname, pe.started_at,
            pe.completed_at as execution_completed_at, pe.error_message
        FROM ProfilingRequests pr
        LEFT JOIN ProfilingExecutions pe ON pr.ID = pe.profiling_request_id
        WHERE pr.request_id = %(request_id)s::uuid
        """

        values = {"request_id": request_id}
        result = self.db.execute(query, values, one_value=True, return_dict=True)
        return result if result else None
