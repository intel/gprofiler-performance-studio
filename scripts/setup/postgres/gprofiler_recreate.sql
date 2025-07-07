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

-- TYPES

CREATE TYPE providername AS ENUM (
    'AWS',
    'GCP',
    'Azure',
    'Unknown');


CREATE TABLE InstanceCloudMetadata (
    ID bigserial PRIMARY KEY,
    meta jsonb NOT NULL,
    hash_meta text UNIQUE NOT NULL,
    ts timestamp DEFAULT CURRENT_TIMESTAMP
);



CREATE TABLE Libcs (
    ID bigserial PRIMARY KEY,
    type text NOT NULL,
    version text NOT NULL,
    ts timestamp DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique libc" UNIQUE (type, version)
);


CREATE TABLE MachineTypes (
    ID bigserial PRIMARY KEY,
    provider ProviderName NOT NULL,
    name text NOT NULL,
    ts timestamp DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique machine type" UNIQUE (provider, name)
);


CREATE TABLE OSes (
    ID bigserial PRIMARY KEY,
    system_name text NOT NULL,
    "name" text NOT NULL,
    "release" text NOT NULL,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique OS" UNIQUE (system_name, name, release)
);


CREATE TABLE ProfilerVersions (
    ID bigserial PRIMARY KEY,
    major bigint NOT NULL CONSTRAINT "non-negative major number" CHECK(major >= 0),
    minor bigint NOT NULL CONSTRAINT "non-negative minor number" CHECK(minor >= 0),
    patch bigint NOT NULL CONSTRAINT "non-negative patch number" CHECK(patch >= 0),
    weight bigint NOT NULL,
    name text,
    ts timestamp DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique profiler_version" UNIQUE (major, minor, patch)
);


CREATE TYPE ServiceType AS ENUM ('instances', 'pods', 'containers');
CREATE TYPE EnvType AS ENUM ('instances', 'k8s', 'containers', 'ecs');


CREATE TABLE Instances (
    ID bigserial PRIMARY KEY,
    mac macaddr NOT NULL,
    identifier text,
    ts timestamp DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX "unique instance" ON instances USING btree (mac, identifier);
CREATE UNIQUE INDEX "unique instance (no identifier)" ON public.instances USING btree (mac, ((identifier IS NULL))) WHERE (identifier IS NULL);


CREATE TABLE Kernels (
    ID bigserial PRIMARY KEY,
    os bigint NOT NULL CONSTRAINT "kernel must belong to a valid OS" REFERENCES OSes,
    release text NOT NULL,
    version text NOT NULL,
    hardware_type text NOT NULL,
    ts timestamp DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique kernel" UNIQUE (os, release, version, hardware_type)
);


CREATE TABLE Machines (
    ID bigserial PRIMARY KEY,
    type bigint NOT NULL CONSTRAINT "type must belong to a valid MachineType" REFERENCES MachineTypes,
    processors bigint NOT NULL CONSTRAINT "positive number of processors" CHECK(processors > 0),
    memory bigint NOT NULL CONSTRAINT "positive memory" CHECK(memory > 0),
    ts timestamp DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique machine" UNIQUE (type, processors, memory)
);


CREATE TYPE RunMode AS ENUM ('k8s', 'container', 'standalone_executable', 'local_python');

CREATE TABLE ProfilerRunEnvironments (
    ID bigserial PRIMARY KEY,
    python_version text NOT NULL,
    libc bigint NOT NULL CONSTRAINT "profiler_run_environment must belong to a valid libc" REFERENCES Libcs,
    run_mode RunMode NOT NULL,
    ts timestamp DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique profiler_run_environment" UNIQUE (python_version, libc, run_mode)
);


CREATE TABLE ProfilerTokens (
    ID bigserial PRIMARY KEY,
    "token" text NOT NULL,
    disabled timestamp NULL,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT profilertokens_token_key UNIQUE (token)
);


CREATE TABLE Services (
    ID bigserial PRIMARY KEY,
    "name" text NOT NULL,
    hidden bool NOT NULL DEFAULT false,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    service_type servicetype NOT NULL DEFAULT 'instances'::servicetype,
    cluster_id bigint CONSTRAINT "service must belong to a valid cluster-service" REFERENCES Services,
    is_cluster bool NOT NULL DEFAULT false,
    env_type envtype NULL,
    profiler_sample_threshold float8 NULL,
    CONSTRAINT "unique service" UNIQUE (name)
);

CREATE INDEX services_hidden_idx ON services USING btree (hidden);


CREATE TABLE TokenAssociations (
    ID bigserial PRIMARY KEY,
    token bigint NOT NULL CONSTRAINT "token_association must belong to a valid profiler" REFERENCES ProfilerTokens,
    service_name text NOT NULL,
    service bigint UNIQUE NOT NULL CONSTRAINT "token_association must belong to a valid service" REFERENCES Services,
    last_seen timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tokenassociations_service_key UNIQUE (service),
    CONSTRAINT "unique token_association" UNIQUE (token, service_name)
);


CREATE OR REPLACE RULE ServicesDeleteProtection
    AS ON DELETE TO Services DO INSTEAD
    UPDATE Services SET hidden = true WHERE Services.ID = OLD.ID;


CREATE TABLE InstanceRuns (
    ID bigserial PRIMARY KEY,
    instance bigint NOT NULL CONSTRAINT "instance_run must belong to a valid instance" REFERENCES Instances,
    boot_time timestamp NOT NULL,
    machine bigint NOT NULL CONSTRAINT "instance_run must have a valid machine" REFERENCES Machines,
    kernel bigint NOT NULL CONSTRAINT "instance_run must have a valid kernel" REFERENCES Kernels,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    metadata bigint CONSTRAINT "instance_run must have a valid metadata" REFERENCES InstanceCloudMetadata,
    CONSTRAINT "unique instance_run" UNIQUE (instance, boot_time)
);

CREATE INDEX instanceruns_instance_idx ON instanceruns USING btree (instance);
CREATE INDEX instanceruns_kernel_idx ON instanceruns USING btree (kernel);
CREATE INDEX instanceruns_machine_idx ON instanceruns USING btree (machine);
CREATE INDEX instanceruns_metadata_idx ON instanceruns USING btree (metadata);


CREATE TABLE ProfilerFilters
(
    ID bigserial PRIMARY KEY,
    service bigint NOT NULL CONSTRAINT "ProfilerFilter must belong to a valid service" REFERENCES Services,
    filter_content jsonb NOT NULL,
    ts timestamp DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ProfilerProcesses (
    ID bigserial PRIMARY KEY,
    instance_run bigint NOT NULL CONSTRAINT "profiler_process must belong to a valid instance_run" REFERENCES InstanceRuns,
    profiler_version bigint NOT NULL CONSTRAINT "profiler_process must have a valid profiler_version" REFERENCES ProfilerVersions,
    profiler_run_environment bigint NOT NULL CONSTRAINT "profiler_process must have a valid profiler_run_environment" REFERENCES ProfilerRunEnvironments,
    pid bigint NOT NULL CONSTRAINT "non-negative pid" CHECK(pid >= 0),
    spawn_local_time timestamp NOT NULL,
    public_ip text NOT NULL,
    private_ip text NOT NULL,
    hostname text NOT NULL,
    service bigint NOT NULL CONSTRAINT "profiler_process must belong to a valid service" REFERENCES Services,
    last_seen timestamp DEFAULT CURRENT_TIMESTAMP CONSTRAINT "last_seen must be after ts" CHECK(last_seen >= ts),
    spawn_uptime int8 NOT NULL,
    run_arguments jsonb NOT NULL,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique profiler_process" UNIQUE (instance_run, profiler_version, pid, spawn_local_time)
);
CREATE INDEX profilerprocesses_last_seen_idx ON profilerprocesses USING btree (last_seen);
CREATE INDEX profilerprocesses_profiler_run_environment_idx ON profilerprocesses USING btree (profiler_run_environment);
CREATE INDEX profilerprocesses_profiler_version_idx ON profilerprocesses USING btree (profiler_version);
CREATE INDEX profilerprocesses_service_idx ON profilerprocesses USING btree (service);
CREATE INDEX profilerprocesses_service_last_seen_idx ON profilerprocesses USING btree (service, last_seen DESC);



CREATE TABLE ProfilerServiceHourlyUsages (
    ID bigserial PRIMARY KEY,
    service bigint NOT NULL CONSTRAINT "profiler_service_hourly_usage must belong to a valid service" REFERENCES Services,
    start_date timestamp NOT NULL CONSTRAINT "start_date must be a whole hour" CHECK(date_trunc('hour', start_date) = start_date),
    running_hours float8 NOT NULL,
    core_hours float8 NOT NULL,
    lowest_agent_version bigint NOT NULL CONSTRAINT "prof_service_hourly_usage must have a valid profiler_version" REFERENCES ProfilerVersions,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "unique profiler_service_hourly_usage" UNIQUE (service, start_date)
);

CREATE TABLE ProfilerSnapshots (
    ID bigserial PRIMARY KEY,
    service bigint NOT NULL CONSTRAINT "profiler_snapshot must belong to a valid service" REFERENCES Services,
    start_time timestamp NULL,
    end_time timestamp NULL CONSTRAINT "end_date must be after start_date" CHECK(end_time > start_time),
    hidden bool NULL DEFAULT false,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP,
    filter_content jsonb NULL
);

CREATE TABLE MinesweeperFrames (
    ID bigserial PRIMARY KEY,
    snapshot bigint NOT NULL CONSTRAINT "minesweeper_frame must belong to a valid snapshot" REFERENCES ProfilerSnapshots,
    "level" int8 NULL,
    "start" int8 NULL,
    duration int8 NULL,
    ts timestamp NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE OR REPLACE FUNCTION calc_profiler_usage_history(start_date timestamp without time zone, end_date timestamp without time zone, interval_s bigint, max_iterations bigint DEFAULT 3)
 RETURNS TABLE(start_time timestamp without time zone, end_time timestamp without time zone, service bigint, running_hours double precision, core_hours double precision, lowest_agent_version bigint)
 LANGUAGE plpgsql
AS $function$
    BEGIN
        RETURN QUERY
            WITH TimeSeries AS (
                SELECT
                   (start_date + interval '1 seconds' * interval_s * generate_series) AS start_time,
                   (start_date + interval '1 seconds' * interval_s * (generate_series + 1)) AS end_time
                FROM GENERATE_SERIES(0, LEAST(max_iterations, CAST (EXTRACT (EPOCH FROM end_date - start_date) AS bigint) / interval_s) - 1)
            ), RelevantProfilerProcesses AS (
                SELECT ProfilerProcesses.service, ProfilerProcesses.instance_run, ProfilerProcesses.last_seen, ProfilerProcesses.profiler_version, ProfilerProcesses.ts as first_seen
                FROM ProfilerProcesses
                INNER JOIN Services ON Services.ID = ProfilerProcesses.service
                WHERE Services.cluster_id IS NULL
                    AND ProfilerProcesses.last_seen >= start_date
                    AND ProfilerProcesses.ts < end_date
            ), TimeSeriesProcesess AS (
                SELECT
                    TimeSeries.start_time,
                    TimeSeries.end_time,
                    RelevantProfilerProcesses.service,
                    Machines.processors,
                    EXTRACT(EPOCH FROM (LEAST(RelevantProfilerProcesses.last_seen, TimeSeries.end_time) -
                                        GREATEST(RelevantProfilerProcesses.first_seen, TimeSeries.start_time))) AS duration,
                    Machines.type AS machine_type,
                    InstanceRuns.metadata,
                    ProfilerVersions.ID as version_id,
                    ProfilerVersions.weight
                FROM RelevantProfilerProcesses
                INNER JOIN TimeSeries ON RelevantProfilerProcesses.last_seen >= TimeSeries.start_time
                    AND RelevantProfilerProcesses.first_seen < TimeSeries.end_time
                INNER JOIN InstanceRuns ON InstanceRuns.ID = RelevantProfilerProcesses.instance_run
                INNER JOIN Machines ON Machines.ID = InstanceRuns.machine
                INNER JOIN ProfilerVersions ON ProfilerVersions.ID = RelevantProfilerProcesses.profiler_version
            )
            SELECT
                TimeSeriesProcesess.start_time,
                TimeSeriesProcesess.end_time,
                TimeSeriesProcesess.service,
                CAST(SUM(TimeSeriesProcesess.duration) / 3600 AS DOUBLE PRECISION) AS running_hours,
                CAST(SUM(TimeSeriesProcesess.processors * TimeSeriesProcesess.duration) / 3600 AS DOUBLE PRECISION) AS core_hours,
                FIRST(TimeSeriesProcesess.version_id ORDER BY TimeSeriesProcesess.weight) AS agent_version_lowest
            FROM TimeSeriesProcesess
            GROUP BY TimeSeriesProcesess.start_time, TimeSeriesProcesess.end_time, TimeSeriesProcesess.service
            ORDER BY TimeSeriesProcesess.start_time, TimeSeriesProcesess.service;
    END; $function$
;

CREATE OR REPLACE FUNCTION get_deployment(my_cluster_id bigint, service_name text, stype servicetype DEFAULT 'instances'::servicetype, create_hidden boolean DEFAULT false, namespace text DEFAULT NULL::text)
 RETURNS bigint
 LANGUAGE plpgsql
AS $function$
    DECLARE
        service_id bigint;
        service_is_cluster boolean;
        service_full_name text;
    BEGIN
        SELECT CASE WHEN namespace IS NOT NULL THEN CONCAT(service_name, '_', namespace) ELSE service_name END
        INTO service_full_name;

        IF namespace IS NULL THEN
            SELECT Services.ID
            INTO service_id
            FROM Services
            WHERE Services.cluster_id = my_cluster_id
            AND Services.name = service_name
            AND NOT hidden;

            IF service_id IS NOT NULL THEN
                RETURN service_id;
            END IF;
        END IF;

        IF namespace IS NOT NULL THEN
            SELECT Services.ID
            INTO service_id
            FROM Services
            WHERE Services.cluster_id = my_cluster_id
            AND NOT hidden
            AND Services.name = service_name;

            IF service_id IS NOT NULL THEN
                UPDATE Services
                SET hidden = true
                WHERE Services.ID = service_id;
            END IF;

            SELECT Services.ID
            INTO service_id
            FROM Services
            WHERE Services.cluster_id = my_cluster_id
            AND Services.name = service_full_name;

            IF service_id IS NOT NULL THEN
                RETURN service_id;
            END IF;
        END IF;

        INSERT INTO Services(name, service_type, hidden, cluster_id)
        VALUES (service_full_name, stype, create_hidden, my_cluster_id)
        ON CONFLICT DO NOTHING
        RETURNING ID INTO service_id;

        IF service_id IS NOT NULL THEN
            UPDATE Services
            SET is_cluster = TRUE
            WHERE ID = my_cluster_id;

            RETURN -service_id;
        END IF;

        SELECT Services.ID
        INTO service_id
        FROM Services
        WHERE Services.cluster_id = my_cluster_id
        AND Services.name = service_full_name;

        RETURN service_id;
    END; $function$
;

CREATE OR REPLACE FUNCTION get_instance(mac_ macaddr, identifier_ text)
 RETURNS bigint
 LANGUAGE plpgsql
AS $function$
    DECLARE
        instance_id bigint;
    BEGIN
        IF identifier_ IS NULL THEN
            SELECT Instances.ID
            INTO instance_id
            FROM Instances
            WHERE Instances.mac = mac_ AND Instances.identifier IS NULL;
        ELSE
            SELECT Instances.ID
            INTO instance_id
            FROM Instances
            WHERE Instances.mac = mac_ AND Instances.identifier = identifier_;
        END IF;

        IF instance_id IS NOT NULL THEN
            RETURN instance_id;
        END IF;

        INSERT INTO Instances(mac, identifier)
        VALUES (mac_, identifier_)
        ON CONFLICT DO NOTHING
        RETURNING -ID INTO instance_id;

        IF instance_id IS NULL THEN
            IF identifier_ IS NULL THEN
                SELECT Instances.ID
                INTO instance_id
                FROM Instances
                WHERE Instances.mac = mac_ AND Instances.identifier IS NULL;
            ELSE
                SELECT Instances.ID
                INTO instance_id
                FROM Instances
                WHERE Instances.mac = mac_ AND Instances.identifier = identifier_;
            END IF;
        END IF;

        RETURN instance_id;
    END; $function$
;

CREATE OR REPLACE FUNCTION get_instance_run(instance_id bigint, boot_time_ timestamp without time zone, machine_id bigint, kernel_id bigint, metadata_id bigint)
 RETURNS TABLE(instance_run_id bigint, is_new_instance_run boolean)
 LANGUAGE plpgsql
AS $function$
    DECLARE
        instance_run_id bigint;
        machine_query bigint;
        kernel_query bigint;
        metadata_query bigint;
        is_new_instance_run boolean;
        machine_type_current bigint;
        machine_type_other bigint;
        machine_processors_current bigint;
        machine_processors_other bigint;
        machine_memory_current bigint;
        machine_memory_other bigint;
        os_current bigint;
        os_other bigint;
        release_current text;
        release_other text;
        version_current text;
        version_other text;
        hardware_type_current text;
        hardware_type_other text;
    BEGIN
        SELECT InstanceRuns.ID, InstanceRuns.machine, InstanceRuns.kernel, InstanceRuns.metadata
            INTO instance_run_id, machine_query, kernel_query, metadata_query
            FROM InstanceRuns
            WHERE InstanceRuns.instance = instance_id AND
                  InstanceRuns.boot_time = boot_time_;
        is_new_instance_run = FALSE;
        IF instance_run_id IS NOT NULL THEN
            IF machine_query != machine_id AND kernel_query = kernel_id THEN
                SELECT Machines.type, Machines.processors, Machines.memory
                    INTO machine_type_current, machine_processors_current, machine_memory_current
                    FROM Machines WHERE ID = machine_id;
                SELECT Machines.type, Machines.processors, Machines.memory
                    INTO machine_type_other, machine_processors_other, machine_memory_other
                    FROM Machines WHERE ID = machine_query;
                IF machine_type_current != 1 AND machine_type_other = 1 AND metadata_query IS NULL THEN
                    UPDATE InstanceRuns
                    SET machine = machine_id, metadata = metadata_id
                    WHERE ID = instance_run_id;
                    RETURN QUERY SELECT * FROM (VALUES (instance_run_id, is_new_instance_run)) AS t (instance_run_id, is_new_instance_run);
                    RETURN;
                ELSIF machine_type_current = 1 AND machine_type_other != 1 AND metadata_id IS NULL THEN
                    -- silently ignore conflict since DB data is correct and connected agent's metadata failed to fetch
                    RETURN QUERY SELECT * FROM (VALUES (instance_run_id, is_new_instance_run)) AS t (instance_run_id, is_new_instance_run);
                    RETURN;
                ELSIF machine_type_current = machine_type_other AND machine_processors_current = machine_processors_other AND ABS(machine_memory_current - machine_memory_other) < 2 THEN
                    -- silently ignore conflict since change in memory is minor
                    RETURN QUERY SELECT * FROM (VALUES (instance_run_id, is_new_instance_run)) AS t (instance_run_id, is_new_instance_run);
                    RETURN;
                END IF;
            END IF;
            IF kernel_query != kernel_id AND machine_query = machine_id THEN
                SELECT Kernels.os, Kernels.release, Kernels.version, Kernels.hardware_type
                INTO os_current, release_current, version_current, hardware_type_current
                FROM Kernels WHERE ID = kernel_id;
                SELECT Kernels.os, Kernels.release, Kernels.version, Kernels.hardware_type
                INTO os_other, release_other, version_other, hardware_type_other
                FROM Kernels WHERE ID = kernel_query;

                IF os_current != os_other AND release_current = release_other AND
                   version_current = version_other AND hardware_type_current = hardware_type_other THEN
                    UPDATE InstanceRuns
                    SET kernel = kernel_id
                    WHERE ID = instance_run_id;
                    RETURN QUERY SELECT * FROM (VALUES (instance_run_id, is_new_instance_run)) AS t (instance_run_id, is_new_instance_run);
                    RETURN;
                END IF;
            END IF;
            IF machine_query != machine_id OR kernel_query != kernel_id THEN
                RETURN QUERY SELECT * FROM (VALUES (-instance_run_id, is_new_instance_run)) AS t (instance_run_id, is_new_instance_run);  -- indicates that there is a conflict (that we allow)
                RETURN;
            END IF;
            RETURN QUERY SELECT * FROM (VALUES (instance_run_id, is_new_instance_run)) AS t (instance_run_id, is_new_instance_run);
            RETURN;
        END IF;
        INSERT INTO InstanceRuns(instance, boot_time, machine, kernel, metadata)
            VALUES (instance_id, boot_time_, machine_id, kernel_id, metadata_id)
            ON CONFLICT DO NOTHING
            RETURNING ID INTO instance_run_id;
        IF instance_run_id IS NOT NULL THEN
            is_new_instance_run = TRUE;
        ELSE
            -- race condition from first SELECT to INSERT; lets fetch the row that was added async
            SELECT InstanceRuns.ID
                INTO instance_run_id
                FROM InstanceRuns
                WHERE InstanceRuns.instance = instance_id AND
                      InstanceRuns.boot_time = boot_time_;
        END IF;
        RETURN QUERY SELECT * FROM (VALUES (instance_run_id, is_new_instance_run)) AS t (instance_run_id, is_new_instance_run);
    END; $function$
;

CREATE OR REPLACE FUNCTION get_profiler_process(instance_run_id bigint, profiler_version_id bigint, pid_ bigint, spawn_local_time_ timestamp without time zone, spawn_uptime_ bigint, public_ip text, private_ip text, hostname text, service_id bigint, profiler_run_environment_id bigint, run_arguments jsonb)
 RETURNS TABLE(profiler_process_id bigint, is_new_profiler_process boolean)
 LANGUAGE plpgsql
AS $function$
    DECLARE
        profiler_process_id bigint;
        spawn_uptime_query bigint;
        is_new_profiler_process boolean;
    BEGIN
        SELECT ProfilerProcesses.ID, ProfilerProcesses.spawn_uptime
            INTO profiler_process_id, spawn_uptime_query
            FROM ProfilerProcesses
            WHERE ProfilerProcesses.instance_run = instance_run_id AND
                  ProfilerProcesses.profiler_version = profiler_version_id AND
                  ProfilerProcesses.pid = pid_ AND
                  ProfilerProcesses.spawn_local_time = spawn_local_time_;

        IF profiler_process_id IS NOT NULL THEN
            is_new_profiler_process = FALSE; --Existing Profiler agent installation
            IF spawn_uptime_query != spawn_uptime_ THEN
                RETURN QUERY SELECT * FROM (VALUES (-profiler_process_id, is_new_profiler_process)) AS t (profiler_process_id, is_new_profiler_process);  -- indicates that there is a conflict (that we allow)
            ELSE
                RETURN QUERY SELECT * FROM (VALUES (profiler_process_id, is_new_profiler_process)) AS t (profiler_process_id, is_new_profiler_process);
            END IF;
            RETURN;
        END IF;

        INSERT INTO ProfilerProcesses(instance_run, profiler_version, pid, spawn_local_time, spawn_uptime, public_ip, private_ip, hostname, service, profiler_run_environment, run_arguments)
            VALUES (instance_run_id, profiler_version_id, pid_, spawn_local_time_, spawn_uptime_, public_ip, private_ip, hostname, service_id, profiler_run_environment_id, run_arguments)
            ON CONFLICT DO NOTHING
            RETURNING ID INTO profiler_process_id;
        is_new_profiler_process = TRUE; --New Profiler_process
        RETURN QUERY SELECT * FROM (VALUES (profiler_process_id, is_new_profiler_process)) AS t (profiler_process_id, is_new_profiler_process);
    END; $function$
;

CREATE OR REPLACE FUNCTION get_service(service_name text, stype servicetype DEFAULT 'instances'::servicetype, create_hidden boolean DEFAULT false, use_dot_logic boolean DEFAULT true, service_env_type envtype DEFAULT NULL::envtype)
 RETURNS bigint
 LANGUAGE plpgsql
AS $function$
    DECLARE
        service_id bigint;
        my_cluster_id bigint;
        service_is_cluster boolean;
        db_env_type EnvType;
    BEGIN
        SELECT Services.ID, Services.env_type
        INTO service_id, db_env_type
        FROM Services
        WHERE Services.name = service_name;

        IF service_id IS NOT NULL THEN
            IF db_env_type IS NULL AND service_env_type IS NOT NULL THEN
                UPDATE Services
                SET env_type = service_env_type
                WHERE ID = service_id;
            END IF;
            RETURN service_id;
        END IF;

        IF use_dot_logic IS TRUE AND position('.' in service_name) != 0 THEN
            SELECT Services.ID, Services.is_cluster
            INTO my_cluster_id, service_is_cluster
            FROM Services
            WHERE Services.name = SPLIT_PART(service_name, '.', 1);

            IF my_cluster_id IS NOT NULL AND NOT service_is_cluster THEN
                UPDATE Services
                SET is_cluster = TRUE
                WHERE ID = my_cluster_id;
            END IF;
        END IF;

        INSERT INTO Services(name, service_type, hidden, cluster_id, env_type)
        VALUES (service_name, stype, create_hidden, my_cluster_id, service_env_type)
        ON CONFLICT DO NOTHING
        RETURNING ID INTO service_id;

        IF service_id IS NOT NULL THEN
            RETURN -service_id;
        END IF;

        SELECT Services.ID, Services.env_type
        INTO service_id, db_env_type
        FROM Services
        WHERE Services.name = service_name;

        IF db_env_type IS NULL AND service_env_type IS NOT NULL THEN
            UPDATE Services
            SET env_type = service_env_type
            WHERE ID = service_id;
        END IF;

        RETURN service_id;
    END; $function$
;

CREATE OR REPLACE PROCEDURE update_profiler_service_hourly_usages(IN max_iterations bigint DEFAULT 3)
 LANGUAGE plpgsql
AS $procedure$
    DECLARE
        start_date timestamp;  -- will hold the last calculated value + 1h
        end_date timestamp;  -- will hold the last complete hour, which we can complete the calculation over
        connected_time INTERVAL := '10 minutes';
    BEGIN
        SELECT (ProfilerServiceHourlyUsages.start_date + interval '1 hours'), date_trunc('hour', CURRENT_TIMESTAMP - connected_time)
        INTO start_date, end_date
        FROM ProfilerServiceHourlyUsages
        ORDER BY ProfilerServiceHourlyUsages.start_date DESC
        LIMIT 1;
        IF start_date IS NULL THEN
            start_date = date_trunc('hour', CURRENT_TIMESTAMP - interval '1 hour' * 3);
        END IF;
        IF end_date IS NULL THEN
            end_date = date_trunc('hour', CURRENT_TIMESTAMP - connected_time);
        END IF;
        end_date = LEAST(end_date, start_date + interval '1 hour' * max_iterations);
        RAISE NOTICE 'start_date: %, end_date: %', start_date, end_date;
        INSERT INTO ProfilerServiceHourlyUsages(start_date, service, running_hours, core_hours, lowest_agent_version)
        SELECT start_time, service, running_hours, core_hours, lowest_agent_version
        FROM calc_profiler_usage_history(start_date, end_date, 60 * 60, max_iterations);
    END;
$procedure$
;



CREATE FUNCTION first_agg(anyelement, anyelement) RETURNS anyelement
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $_$
        SELECT $1;
$_$;


CREATE AGGREGATE first(anyelement) (
    SFUNC = first_agg,
    STYPE = anyelement
);



CREATE FUNCTION last_agg(anyelement, anyelement) RETURNS anyelement
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $_$
        SELECT $2;
$_$;



CREATE AGGREGATE last(anyelement) (
    SFUNC = last_agg,
    STYPE = anyelement
);


create function zz_concat(text, text) returns text as
    'select md5($1 || $2);' language 'sql';

create aggregate zz_hashagg(text) (
    sfunc = zz_concat,
    stype = text,
    initcond = '');


-- Profiling and Heartbeat Tables (added for profiling request management)

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

    -- Foreign key to services table
    service_id bigint CONSTRAINT "profiling_request_service_fk" REFERENCES Services(ID) ON DELETE CASCADE
);



-- Indexes for better query performance
CREATE INDEX idx_profiling_requests_service_name ON ProfilingRequests(service_name);
CREATE INDEX idx_profiling_requests_status ON ProfilingRequests(status);
CREATE INDEX idx_profiling_requests_target_hostnames ON ProfilingRequests USING GIN(target_hostnames);
CREATE INDEX idx_profiling_requests_created_at ON ProfilingRequests(created_at);
CREATE INDEX idx_profiling_requests_assigned_hostname ON ProfilingRequests(assigned_to_hostname);
