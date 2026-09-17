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

-- Precomputed workload-status store.
--
-- The workload_status endpoint used to aggregate the live
-- HostHeartbeats -> HeartbeatContainers -> HeartbeatProcesses flatten on every
-- request, which is O(fresh rows) and does not scale as fleets onboard. This
-- introduces a precomputed store, rebuilt every ~30s by the periodic-tasks
-- worker and read by the endpoint:
--
--   * Layer 1 -- workload_snapshot: the fresh (host x container x process)
--     flatten, denormalized and indexed. Serves FILTERED reads (filters use the
--     indexes, so only a small subset is scanned; no live 3-way join).
--   * Layer 2 -- workload_scope_summary + workload_tab_counts: precomputed
--     per-scope grouped rows and the six tab counts for the UNFILTERED view.
--     Serves the default landing view instantly.
--
-- Atomic swap: each object has two physical tables (_0 / _1); the reader always
-- queries a VIEW, and the refresh worker rebuilds the inactive generation then
-- re-points the views + flips workload_snapshot_meta in one transaction.

-- ---------------------------------------------------------------- generation meta
CREATE TABLE IF NOT EXISTS workload_snapshot_meta (
    id smallint PRIMARY KEY DEFAULT 1,
    active_generation smallint NOT NULL DEFAULT 0,
    built_at timestamp NULL,
    build_duration_ms integer NULL,
    snapshot_rows bigint NULL,
    CONSTRAINT workload_snapshot_meta_singleton CHECK (id = 1)
);

INSERT INTO workload_snapshot_meta (id, active_generation)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;

-- ------------------------------------------------------------- Layer 1: snapshot
-- One physical table per generation; identical schema. The row grain is one row
-- per (fresh host, container, process); hosts with no containers / containers
-- with no processes contribute a row with NULL child columns (LEFT JOIN grain),
-- matching the previous live flatten exactly.
DO $$
DECLARE
    gen text;
BEGIN
    FOREACH gen IN ARRAY ARRAY['0', '1'] LOOP
        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS workload_snapshot_%1$s (
                host_id bigint NOT NULL,
                hostname text NOT NULL,
                ip_address text NULL,
                service_name text NOT NULL,
                agent_version text NULL,
                run_mode text NULL,
                heartbeat_timestamp timestamp NOT NULL,
                namespace text NULL,
                pod_name text NULL,
                container_name text NULL,
                workload_name text NULL,
                workload_kind text NULL,
                pid integer NULL,
                process_name text NULL,
                command_type text NULL,
                command_status text NULL,
                combined_config jsonb NULL,
                profiling_status text NULL
            )
        $f$, gen);
        -- Filter-column indexes so filtered reads touch only the matching subset.
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_snap_%1$s_service ON workload_snapshot_%1$s (service_name)', gen);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_snap_%1$s_hostname ON workload_snapshot_%1$s (hostname)', gen);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_snap_%1$s_namespace ON workload_snapshot_%1$s (namespace)', gen);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_snap_%1$s_pod ON workload_snapshot_%1$s (pod_name)', gen);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_snap_%1$s_container ON workload_snapshot_%1$s (container_name)', gen);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_snap_%1$s_process ON workload_snapshot_%1$s (process_name)', gen);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_snap_%1$s_pid ON workload_snapshot_%1$s (pid)', gen);
    END LOOP;
END $$;

-- ------------------------------------------------- Layer 2: per-scope grouped rows
-- Precomputed grouped rows for the coarse, few/large-entity scopes that are slow
-- to aggregate live (service / namespace / pod / host). Fine scopes
-- (container / process) are served from the Layer 1 snapshot directly. Column
-- shape mirrors the dicts get_workload_inventory_status returns, so the reader
-- reuses the existing row-building code.
DO $$
DECLARE
    gen text;
BEGIN
    FOREACH gen IN ARRAY ARRAY['0', '1'] LOOP
        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS workload_scope_summary_%1$s (
                scope text NOT NULL,
                sort_seq integer NOT NULL,          -- default (key) ordering position
                row_id text NOT NULL,
                service_name text NULL,
                hostname text NULL,
                namespace text NULL,
                pod_name text NULL,
                container_name text NULL,
                host_count integer NULL,
                namespace_count integer NULL,
                pod_count integer NULL,
                container_count integer NULL,
                process_count integer NULL,
                pids integer[] NULL,
                l_hostname text NULL,
                l_ip_address text NULL,
                l_namespace text NULL,
                l_pod_name text NULL,
                l_container_name text NULL,
                l_workload_name text NULL,
                l_workload_kind text NULL,
                l_process_name text NULL,
                l_pid integer NULL,
                l_command_type text NULL,
                l_command_status text NULL,
                l_combined_config jsonb NULL,
                any_active boolean NULL,
                l_profiling_status text NULL,
                l_agent_version text NULL,
                l_run_mode text NULL,
                l_heartbeat_timestamp timestamp NULL
            )
        $f$, gen);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_wl_summary_%1$s_scope_seq ON workload_scope_summary_%1$s (scope, sort_seq)', gen);
    END LOOP;
END $$;

-- ------------------------------------------------------- Layer 2: tab counts
CREATE TABLE IF NOT EXISTS workload_tab_counts_0 (
    scope text PRIMARY KEY,
    count bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS workload_tab_counts_1 (
    scope text PRIMARY KEY,
    count bigint NOT NULL
);

-- --------------------------------------------------------------- read-side views
-- Point at generation 0 initially; the refresh worker re-points these on swap.
CREATE OR REPLACE VIEW workload_snapshot AS SELECT * FROM workload_snapshot_0;
CREATE OR REPLACE VIEW workload_scope_summary AS SELECT * FROM workload_scope_summary_0;
CREATE OR REPLACE VIEW workload_tab_counts AS SELECT * FROM workload_tab_counts_0;

-- ---------------------------------------------------------- refresh procedure
-- Rebuilds the inactive generation (Layer 1 snapshot + Layer 2 summaries/counts)
-- from the live heartbeat tables, then atomically re-points the read-side views
-- and flips workload_snapshot_meta. Readers only ever touch the active
-- generation's tables (via the views), so the rebuild never blocks reads.
CREATE OR REPLACE PROCEDURE refresh_workload_snapshot(IN fresh_interval interval DEFAULT '2 minutes')
    LANGUAGE plpgsql
AS $procedure$
DECLARE
    cur_gen   smallint;
    new_gen   smallint;
    snap_tbl  text;
    sum_tbl   text;
    cnt_tbl   text;
    t0        timestamptz := clock_timestamp();
    n_rows    bigint;
    -- Shared per-group aggregate tail (identical for every coarse scope).
    agg_tail  text := $a$
        COUNT(DISTINCT hostname),
        COUNT(DISTINCT namespace) FILTER (WHERE namespace IS NOT NULL),
        COUNT(DISTINCT pod_name) FILTER (WHERE pod_name IS NOT NULL),
        COUNT(DISTINCT container_name) FILTER (WHERE container_name IS NOT NULL),
        COUNT(DISTINCT (pid, process_name)) FILTER (WHERE pid IS NOT NULL),
        array_agg(DISTINCT pid) FILTER (WHERE pid IS NOT NULL),
        (array_agg(hostname ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(ip_address ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(namespace ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(pod_name ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(container_name ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(workload_name ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(workload_kind ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(process_name ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(pid ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(command_type ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(command_status ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(combined_config ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        bool_or(profiling_status = 'active'),
        (array_agg(profiling_status ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(agent_version ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        (array_agg(run_mode ORDER BY heartbeat_timestamp DESC NULLS LAST))[1],
        MAX(heartbeat_timestamp)
    $a$;
    sum_cols text := $c$scope, sort_seq, row_id, service_name, hostname, namespace, pod_name, container_name,
        host_count, namespace_count, pod_count, container_count, process_count, pids,
        l_hostname, l_ip_address, l_namespace, l_pod_name, l_container_name, l_workload_name, l_workload_kind,
        l_process_name, l_pid, l_command_type, l_command_status, l_combined_config, any_active, l_profiling_status,
        l_agent_version, l_run_mode, l_heartbeat_timestamp$c$;
BEGIN
    SELECT active_generation INTO cur_gen FROM workload_snapshot_meta WHERE id = 1 FOR UPDATE;
    new_gen  := 1 - cur_gen;
    snap_tbl := 'workload_snapshot_'      || new_gen;
    sum_tbl  := 'workload_scope_summary_' || new_gen;
    cnt_tbl  := 'workload_tab_counts_'    || new_gen;

    EXECUTE format('TRUNCATE %I', snap_tbl);
    EXECUTE format('TRUNCATE %I', sum_tbl);
    EXECUTE format('TRUNCATE %I', cnt_tbl);

    -- Layer 1: the fresh flatten (host x container x process), PID-aware status.
    EXECUTE format($f$
        INSERT INTO %1$I (host_id, hostname, ip_address, service_name, agent_version, run_mode,
            heartbeat_timestamp, namespace, pod_name, container_name, workload_name, workload_kind,
            pid, process_name, command_type, command_status, combined_config, profiling_status)
        WITH fresh_hosts AS MATERIALIZED (
            SELECT fh.id, fh.hostname, host(fh.ip_address) AS ip_address, fh.service_name,
                   fh.agent_version, fh.run_mode, fh.heartbeat_timestamp
            FROM HostHeartbeats fh
            WHERE fh.heartbeat_timestamp > NOW() - %2$L::interval
        ),
        current_commands AS (
            SELECT hostname, service_name, command_type, status, combined_config FROM ProfilingCommands
        )
        SELECT fh.id, fh.hostname, fh.ip_address, fh.service_name, fh.agent_version, fh.run_mode,
               fh.heartbeat_timestamp, hc.namespace, hc.pod_name, hc.container_name, hc.workload_name,
               hc.workload_kind, hp.pid, hp.process_name,
               COALESCE(c.command_type, 'N/A'), c.status::text, c.combined_config,
               CASE
                   WHEN c.status IS NULL THEN 'stopped'
                   WHEN c.command_type = 'start' AND c.status IN ('pending','sent','completed') THEN
                       CASE
                           WHEN c.combined_config IS NULL OR (c.combined_config -> 'pids') IS NULL
                                OR jsonb_typeof(c.combined_config -> 'pids') <> 'array'
                                OR jsonb_array_length(c.combined_config -> 'pids') = 0
                               THEN 'active'
                           WHEN hp.pid IS NOT NULL AND EXISTS (
                               SELECT 1 FROM jsonb_array_elements_text(c.combined_config -> 'pids') AS t(pid)
                               WHERE t.pid = hp.pid::text
                           ) THEN 'active'
                           ELSE 'stopped'
                       END
                   ELSE c.status::text
               END
        FROM fresh_hosts fh
        LEFT JOIN current_commands c ON fh.hostname = c.hostname AND fh.service_name = c.service_name
        LEFT JOIN HeartbeatContainers hc ON hc.host_id = fh.id
        LEFT JOIN HeartbeatProcesses hp ON hp.container_row_id = hc.id
    $f$, snap_tbl, fresh_interval);
    GET DIAGNOSTICS n_rows = ROW_COUNT;

    -- Layer 2: coarse-scope grouped rows (service / namespace / pod). host,
    -- container and process scopes are served live from the snapshot (fast).
    EXECUTE format($f$
        INSERT INTO %1$I (%3$s)
        SELECT 'service', row_number() OVER (ORDER BY service_name ASC NULLS LAST), service_name,
               service_name, NULL, NULL, NULL, NULL, %4$s
        FROM %2$I GROUP BY service_name
    $f$, sum_tbl, snap_tbl, sum_cols, agg_tail);

    EXECUTE format($f$
        INSERT INTO %1$I (%3$s)
        SELECT 'namespace', row_number() OVER (ORDER BY service_name ASC NULLS LAST, namespace ASC NULLS LAST),
               service_name || '|' || COALESCE(namespace, ''),
               service_name, NULL, namespace, NULL, NULL, %4$s
        FROM %2$I WHERE namespace IS NOT NULL GROUP BY service_name, namespace
    $f$, sum_tbl, snap_tbl, sum_cols, agg_tail);

    EXECUTE format($f$
        INSERT INTO %1$I (%3$s)
        SELECT 'pod', row_number() OVER (ORDER BY service_name ASC NULLS LAST, namespace ASC NULLS LAST, pod_name ASC NULLS LAST),
               service_name || '|' || COALESCE(namespace, '') || '|' || COALESCE(pod_name, ''),
               service_name, NULL, namespace, pod_name, NULL, %4$s
        FROM %2$I WHERE pod_name IS NOT NULL GROUP BY service_name, namespace, pod_name
    $f$, sum_tbl, snap_tbl, sum_cols, agg_tail);

    -- Layer 2: the six tab counts + active_hosts, one snapshot scan.
    EXECUTE format($f$
        INSERT INTO %1$I (scope, count)
        SELECT k, v FROM (
            SELECT COUNT(DISTINCT service_name) AS c_service,
                   COUNT(DISTINCT (service_name, hostname)) AS c_host,
                   COUNT(DISTINCT (service_name, namespace)) FILTER (WHERE namespace IS NOT NULL) AS c_namespace,
                   COUNT(DISTINCT (service_name, namespace, pod_name)) FILTER (WHERE pod_name IS NOT NULL) AS c_pod,
                   COUNT(DISTINCT (service_name, hostname, namespace, pod_name, container_name)) FILTER (WHERE container_name IS NOT NULL) AS c_container,
                   COUNT(DISTINCT (service_name, hostname, pid)) FILTER (WHERE pid IS NOT NULL) AS c_process,
                   COUNT(DISTINCT hostname) AS active_hosts
            FROM %2$I
        ) t, LATERAL (VALUES ('service', t.c_service), ('host', t.c_host), ('namespace', t.c_namespace),
                             ('pod', t.c_pod), ('container', t.c_container), ('process', t.c_process),
                             ('active_hosts', t.active_hosts)) AS x(k, v)
    $f$, cnt_tbl, snap_tbl);

    -- Atomic swap: re-point views + flip the pointer, all in this transaction.
    EXECUTE format('CREATE OR REPLACE VIEW workload_snapshot AS SELECT * FROM %I', snap_tbl);
    EXECUTE format('CREATE OR REPLACE VIEW workload_scope_summary AS SELECT * FROM %I', sum_tbl);
    EXECUTE format('CREATE OR REPLACE VIEW workload_tab_counts AS SELECT * FROM %I', cnt_tbl);

    UPDATE workload_snapshot_meta
    SET active_generation = new_gen,
        built_at = clock_timestamp(),
        build_duration_ms = (EXTRACT(EPOCH FROM (clock_timestamp() - t0)) * 1000)::integer,
        snapshot_rows = n_rows
    WHERE id = 1;
END;
$procedure$;
