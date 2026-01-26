--
-- Copyright (C) 2025 Intel Corporation
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
-- MIGRATION: Add Dynamic Profiling Feature
-- ============================================================
-- This migration adds the dynamic profiling feature to existing
-- gProfiler Performance Studio deployments.
--
-- Features Added:
--   - Host heartbeat tracking
--   - Profiling request management
--   - Profiling command orchestration
--   - Profiling execution audit trail
--
-- Usage:
--   psql -U performance_studio -d performance_studio -f add_dynamic_profiling.up.sql
--
-- Rollback:
--   psql -U performance_studio -d performance_studio -f add_dynamic_profiling.down.sql
-- ============================================================

BEGIN;

-- ============================================================
-- STEP 1: Create ENUM Types
-- ============================================================

-- Profiling mode for different profiling types
DO $$ BEGIN
    CREATE TYPE ProfilingMode AS ENUM ('cpu', 'allocation', 'none');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Status for profiling requests
DO $$ BEGIN
    CREATE TYPE ProfilingRequestStatus AS ENUM ('pending', 'assigned', 'completed', 'failed', 'cancelled');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Status for profiling commands
DO $$ BEGIN
    CREATE TYPE CommandStatus AS ENUM ('pending', 'sent', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Status for host health
DO $$ BEGIN
    CREATE TYPE HostStatus AS ENUM ('active', 'idle', 'error', 'offline');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- ============================================================
-- STEP 2: Create Tables
-- ============================================================

-- Host Heartbeat Table - Tracks agent heartbeats and status
CREATE TABLE IF NOT EXISTS HostHeartbeats (
    ID bigserial PRIMARY KEY,
    hostname text NOT NULL,
    ip_address inet NOT NULL,
    service_name text NOT NULL,
    last_command_id uuid NULL,
    status HostStatus NOT NULL DEFAULT 'active',
    heartbeat_timestamp timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique_host_heartbeat" UNIQUE (hostname, service_name)
);

COMMENT ON TABLE HostHeartbeats IS 'Tracks agent heartbeats and availability for dynamic profiling';
COMMENT ON COLUMN HostHeartbeats.hostname IS 'Host identifier from agent';
COMMENT ON COLUMN HostHeartbeats.last_command_id IS 'Last command ID received by this host';
COMMENT ON COLUMN HostHeartbeats.heartbeat_timestamp IS 'Timestamp of last heartbeat from agent';


-- Profiling Requests Table - Stores user profiling requests
CREATE TABLE IF NOT EXISTS ProfilingRequests (
    ID bigserial PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    service_name text NOT NULL,
    request_type text NOT NULL CHECK (request_type IN ('start', 'stop')),
    continuous boolean NOT NULL DEFAULT false,
    duration integer NULL DEFAULT 60,
    frequency integer NULL DEFAULT 11,
    profiling_mode ProfilingMode NOT NULL DEFAULT 'cpu',
    target_hostnames text[] NOT NULL,
    pids integer[] NULL,
    stop_level text NULL DEFAULT 'process' CHECK (stop_level IN ('process', 'host')),
    additional_args jsonb NULL,
    status ProfilingRequestStatus NOT NULL DEFAULT 'pending',
    assigned_to_hostname text NULL,
    assigned_at timestamp NULL,
    completed_at timestamp NULL,
    estimated_completion_time timestamp NULL,
    service_id bigint NULL CONSTRAINT "fk_profiling_request_service" REFERENCES Services(ID),
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE ProfilingRequests IS 'Stores profiling requests from users/API';
COMMENT ON COLUMN ProfilingRequests.request_id IS 'Unique identifier for this profiling request';
COMMENT ON COLUMN ProfilingRequests.request_type IS 'Type of profiling request: start or stop';
COMMENT ON COLUMN ProfilingRequests.continuous IS 'Whether profiling should run continuously';
COMMENT ON COLUMN ProfilingRequests.target_hostnames IS 'Array of target hostnames for profiling';


-- Profiling Commands Table - Stores commands sent to agents
CREATE TABLE IF NOT EXISTS ProfilingCommands (
    ID bigserial PRIMARY KEY,
    command_id uuid NOT NULL,
    hostname text NOT NULL,
    service_name text NOT NULL,
    command_type text NOT NULL CHECK (command_type IN ('start', 'stop')),
    request_ids uuid[] NOT NULL,
    combined_config jsonb NULL,
    status CommandStatus NOT NULL DEFAULT 'pending',
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at timestamp NULL,
    completed_at timestamp NULL,
    execution_time integer NULL,
    error_message text NULL,
    results_path text NULL,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique_profiling_command_per_host" UNIQUE (hostname, service_name)
);

COMMENT ON TABLE ProfilingCommands IS 'Stores profiling commands to be executed by agents';
COMMENT ON COLUMN ProfilingCommands.command_id IS 'Unique identifier for this command';
COMMENT ON COLUMN ProfilingCommands.hostname IS 'Target hostname for command execution';
COMMENT ON COLUMN ProfilingCommands.request_ids IS 'Array of request IDs that generated this command';
COMMENT ON COLUMN ProfilingCommands.combined_config IS 'Merged configuration for multiple requests';


-- Profiling Executions Table - Audit trail for profiling executions
CREATE TABLE IF NOT EXISTS ProfilingExecutions (
    ID bigserial PRIMARY KEY,
    command_id uuid NOT NULL,
    hostname text NOT NULL,
    profiling_request_id uuid NOT NULL CONSTRAINT "fk_profiling_execution_request" REFERENCES ProfilingRequests(request_id),
    status ProfilingRequestStatus NOT NULL DEFAULT 'pending',
    started_at timestamp NULL,
    completed_at timestamp NULL,
    execution_time integer NULL,
    error_message text NULL,
    results_path text NULL,
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique_profiling_execution" UNIQUE (command_id, hostname)
);

COMMENT ON TABLE ProfilingExecutions IS 'Audit trail for profiling command executions';
COMMENT ON COLUMN ProfilingExecutions.command_id IS 'Reference to the command that was executed';
COMMENT ON COLUMN ProfilingExecutions.profiling_request_id IS 'Reference to the original profiling request';
COMMENT ON COLUMN ProfilingExecutions.results_path IS 'Path to profiling results (S3 or local)';


-- ============================================================
-- STEP 3: Create Indexes for Performance
-- ============================================================

-- Indexes for HostHeartbeats
CREATE INDEX IF NOT EXISTS idx_hostheartbeats_hostname ON HostHeartbeats (hostname);
CREATE INDEX IF NOT EXISTS idx_hostheartbeats_service_name ON HostHeartbeats (service_name);
CREATE INDEX IF NOT EXISTS idx_hostheartbeats_status ON HostHeartbeats (status);
CREATE INDEX IF NOT EXISTS idx_hostheartbeats_heartbeat_timestamp ON HostHeartbeats (heartbeat_timestamp);

-- Indexes for ProfilingRequests
CREATE INDEX IF NOT EXISTS idx_profilingrequests_request_id ON ProfilingRequests (request_id);
CREATE INDEX IF NOT EXISTS idx_profilingrequests_service_name ON ProfilingRequests (service_name);
CREATE INDEX IF NOT EXISTS idx_profilingrequests_status ON ProfilingRequests (status);
CREATE INDEX IF NOT EXISTS idx_profilingrequests_request_type ON ProfilingRequests (request_type);
CREATE INDEX IF NOT EXISTS idx_profilingrequests_created_at ON ProfilingRequests (created_at);

-- Indexes for ProfilingCommands
CREATE INDEX IF NOT EXISTS idx_profilingcommands_command_id ON ProfilingCommands (command_id);
CREATE INDEX IF NOT EXISTS idx_profilingcommands_hostname ON ProfilingCommands (hostname);
CREATE INDEX IF NOT EXISTS idx_profilingcommands_service_name ON ProfilingCommands (service_name);
CREATE INDEX IF NOT EXISTS idx_profilingcommands_status ON ProfilingCommands (status);
CREATE INDEX IF NOT EXISTS idx_profilingcommands_hostname_service ON ProfilingCommands (hostname, service_name);

-- Indexes for ProfilingExecutions
CREATE INDEX IF NOT EXISTS idx_profilingexecutions_command_id ON ProfilingExecutions (command_id);
CREATE INDEX IF NOT EXISTS idx_profilingexecutions_hostname ON ProfilingExecutions (hostname);
CREATE INDEX IF NOT EXISTS idx_profilingexecutions_profiling_request_id ON ProfilingExecutions (profiling_request_id);
CREATE INDEX IF NOT EXISTS idx_profilingexecutions_status ON ProfilingExecutions (status);


-- ============================================================
-- STEP 4: Verify Migration Success
-- ============================================================

DO $$
DECLARE
    table_count integer;
    index_count integer;
BEGIN
    -- Count new tables
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN ('hostheartbeats', 'profilingrequests', 'profilingcommands', 'profilingexecutions');
    
    -- Count new indexes
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE schemaname = 'public'
    AND indexname LIKE 'idx_%heartbeat%' OR indexname LIKE 'idx_%profiling%';
    
    RAISE NOTICE 'Migration completed successfully!';
    RAISE NOTICE 'Tables created: %', table_count;
    RAISE NOTICE 'Indexes created: %', index_count;
    
    IF table_count < 4 THEN
        RAISE EXCEPTION 'Migration failed: Expected 4 tables, found %', table_count;
    END IF;
END $$;

COMMIT;

-- ============================================================
-- Migration Complete
-- ============================================================
-- The dynamic profiling feature has been successfully added.
-- New tables: HostHeartbeats, ProfilingRequests, ProfilingCommands, ProfilingExecutions
-- New types: ProfilingMode, ProfilingRequestStatus, CommandStatus, HostStatus
-- ============================================================

