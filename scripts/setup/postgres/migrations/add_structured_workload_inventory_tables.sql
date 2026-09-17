--
-- Copyright (C) 2023 Intel Corporation
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--    http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--

-- Normalized workload inventory tables.
--
-- These replace the per-host HostHeartbeats.containers JSONB snapshot with a
-- structured, queryable model. The heartbeat path writes the inventory into
-- these tables, and inventory reads (target resolution and workload status)
-- join/aggregate over them directly in SQL. The legacy JSONB column is removed
-- by drop_containers_jsonb_from_hostheartbeats.sql.

CREATE TABLE IF NOT EXISTS HeartbeatContainers (
    id bigserial PRIMARY KEY,
    host_id bigint NOT NULL REFERENCES HostHeartbeats (ID) ON DELETE CASCADE,
    container_id text NULL,
    container_name text NULL,
    runtime text NULL,
    namespace text NULL,
    pod_name text NULL,
    workload_name text NULL,
    workload_kind text NULL,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_heartbeat_container UNIQUE (host_id, container_id)
);

CREATE INDEX IF NOT EXISTS idx_hb_containers_host_id ON HeartbeatContainers (host_id);
CREATE INDEX IF NOT EXISTS idx_hb_containers_namespace ON HeartbeatContainers (namespace);
CREATE INDEX IF NOT EXISTS idx_hb_containers_pod_name ON HeartbeatContainers (pod_name);
CREATE INDEX IF NOT EXISTS idx_hb_containers_workload_name ON HeartbeatContainers (workload_name);

CREATE TABLE IF NOT EXISTS HeartbeatProcesses (
    id bigserial PRIMARY KEY,
    container_row_id bigint NOT NULL REFERENCES HeartbeatContainers (id) ON DELETE CASCADE,
    pid integer NOT NULL,
    process_name text NULL,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_heartbeat_process UNIQUE (container_row_id, pid)
);

CREATE INDEX IF NOT EXISTS idx_hb_processes_container_row_id ON HeartbeatProcesses (container_row_id);
CREATE INDEX IF NOT EXISTS idx_hb_processes_process_name ON HeartbeatProcesses (process_name);
