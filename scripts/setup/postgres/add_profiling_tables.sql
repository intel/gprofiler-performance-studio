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

-- Migration script to add profiling request and heartbeat tables

-- Create enum for profiling modes
CREATE TYPE ProfilingMode AS ENUM ('cpu', 'allocation', 'none');

-- Create enum for profiling request status
CREATE TYPE ProfilingRequestStatus AS ENUM ('pending', 'assigned', 'in_progress', 'completed', 'failed', 'cancelled');

-- Create enum for host status
CREATE TYPE HostStatus AS ENUM ('active', 'idle', 'error', 'offline');

-- Table for storing profiling requests
CREATE TABLE ProfilingRequests (
    ID bigserial PRIMARY KEY,
    request_id uuid UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    service_name text NOT NULL,
    duration integer DEFAULT 60 CHECK (duration > 0),
    frequency integer DEFAULT 11 CHECK (frequency > 0),
    profiling_mode ProfilingMode DEFAULT 'cpu',
    target_hostnames text[], -- Array of target hostnames
    pids integer[], -- Array of target PIDs
    additional_args jsonb, -- Store additional arguments as JSON
    status ProfilingRequestStatus DEFAULT 'pending',
    assigned_to_hostname text, -- Which host is executing this request
    assigned_command_id uuid, -- Command ID for tracking execution
    created_at timestamp DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP,
    assigned_at timestamp,
    completed_at timestamp,
    estimated_completion_time timestamp,

    -- Foreign key to services table if it exists
    service_id bigint CONSTRAINT "profiling_request_service_fk" REFERENCES Services(ID) ON DELETE CASCADE
);

-- Table for storing host heartbeats
CREATE TABLE HostHeartbeats (
    ID bigserial PRIMARY KEY,
    hostname text NOT NULL,
    ip_address inet NOT NULL,
    service_name text NOT NULL,
    last_command_id uuid, -- Last profiling command executed
    status HostStatus DEFAULT 'active',
    heartbeat_timestamp timestamp DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to services table if it exists
    service_id bigint CONSTRAINT "heartbeat_service_fk" REFERENCES Services(ID) ON DELETE CASCADE,

    -- Ensure one heartbeat record per hostname (upsert pattern)
    CONSTRAINT unique_hostname UNIQUE (hostname)
);

-- Table for tracking profiling command executions
CREATE TABLE ProfilingExecutions (
    ID bigserial PRIMARY KEY,
    profiling_request_id bigint NOT NULL CONSTRAINT "execution_request_fk" REFERENCES ProfilingRequests(ID) ON DELETE CASCADE,
    command_id uuid UNIQUE NOT NULL,
    hostname text NOT NULL,
    started_at timestamp DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp,
    status ProfilingRequestStatus DEFAULT 'in_progress',
    result_data jsonb, -- Store execution results/logs
    error_message text,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for better query performance
CREATE INDEX idx_profiling_requests_service_name ON ProfilingRequests(service_name);
CREATE INDEX idx_profiling_requests_status ON ProfilingRequests(status);
CREATE INDEX idx_profiling_requests_target_hostnames ON ProfilingRequests USING GIN(target_hostnames);
CREATE INDEX idx_profiling_requests_created_at ON ProfilingRequests(created_at);
CREATE INDEX idx_profiling_requests_assigned_hostname ON ProfilingRequests(assigned_to_hostname);

CREATE INDEX idx_host_heartbeats_hostname ON HostHeartbeats(hostname);
CREATE INDEX idx_host_heartbeats_service_name ON HostHeartbeats(service_name);
CREATE INDEX idx_host_heartbeats_status ON HostHeartbeats(status);
CREATE INDEX idx_host_heartbeats_heartbeat_timestamp ON HostHeartbeats(heartbeat_timestamp);

CREATE INDEX idx_profiling_executions_request_id ON ProfilingExecutions(profiling_request_id);
CREATE INDEX idx_profiling_executions_command_id ON ProfilingExecutions(command_id);
CREATE INDEX idx_profiling_executions_hostname ON ProfilingExecutions(hostname);
CREATE INDEX idx_profiling_executions_status ON ProfilingExecutions(status);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update updated_at timestamps
CREATE TRIGGER update_profiling_requests_updated_at
    BEFORE UPDATE ON ProfilingRequests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_host_heartbeats_updated_at
    BEFORE UPDATE ON HostHeartbeats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_profiling_executions_updated_at
    BEFORE UPDATE ON ProfilingExecutions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to get pending profiling requests for a host/service
CREATE OR REPLACE FUNCTION get_pending_profiling_request(
    p_hostname text,
    p_service_name text,
    p_exclude_command_id uuid DEFAULT NULL
)
RETURNS TABLE(
    request_id uuid,
    service_name text,
    duration integer,
    frequency integer,
    profiling_mode text,
    target_hostnames text[],
    pids integer[],
    additional_args jsonb,
    created_at timestamp,
    estimated_completion_time timestamp
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        pr.request_id,
        pr.service_name,
        pr.duration,
        pr.frequency,
        pr.profiling_mode::text,
        pr.target_hostnames,
        pr.pids,
        pr.additional_args,
        pr.created_at,
        pr.estimated_completion_time
    FROM ProfilingRequests pr
    WHERE pr.status = 'pending'
      AND pr.service_name = p_service_name
      AND (
          pr.target_hostnames IS NULL
          OR p_hostname = ANY(pr.target_hostnames)
      )
      AND (
          p_exclude_command_id IS NULL
          OR pr.assigned_command_id != p_exclude_command_id
      )
    ORDER BY pr.created_at ASC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to mark profiling request as assigned
CREATE OR REPLACE FUNCTION mark_profiling_request_assigned(
    p_request_id uuid,
    p_command_id uuid,
    p_hostname text
)
RETURNS boolean AS $$
DECLARE
    rows_updated integer;
BEGIN
    UPDATE ProfilingRequests
    SET
        status = 'assigned',
        assigned_to_hostname = p_hostname,
        assigned_command_id = p_command_id,
        assigned_at = CURRENT_TIMESTAMP
    WHERE request_id = p_request_id
      AND status = 'pending';

    GET DIAGNOSTICS rows_updated = ROW_COUNT;

    -- Insert execution record
    IF rows_updated > 0 THEN
        INSERT INTO ProfilingExecutions (
            profiling_request_id,
            command_id,
            hostname,
            status
        ) SELECT
            pr.ID,
            p_command_id,
            p_hostname,
            'assigned'
        FROM ProfilingRequests pr
        WHERE pr.request_id = p_request_id;

        RETURN true;
    END IF;

    RETURN false;
END;
$$ LANGUAGE plpgsql;

-- Function to upsert host heartbeat
CREATE OR REPLACE FUNCTION upsert_host_heartbeat(
    p_hostname text,
    p_ip_address inet,
    p_service_name text,
    p_last_command_id uuid DEFAULT NULL,
    p_status text DEFAULT 'active'
)
RETURNS void AS $$
BEGIN
    INSERT INTO HostHeartbeats (
        hostname,
        ip_address,
        service_name,
        last_command_id,
        status,
        service_id
    ) VALUES (
        p_hostname,
        p_ip_address,
        p_service_name,
        p_last_command_id,
        p_status::HostStatus,
        (SELECT ID FROM Services WHERE name = p_service_name LIMIT 1)
    )
    ON CONFLICT (hostname)
    DO UPDATE SET
        ip_address = EXCLUDED.ip_address,
        service_name = EXCLUDED.service_name,
        last_command_id = EXCLUDED.last_command_id,
        status = EXCLUDED.status,
        heartbeat_timestamp = CURRENT_TIMESTAMP,
        service_id = (SELECT ID FROM Services WHERE name = EXCLUDED.service_name LIMIT 1);
END;
$$ LANGUAGE plpgsql;
