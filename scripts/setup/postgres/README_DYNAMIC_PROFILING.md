# Dynamic Profiling Database Setup

This directory contains SQL scripts for setting up and testing the Dynamic Profiling database schema.

## Files

1. **`dynamic_profiling_schema.sql`** - Main schema with all tables, indexes, and constraints
2. **`test_dynamic_profiling.sql`** - Test data and verification queries

## Quick Setup

### 1. Create Schema

```bash
# Option A: Using psql command line
psql -U postgres -d gprofiler -f dynamic_profiling_schema.sql

# Option B: Using psql interactive
psql -U postgres -d gprofiler
\i dynamic_profiling_schema.sql
\q
```

### 2. Load Test Data (Optional)

```bash
# Load test data
psql -U postgres -d gprofiler -f test_dynamic_profiling.sql
```

### 3. Verify Installation

```sql
-- Connect to database
psql -U postgres -d gprofiler

-- List all dynamic profiling tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND (table_name LIKE '%profiling%' OR table_name LIKE '%heartbeat%')
ORDER BY table_name;

-- Expected output: 10 tables
--  containershosts
--  containerprocesses
--  hostheartbeats
--  jobcontainers
--  namespaceservices
--  processeshosts
--  profilingcommand
--  profilingexecutions
--  profilingrequest
--  servicecontainers
```

## Schema Overview

### Core Tables

#### ProfilingRequest
Stores profiling requests from API calls.
- Supports hierarchical targeting (service/job/namespace/pod/host/process)
- Configurable profiling modes (CPU, memory, allocation, native)
- Status tracking (pending, in_progress, completed, failed, cancelled)

#### ProfilingCommand
Commands sent to agents on specific hosts.
- Maps requests to host-specific commands
- Tracks command lifecycle
- Indexed for fast lookups (165k QPM target)

#### HostHeartbeats
Real-time host availability tracking.
- Optimized for high-throughput (165k QPM)
- Sub-second response times
- Tracks containers, jobs, workloads per host

#### ProfilingExecutions
Audit trail of all profiling executions.
- Links to original requests and commands
- Complete execution history
- Status tracking for troubleshooting

### Mapping Tables

Denormalized tables for fast query performance:

- **NamespaceServices** - Namespace → Service
- **ServiceContainers** - Service → Container
- **JobContainers** - Job → Container
- **ContainerProcesses** - Container → Process
- **ContainersHosts** - Container → Host
- **ProcessesHosts** - Process → Host

## Performance Features

### Indexes (25+ total)

```sql
-- Check indexes
SELECT 
    tablename, 
    indexname, 
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public' 
  AND (tablename LIKE '%profiling%' OR tablename LIKE '%heartbeat%')
ORDER BY tablename, indexname;
```

### Triggers (10 total)

All tables have auto-updating `updated_at` timestamps:

```sql
-- Check triggers
SELECT 
    trigger_name, 
    event_object_table, 
    action_statement
FROM information_schema.triggers
WHERE trigger_schema = 'public'
  AND trigger_name LIKE '%updated_at%'
ORDER BY event_object_table;
```

## Common Queries

### Find Active Hosts

```sql
-- Hosts seen in last 5 minutes
SELECT 
    host_id,
    host_name,
    service_name,
    namespace,
    timestamp_last_seen,
    EXTRACT(EPOCH FROM (NOW() - timestamp_last_seen)) as seconds_ago
FROM HostHeartbeats
WHERE timestamp_last_seen > NOW() - INTERVAL '5 minutes'
ORDER BY timestamp_last_seen DESC;
```

### Query Profiling Requests by Status

```sql
-- Active profiling requests
SELECT 
    request_id,
    service_name,
    namespace,
    profiling_mode,
    duration_seconds,
    status,
    created_at
FROM ProfilingRequest
WHERE status IN ('pending', 'in_progress')
ORDER BY created_at DESC;
```

### Hierarchical Mapping: Namespace to Hosts

```sql
-- Map namespace to all hosts
SELECT DISTINCT
    ns.namespace,
    ns.service_name,
    ch.host_name,
    ch.host_id
FROM NamespaceServices ns
JOIN ServiceContainers sc ON sc.service_name = ns.service_name
JOIN ContainersHosts ch ON ch.container_name = sc.container_name
WHERE ns.namespace = 'production'
ORDER BY ns.service_name, ch.host_name;
```

### Audit Trail: Request Execution History

```sql
-- Complete execution history for a request
SELECT 
    pr.request_id,
    pr.service_name,
    pr.status as request_status,
    pe.host_name,
    pe.command_type,
    pe.status as execution_status,
    pe.started_at,
    pe.completed_at,
    EXTRACT(EPOCH FROM (pe.completed_at - pe.started_at)) as duration_seconds
FROM ProfilingRequest pr
JOIN ProfilingExecutions pe ON pe.profiling_request_id = pr.id
WHERE pr.request_id = 'YOUR-REQUEST-UUID-HERE'
ORDER BY pe.started_at;
```

## Maintenance

### Regular Maintenance Tasks

```sql
-- Vacuum and analyze for performance
VACUUM ANALYZE ProfilingRequest;
VACUUM ANALYZE ProfilingCommand;
VACUUM ANALYZE HostHeartbeats;
VACUUM ANALYZE ProfilingExecutions;

-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
  AND (tablename LIKE '%profiling%' OR tablename LIKE '%heartbeat%')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Monitor Index Usage

```sql
-- Check which indexes are being used
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
  AND (tablename LIKE '%profiling%' OR tablename LIKE '%heartbeat%')
ORDER BY idx_scan DESC;
```

### Clean Up Old Data

```sql
-- Archive executions older than 90 days
DELETE FROM ProfilingExecutions
WHERE created_at < NOW() - INTERVAL '90 days';

-- Archive completed requests older than 30 days
DELETE FROM ProfilingRequest
WHERE status = 'completed'
  AND created_at < NOW() - INTERVAL '30 days';
```

## Troubleshooting

### Issue: Slow Heartbeat Queries

```sql
-- Check if indexes are being used
EXPLAIN ANALYZE
SELECT * FROM HostHeartbeats
WHERE host_id = 'your-host-id';

-- Should show "Index Scan using host_heartbeats_host_id_idx"
```

### Issue: Slow Hierarchical Queries

```sql
-- Check query plan for hierarchical lookup
EXPLAIN ANALYZE
SELECT ch.host_id
FROM NamespaceServices ns
JOIN ServiceContainers sc ON sc.service_name = ns.service_name
JOIN ContainersHosts ch ON ch.container_name = sc.container_name
WHERE ns.namespace = 'production';

-- Should use indexes on all join columns
```

### Issue: Foreign Key Violations

```sql
-- Check orphaned records
SELECT 'ProfilingCommand' as table_name, COUNT(*) as orphaned
FROM ProfilingCommand pc
LEFT JOIN ProfilingRequest pr ON pr.id = pc.profiling_request_id
WHERE pr.id IS NULL
UNION ALL
SELECT 'ProfilingExecutions', COUNT(*)
FROM ProfilingExecutions pe
LEFT JOIN ProfilingRequest pr ON pr.id = pe.profiling_request_id
WHERE pr.id IS NULL;
```

## Drop Schema (Caution!)

```sql
-- WARNING: This will delete all dynamic profiling data!
-- Uncomment and run only if you need to completely remove the schema

-- DROP TABLE IF EXISTS ProcessesHosts CASCADE;
-- DROP TABLE IF EXISTS ContainersHosts CASCADE;
-- DROP TABLE IF EXISTS ContainerProcesses CASCADE;
-- DROP TABLE IF EXISTS JobContainers CASCADE;
-- DROP TABLE IF EXISTS ServiceContainers CASCADE;
-- DROP TABLE IF EXISTS NamespaceServices CASCADE;
-- DROP TABLE IF EXISTS ProfilingExecutions CASCADE;
-- DROP TABLE IF EXISTS ProfilingCommand CASCADE;
-- DROP TABLE IF EXISTS HostHeartbeats CASCADE;
-- DROP TABLE IF EXISTS ProfilingRequest CASCADE;
-- DROP TYPE IF EXISTS ProfilingMode CASCADE;
-- DROP TYPE IF EXISTS ProfilingStatus CASCADE;
-- DROP TYPE IF EXISTS CommandType CASCADE;
-- DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
```

## Docker Setup

If using Docker PostgreSQL:

```bash
# Start PostgreSQL container
docker run --name gprofiler-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=gprofiler \
  -p 5432:5432 \
  -d postgres:14

# Wait for PostgreSQL to start
sleep 5

# Apply schema
docker exec -i gprofiler-postgres \
  psql -U postgres -d gprofiler < dynamic_profiling_schema.sql

# Load test data (optional)
docker exec -i gprofiler-postgres \
  psql -U postgres -d gprofiler < test_dynamic_profiling.sql
```

## References

- **Main Documentation:** `docs/DYNAMIC_PROFILING.md`
- **Python Models:** `src/gprofiler/backend/models/dynamic_profiling_models.py`
- **Design Doc:** [Google Doc](https://docs.google.com/document/d/1iwA_NN1YKDBqfig95Qevw0HcSCqgu7_ya8PGuCksCPc/edit)

## Support

For issues or questions:
1. Check the main documentation: `docs/DYNAMIC_PROFILING.md`
2. Review test data script: `test_dynamic_profiling.sql`
3. Verify indexes are being used: `EXPLAIN ANALYZE your_query`




