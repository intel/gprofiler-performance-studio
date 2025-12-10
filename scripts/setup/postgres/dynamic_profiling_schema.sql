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

-- ============================================================
-- DYNAMIC PROFILING DATA MODEL
-- ============================================================
-- This schema supports dynamic profiling capabilities that allow
-- profiling requests at various hierarchy levels (service, job, namespace)
-- to be mapped to specific host-level commands while maintaining
-- sub-second heartbeat response times for 165k QPM.
--
-- References: 
-- https://docs.google.com/document/d/1iwA_NN1YKDBqfig95Qevw0HcSCqgu7_ya8PGuCksCPc/edit
-- ============================================================


-- ============================================================
-- ENUMS AND TYPES
-- ============================================================

-- Command types for profiling operations
CREATE TYPE CommandType AS ENUM (
    'start',
    'stop',
    'reconfigure'
);

-- Status for profiling requests
CREATE TYPE ProfilingStatus AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'failed',
    'cancelled'
);

-- Profiling modes
CREATE TYPE ProfilingMode AS ENUM (
    'cpu',
    'memory',
    'allocation',
    'native'
);


-- ============================================================
-- CORE TABLES
-- ============================================================

-- ProfilingRequest: Stores profiling requests from API calls
CREATE TABLE ProfilingRequest (
    ID bigserial PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    
    -- Target specification
    service_name text,
    job_name text,
    namespace text,
    pod_name text,
    host_name text,
    process_id bigint,
    
    -- Profiling configuration
    profiling_mode ProfilingMode NOT NULL DEFAULT 'cpu',
    duration_seconds integer NOT NULL CONSTRAINT "positive duration" CHECK (duration_seconds > 0),
    sample_rate integer NOT NULL DEFAULT 100 CONSTRAINT "valid sample rate" CHECK (sample_rate > 0 AND sample_rate <= 1000),
    
    -- Execution configuration
    executors text[] DEFAULT ARRAY[]::text[],
    
    -- Request metadata
    start_time timestamp NOT NULL,
    stop_time timestamp,
    mode text,
    
    -- Status tracking
    status ProfilingStatus NOT NULL DEFAULT 'pending',
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign keys
    profiler_token_id bigint CONSTRAINT "request must have valid token" REFERENCES ProfilerTokens,
    
    -- Constraints
    CONSTRAINT "at_least_one_target" CHECK (
        service_name IS NOT NULL OR 
        job_name IS NOT NULL OR 
        namespace IS NOT NULL OR 
        pod_name IS NOT NULL OR 
        host_name IS NOT NULL OR 
        process_id IS NOT NULL
    )
);

-- Indexes for ProfilingRequest
CREATE INDEX profiling_request_status_idx ON ProfilingRequest(status);
CREATE INDEX profiling_request_created_at_idx ON ProfilingRequest(created_at);
CREATE INDEX profiling_request_service_idx ON ProfilingRequest(service_name) WHERE service_name IS NOT NULL;
CREATE INDEX profiling_request_namespace_idx ON ProfilingRequest(namespace) WHERE namespace IS NOT NULL;
CREATE INDEX profiling_request_host_idx ON ProfilingRequest(host_name) WHERE host_name IS NOT NULL;


-- ProfilingCommand: Profiling commands sent to agents (scale in future)
CREATE TABLE ProfilingCommand (
    ID bigserial PRIMARY KEY,
    command_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    
    -- Link to original request
    profiling_request_id bigint NOT NULL CONSTRAINT "command must belong to request" REFERENCES ProfilingRequest,
    
    -- Host targeting
    host_id text NOT NULL,  -- Index key for fast lookup
    target_containers text[] DEFAULT ARRAY[]::text[],
    target_processes bigint[] DEFAULT ARRAY[]::bigint[],
    
    -- Command details
    command_type CommandType NOT NULL,
    command_args jsonb NOT NULL DEFAULT '{}'::jsonb,
    
    -- Command lifecycle
    command_json text,  -- Full command serialized for agent
    sent_at timestamp,
    completed_at timestamp,
    status ProfilingStatus NOT NULL DEFAULT 'pending',
    
    -- Timestamps
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for ProfilingCommand
CREATE INDEX profiling_command_request_idx ON ProfilingCommand(profiling_request_id);
CREATE INDEX profiling_command_host_idx ON ProfilingCommand(host_id);
CREATE INDEX profiling_command_status_idx ON ProfilingCommand(status);
CREATE INDEX profiling_command_sent_at_idx ON ProfilingCommand(sent_at);


-- HostHeartbeats: Tracks available host status, details and last seen info
CREATE TABLE HostHeartbeats (
    ID bigserial PRIMARY KEY,
    
    -- Host identification
    host_id text NOT NULL UNIQUE,
    service_name text,
    host_name text NOT NULL,
    host_ip inet,
    
    -- Environment details
    namespace text,
    pod_name text,
    containers text[] DEFAULT ARRAY[]::text[],
    
    -- Resource tracking
    workloads jsonb DEFAULT '{}'::jsonb,  -- Running workloads/jobs
    jobs text[] DEFAULT ARRAY[]::text[],
    
    -- Agent info
    executors text[] DEFAULT ARRAY[]::text[],
    
    -- Heartbeat tracking (critical for 165k QPM with sub-second response)
    timestamp_first_seen timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    timestamp_last_seen timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_command_id uuid,
    
    -- Metadata
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Critical indexes for heartbeat performance (165k QPM requirement)
CREATE INDEX host_heartbeats_host_id_idx ON HostHeartbeats(host_id);
CREATE INDEX host_heartbeats_last_seen_idx ON HostHeartbeats(timestamp_last_seen);
CREATE INDEX host_heartbeats_service_idx ON HostHeartbeats(service_name) WHERE service_name IS NOT NULL;
CREATE INDEX host_heartbeats_namespace_idx ON HostHeartbeats(namespace) WHERE namespace IS NOT NULL;


-- ProfilingExecutions: Execution history for audit trail
CREATE TABLE ProfilingExecutions (
    ID bigserial PRIMARY KEY,
    execution_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    
    -- Links
    profiling_request_id bigint NOT NULL CONSTRAINT "execution must belong to request" REFERENCES ProfilingRequest,
    profiling_command_id bigint CONSTRAINT "execution may link to command" REFERENCES ProfilingCommand,
    
    -- Execution details
    host_name text NOT NULL,
    target_containers text[] DEFAULT ARRAY[]::text[],
    target_processes bigint[] DEFAULT ARRAY[]::bigint[],
    
    -- Command tracking
    command_type CommandType NOT NULL,
    
    -- Execution lifecycle
    started_at timestamp NOT NULL,
    completed_at timestamp,
    status ProfilingStatus NOT NULL,
    
    -- Timestamps
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for ProfilingExecutions
CREATE INDEX profiling_executions_request_idx ON ProfilingExecutions(profiling_request_id);
CREATE INDEX profiling_executions_command_idx ON ProfilingExecutions(profiling_command_id) WHERE profiling_command_id IS NOT NULL;
CREATE INDEX profiling_executions_host_idx ON ProfilingExecutions(host_name);
CREATE INDEX profiling_executions_status_idx ON ProfilingExecutions(status);
CREATE INDEX profiling_executions_started_at_idx ON ProfilingExecutions(started_at);


-- ============================================================
-- HIERARCHICAL MAPPING TABLES
-- ============================================================
-- These tables denormalize hierarchical mappings for faster 
-- query performance when mapping requests to hosts.
-- ============================================================

-- NamespaceServices: Maps namespaces to services
CREATE TABLE NamespaceServices (
    ID bigserial PRIMARY KEY,
    namespace text NOT NULL,
    service_name text NOT NULL,
    
    -- Metadata
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT "unique namespace service mapping" UNIQUE (namespace, service_name)
);

CREATE INDEX namespace_services_namespace_idx ON NamespaceServices(namespace);
CREATE INDEX namespace_services_service_idx ON NamespaceServices(service_name);


-- ServiceContainers: Maps services to containers
CREATE TABLE ServiceContainers (
    ID bigserial PRIMARY KEY,
    service_name text NOT NULL,
    container_name text NOT NULL,
    
    -- Metadata
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT "unique service container mapping" UNIQUE (service_name, container_name)
);

CREATE INDEX service_containers_service_idx ON ServiceContainers(service_name);
CREATE INDEX service_containers_container_idx ON ServiceContainers(container_name);


-- JobContainers: Maps jobs to containers
CREATE TABLE JobContainers (
    ID bigserial PRIMARY KEY,
    job_name text NOT NULL,
    container_name text NOT NULL,
    
    -- Metadata
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT "unique job container mapping" UNIQUE (job_name, container_name)
);

CREATE INDEX job_containers_job_idx ON JobContainers(job_name);
CREATE INDEX job_containers_container_idx ON JobContainers(container_name);


-- ContainerProcesses: Maps containers to processes
CREATE TABLE ContainerProcesses (
    ID bigserial PRIMARY KEY,
    container_name text NOT NULL,
    process_id bigint NOT NULL,
    process_name text,
    
    -- Metadata
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT "unique container process mapping" UNIQUE (container_name, process_id)
);

CREATE INDEX container_processes_container_idx ON ContainerProcesses(container_name);
CREATE INDEX container_processes_process_idx ON ContainerProcesses(process_id);


-- ContainersHosts: Maps containers to hosts
CREATE TABLE ContainersHosts (
    ID bigserial PRIMARY KEY,
    container_name text NOT NULL,
    host_id text NOT NULL,
    host_name text NOT NULL,
    
    -- Metadata
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT "unique container host mapping" UNIQUE (container_name, host_id)
);

CREATE INDEX containers_hosts_container_idx ON ContainersHosts(container_name);
CREATE INDEX containers_hosts_host_id_idx ON ContainersHosts(host_id);
CREATE INDEX containers_hosts_host_name_idx ON ContainersHosts(host_name);


-- ProcessesHosts: Maps processes to hosts
CREATE TABLE ProcessesHosts (
    ID bigserial PRIMARY KEY,
    process_id bigint NOT NULL,
    host_id text NOT NULL,
    host_name text NOT NULL,
    
    -- Metadata
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT "unique process host mapping" UNIQUE (process_id, host_id)
);

CREATE INDEX processes_hosts_process_idx ON ProcessesHosts(process_id);
CREATE INDEX processes_hosts_host_id_idx ON ProcessesHosts(host_id);
CREATE INDEX processes_hosts_host_name_idx ON ProcessesHosts(host_name);


-- ============================================================
-- TRIGGERS FOR UPDATED_AT
-- ============================================================

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to all tables with updated_at column
CREATE TRIGGER update_profiling_request_updated_at BEFORE UPDATE ON ProfilingRequest
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_profiling_command_updated_at BEFORE UPDATE ON ProfilingCommand
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_host_heartbeats_updated_at BEFORE UPDATE ON HostHeartbeats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_profiling_executions_updated_at BEFORE UPDATE ON ProfilingExecutions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_namespace_services_updated_at BEFORE UPDATE ON NamespaceServices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_service_containers_updated_at BEFORE UPDATE ON ServiceContainers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_job_containers_updated_at BEFORE UPDATE ON JobContainers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_container_processes_updated_at BEFORE UPDATE ON ContainerProcesses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_containers_hosts_updated_at BEFORE UPDATE ON ContainersHosts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_processes_hosts_updated_at BEFORE UPDATE ON ProcessesHosts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE ProfilingRequest IS 'Stores profiling requests from API calls with target specification at various hierarchy levels (service, job, namespace)';
COMMENT ON TABLE ProfilingCommand IS 'Profiling commands sent to agents/hosts (scale in future). Maps high-level requests to specific host-level commands.';
COMMENT ON TABLE HostHeartbeats IS 'Tracks available host status, details and last seen info. Optimized for 165k QPM with sub-second response times.';
COMMENT ON TABLE ProfilingExecutions IS 'Execution history for audit trail. Tracks actual execution of profiling commands on hosts.';
COMMENT ON TABLE NamespaceServices IS 'Denormalized mapping of namespaces to services for faster query performance';
COMMENT ON TABLE ServiceContainers IS 'Denormalized mapping of services to containers for faster query performance';
COMMENT ON TABLE JobContainers IS 'Denormalized mapping of jobs to containers for faster query performance';
COMMENT ON TABLE ContainerProcesses IS 'Denormalized mapping of containers to processes for faster query performance';
COMMENT ON TABLE ContainersHosts IS 'Denormalized mapping of containers to hosts for faster query performance';
COMMENT ON TABLE ProcessesHosts IS 'Denormalized mapping of processes to hosts for faster query performance';




