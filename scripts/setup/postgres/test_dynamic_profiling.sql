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
-- TEST DATA FOR DYNAMIC PROFILING SCHEMA
-- ============================================================
-- This script creates sample data to verify the dynamic profiling
-- schema is working correctly.
-- ============================================================

-- Clean up any existing test data (optional, comment out if not needed)
-- DELETE FROM ProfilingExecutions;
-- DELETE FROM ProfilingCommand;
-- DELETE FROM ProfilingRequest;
-- DELETE FROM HostHeartbeats;
-- DELETE FROM ProcessesHosts;
-- DELETE FROM ContainersHosts;
-- DELETE FROM ContainerProcesses;
-- DELETE FROM JobContainers;
-- DELETE FROM ServiceContainers;
-- DELETE FROM NamespaceServices;

\echo 'Creating test data for Dynamic Profiling...'

-- ============================================================
-- 1. HIERARCHICAL MAPPINGS
-- ============================================================

\echo '1. Creating hierarchical mappings...'

-- Namespace -> Service mappings
INSERT INTO NamespaceServices (namespace, service_name) VALUES
    ('production', 'web-api'),
    ('production', 'data-processor'),
    ('staging', 'web-api'),
    ('development', 'test-service')
ON CONFLICT DO NOTHING;

-- Service -> Container mappings
INSERT INTO ServiceContainers (service_name, container_name) VALUES
    ('web-api', 'web-api-container-1'),
    ('web-api', 'web-api-container-2'),
    ('data-processor', 'processor-container-1'),
    ('test-service', 'test-container-1')
ON CONFLICT DO NOTHING;

-- Job -> Container mappings
INSERT INTO JobContainers (job_name, container_name) VALUES
    ('batch-processing-job', 'processor-container-1'),
    ('data-import-job', 'importer-container-1'),
    ('etl-pipeline', 'etl-container-1')
ON CONFLICT DO NOTHING;

-- Container -> Process mappings
INSERT INTO ContainerProcesses (container_name, process_id, process_name) VALUES
    ('web-api-container-1', 1001, 'python3'),
    ('web-api-container-1', 1002, 'gunicorn'),
    ('web-api-container-2', 2001, 'python3'),
    ('web-api-container-2', 2002, 'gunicorn'),
    ('processor-container-1', 3001, 'python3'),
    ('processor-container-1', 3002, 'celery')
ON CONFLICT DO NOTHING;

-- Container -> Host mappings
INSERT INTO ContainersHosts (container_name, host_id, host_name) VALUES
    ('web-api-container-1', 'host-001', 'worker-node-01'),
    ('web-api-container-2', 'host-002', 'worker-node-02'),
    ('processor-container-1', 'host-003', 'worker-node-03'),
    ('test-container-1', 'host-004', 'dev-node-01')
ON CONFLICT DO NOTHING;

-- Process -> Host mappings
INSERT INTO ProcessesHosts (process_id, host_id, host_name) VALUES
    (1001, 'host-001', 'worker-node-01'),
    (1002, 'host-001', 'worker-node-01'),
    (2001, 'host-002', 'worker-node-02'),
    (2002, 'host-002', 'worker-node-02'),
    (3001, 'host-003', 'worker-node-03'),
    (3002, 'host-003', 'worker-node-03')
ON CONFLICT DO NOTHING;

\echo '  ✓ Hierarchical mappings created'

-- ============================================================
-- 2. HOST HEARTBEATS
-- ============================================================

\echo '2. Creating host heartbeats...'

INSERT INTO HostHeartbeats (
    host_id,
    service_name,
    host_name,
    host_ip,
    namespace,
    pod_name,
    containers,
    workloads,
    jobs,
    executors,
    timestamp_first_seen,
    timestamp_last_seen
) VALUES
    (
        'host-001',
        'web-api',
        'worker-node-01',
        '10.0.1.101',
        'production',
        'web-api-pod-1',
        ARRAY['web-api-container-1'],
        '{"cpu_usage": 45.2, "memory_usage": 60.5}'::jsonb,
        ARRAY['background-task-1'],
        ARRAY['pyspy', 'perf'],
        NOW() - INTERVAL '1 hour',
        NOW() - INTERVAL '5 seconds'
    ),
    (
        'host-002',
        'web-api',
        'worker-node-02',
        '10.0.1.102',
        'production',
        'web-api-pod-2',
        ARRAY['web-api-container-2'],
        '{"cpu_usage": 38.7, "memory_usage": 55.3}'::jsonb,
        ARRAY['background-task-2'],
        ARRAY['pyspy', 'perf'],
        NOW() - INTERVAL '1 hour',
        NOW() - INTERVAL '3 seconds'
    ),
    (
        'host-003',
        'data-processor',
        'worker-node-03',
        '10.0.1.103',
        'production',
        'processor-pod-1',
        ARRAY['processor-container-1'],
        '{"cpu_usage": 78.4, "memory_usage": 82.1}'::jsonb,
        ARRAY['batch-processing-job', 'etl-pipeline'],
        ARRAY['pyspy', 'perf', 'async-profiler'],
        NOW() - INTERVAL '2 hours',
        NOW() - INTERVAL '2 seconds'
    ),
    (
        'host-004',
        'test-service',
        'dev-node-01',
        '10.0.2.101',
        'development',
        'test-pod-1',
        ARRAY['test-container-1'],
        '{"cpu_usage": 15.2, "memory_usage": 25.8}'::jsonb,
        ARRAY[]::text[],
        ARRAY['pyspy'],
        NOW() - INTERVAL '30 minutes',
        NOW() - INTERVAL '10 seconds'
    )
ON CONFLICT (host_id) DO UPDATE SET
    timestamp_last_seen = EXCLUDED.timestamp_last_seen;

\echo '  ✓ Host heartbeats created'

-- ============================================================
-- 3. PROFILING REQUESTS
-- ============================================================

\echo '3. Creating profiling requests...'

-- Request 1: Service-level profiling
INSERT INTO ProfilingRequest (
    service_name,
    profiling_mode,
    duration_seconds,
    sample_rate,
    executors,
    start_time,
    stop_time,
    status
) VALUES
    (
        'web-api',
        'cpu',
        60,
        100,
        ARRAY['pyspy'],
        NOW() - INTERVAL '10 minutes',
        NOW() - INTERVAL '9 minutes',
        'completed'
    );

-- Request 2: Namespace-level profiling
INSERT INTO ProfilingRequest (
    namespace,
    profiling_mode,
    duration_seconds,
    sample_rate,
    executors,
    start_time,
    status
) VALUES
    (
        'production',
        'memory',
        120,
        50,
        ARRAY['pyspy', 'perf'],
        NOW() - INTERVAL '5 minutes',
        'in_progress'
    );

-- Request 3: Host-level profiling
INSERT INTO ProfilingRequest (
    host_name,
    profiling_mode,
    duration_seconds,
    sample_rate,
    start_time,
    status
) VALUES
    (
        'worker-node-03',
        'cpu',
        30,
        200,
        NOW(),
        'pending'
    );

-- Request 4: Job-level profiling
INSERT INTO ProfilingRequest (
    job_name,
    profiling_mode,
    duration_seconds,
    sample_rate,
    executors,
    start_time,
    status
) VALUES
    (
        'batch-processing-job',
        'allocation',
        300,
        100,
        ARRAY['async-profiler'],
        NOW() - INTERVAL '15 minutes',
        'completed'
    );

\echo '  ✓ Profiling requests created'

-- ============================================================
-- 4. PROFILING COMMANDS
-- ============================================================

\echo '4. Creating profiling commands...'

-- Get request IDs for reference
DO $$
DECLARE
    req1_id bigint;
    req2_id bigint;
    req4_id bigint;
BEGIN
    -- Get the request IDs
    SELECT ID INTO req1_id FROM ProfilingRequest WHERE service_name = 'web-api' LIMIT 1;
    SELECT ID INTO req2_id FROM ProfilingRequest WHERE namespace = 'production' LIMIT 1;
    SELECT ID INTO req4_id FROM ProfilingRequest WHERE job_name = 'batch-processing-job' LIMIT 1;

    -- Commands for request 1 (completed)
    INSERT INTO ProfilingCommand (
        profiling_request_id,
        host_id,
        target_containers,
        target_processes,
        command_type,
        command_args,
        command_json,
        sent_at,
        completed_at,
        status
    ) VALUES
        (
            req1_id,
            'host-001',
            ARRAY['web-api-container-1'],
            ARRAY[1001, 1002],
            'start',
            '{"mode": "cpu", "duration": 60, "sample_rate": 100}'::jsonb,
            '{"command": "pyspy", "args": ["--rate", "100", "--duration", "60"]}',
            NOW() - INTERVAL '10 minutes',
            NOW() - INTERVAL '9 minutes',
            'completed'
        ),
        (
            req1_id,
            'host-002',
            ARRAY['web-api-container-2'],
            ARRAY[2001, 2002],
            'start',
            '{"mode": "cpu", "duration": 60, "sample_rate": 100}'::jsonb,
            '{"command": "pyspy", "args": ["--rate", "100", "--duration", "60"]}',
            NOW() - INTERVAL '10 minutes',
            NOW() - INTERVAL '9 minutes',
            'completed'
        );

    -- Commands for request 2 (in progress)
    INSERT INTO ProfilingCommand (
        profiling_request_id,
        host_id,
        target_containers,
        command_type,
        command_args,
        command_json,
        sent_at,
        status
    ) VALUES
        (
            req2_id,
            'host-001',
            ARRAY['web-api-container-1'],
            'start',
            '{"mode": "memory", "duration": 120, "sample_rate": 50}'::jsonb,
            '{"command": "pyspy", "args": ["--rate", "50", "--duration", "120", "--memory"]}',
            NOW() - INTERVAL '5 minutes',
            'in_progress'
        );

    -- Commands for request 4 (completed)
    INSERT INTO ProfilingCommand (
        profiling_request_id,
        host_id,
        target_containers,
        command_type,
        command_args,
        command_json,
        sent_at,
        completed_at,
        status
    ) VALUES
        (
            req4_id,
            'host-003',
            ARRAY['processor-container-1'],
            'start',
            '{"mode": "allocation", "duration": 300, "sample_rate": 100}'::jsonb,
            '{"command": "async-profiler", "args": ["--alloc", "--duration", "300"]}',
            NOW() - INTERVAL '15 minutes',
            NOW() - INTERVAL '10 minutes',
            'completed'
        );

    RAISE NOTICE 'Created commands for requests: %, %, %', req1_id, req2_id, req4_id;
END $$;

\echo '  ✓ Profiling commands created'

-- ============================================================
-- 5. PROFILING EXECUTIONS (AUDIT)
-- ============================================================

\echo '5. Creating profiling executions...'

DO $$
DECLARE
    req1_id bigint;
    cmd1_id bigint;
    cmd2_id bigint;
BEGIN
    -- Get IDs
    SELECT ID INTO req1_id FROM ProfilingRequest WHERE service_name = 'web-api' LIMIT 1;
    SELECT ID INTO cmd1_id FROM ProfilingCommand WHERE host_id = 'host-001' AND status = 'completed' LIMIT 1;
    SELECT ID INTO cmd2_id FROM ProfilingCommand WHERE host_id = 'host-002' AND status = 'completed' LIMIT 1;

    -- Execution records
    INSERT INTO ProfilingExecutions (
        profiling_request_id,
        profiling_command_id,
        host_name,
        target_containers,
        target_processes,
        command_type,
        started_at,
        completed_at,
        status
    ) VALUES
        (
            req1_id,
            cmd1_id,
            'worker-node-01',
            ARRAY['web-api-container-1'],
            ARRAY[1001, 1002],
            'start',
            NOW() - INTERVAL '10 minutes',
            NOW() - INTERVAL '9 minutes',
            'completed'
        ),
        (
            req1_id,
            cmd2_id,
            'worker-node-02',
            ARRAY['web-api-container-2'],
            ARRAY[2001, 2002],
            'start',
            NOW() - INTERVAL '10 minutes',
            NOW() - INTERVAL '9 minutes',
            'completed'
        );

    RAISE NOTICE 'Created execution records for request: %', req1_id;
END $$;

\echo '  ✓ Profiling executions created'

-- ============================================================
-- 6. VERIFICATION QUERIES
-- ============================================================

\echo ''
\echo '=========================================='
\echo 'VERIFICATION QUERIES'
\echo '=========================================='
\echo ''

\echo 'Table Row Counts:'
SELECT 
    'NamespaceServices' as table_name, COUNT(*) as row_count FROM NamespaceServices
UNION ALL SELECT 'ServiceContainers', COUNT(*) FROM ServiceContainers
UNION ALL SELECT 'JobContainers', COUNT(*) FROM JobContainers
UNION ALL SELECT 'ContainerProcesses', COUNT(*) FROM ContainerProcesses
UNION ALL SELECT 'ContainersHosts', COUNT(*) FROM ContainersHosts
UNION ALL SELECT 'ProcessesHosts', COUNT(*) FROM ProcessesHosts
UNION ALL SELECT 'HostHeartbeats', COUNT(*) FROM HostHeartbeats
UNION ALL SELECT 'ProfilingRequest', COUNT(*) FROM ProfilingRequest
UNION ALL SELECT 'ProfilingCommand', COUNT(*) FROM ProfilingCommand
UNION ALL SELECT 'ProfilingExecutions', COUNT(*) FROM ProfilingExecutions
ORDER BY table_name;

\echo ''
\echo 'Sample Profiling Request with Commands:'
SELECT 
    pr.request_id,
    pr.service_name,
    pr.profiling_mode,
    pr.status as request_status,
    COUNT(pc.id) as command_count,
    COUNT(CASE WHEN pc.status = 'completed' THEN 1 END) as completed_commands
FROM ProfilingRequest pr
LEFT JOIN ProfilingCommand pc ON pc.profiling_request_id = pr.id
GROUP BY pr.id, pr.request_id, pr.service_name, pr.profiling_mode, pr.status
ORDER BY pr.created_at DESC
LIMIT 5;

\echo ''
\echo 'Active Hosts (Last Seen < 1 minute ago):'
SELECT 
    host_id,
    host_name,
    service_name,
    namespace,
    ARRAY_LENGTH(containers, 1) as container_count,
    ARRAY_LENGTH(jobs, 1) as job_count,
    EXTRACT(EPOCH FROM (NOW() - timestamp_last_seen))::integer as seconds_since_last_seen
FROM HostHeartbeats
WHERE timestamp_last_seen > NOW() - INTERVAL '1 minute'
ORDER BY timestamp_last_seen DESC;

\echo ''
\echo 'Hierarchical Mapping: Namespace → Service → Container → Host:'
SELECT 
    ns.namespace,
    ns.service_name,
    sc.container_name,
    ch.host_name,
    ch.host_id
FROM NamespaceServices ns
JOIN ServiceContainers sc ON sc.service_name = ns.service_name
JOIN ContainersHosts ch ON ch.container_name = sc.container_name
ORDER BY ns.namespace, ns.service_name, ch.host_name;

\echo ''
\echo '=========================================='
\echo 'TEST DATA CREATION COMPLETE ✓'
\echo '=========================================='
\echo ''
\echo 'Summary:'
\echo '  • Hierarchical mappings: Created'
\echo '  • Host heartbeats: 4 active hosts'
\echo '  • Profiling requests: 4 requests (pending, in_progress, completed)'
\echo '  • Profiling commands: Multiple commands'
\echo '  • Profiling executions: Audit trail created'
\echo ''
\echo 'Ready to test Dynamic Profiling queries!'
\echo ''




