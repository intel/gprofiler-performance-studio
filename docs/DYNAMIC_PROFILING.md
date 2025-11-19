# Dynamic Profiling Data Model

## Overview

The Dynamic Profiling feature enables profiling requests at various hierarchy levels (service, job, namespace) to be mapped to specific host-level commands while maintaining sub-second heartbeat response times for 165k QPM (Queries Per Minute).

## Architecture

The dynamic profiling system consists of:

1. **Profiling Requests** - API-level requests specifying targets at various hierarchy levels
2. **Profiling Commands** - Host-specific commands sent to agents
3. **Host Heartbeats** - Real-time host availability tracking (optimized for 165k QPM)
4. **Profiling Executions** - Audit trail of profiling executions
5. **Hierarchical Mappings** - Denormalized tables for fast query performance

## Data Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    DYNAMIC PROFILING DATA MODEL                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐         ┌──────────────────────┐        │
│  │ ProfilingRequest │────────▶│ ProfilingCommand     │        │
│  │                  │         │                      │        │
│  │ - Request ID     │         │ - Command ID         │        │
│  │ - Service/Job/   │         │ - Host ID (indexed)  │        │
│  │   Namespace/Pod  │         │ - Target Containers  │        │
│  │ - Duration       │         │ - Target Processes   │        │
│  │ - Sample Rate    │         │ - Command Type       │        │
│  │ - Status         │         │ - Status             │        │
│  └──────────────────┘         └──────────────────────┘        │
│           │                            │                       │
│           │                            │                       │
│           ▼                            ▼                       │
│  ┌──────────────────────┐    ┌─────────────────┐             │
│  │ ProfilingExecutions  │    │ HostHeartbeats  │             │
│  │ (Audit Trail)        │    │                 │             │
│  │                      │    │ - Host ID       │             │
│  │ - Execution ID       │    │ - Service       │             │
│  │ - Request/Command    │    │ - Containers    │             │
│  │ - Host Name          │    │ - Workloads     │             │
│  │ - Status             │    │ - Last Seen ⚡   │             │
│  └──────────────────────┘    └─────────────────┘             │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │         HIERARCHICAL MAPPING TABLES                    │  │
│  │  (Denormalized for Fast Query Performance)             │  │
│  ├────────────────────────────────────────────────────────┤  │
│  │                                                         │  │
│  │  • NamespaceServices    - Namespace → Service          │  │
│  │  • ServiceContainers    - Service → Container          │  │
│  │  • JobContainers        - Job → Container              │  │
│  │  • ContainerProcesses   - Container → Process          │  │
│  │  • ContainersHosts      - Container → Host             │  │
│  │  • ProcessesHosts       - Process → Host               │  │
│  │                                                         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                                │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Hierarchical Request Mapping

Requests can target any level of the hierarchy:
- **Namespace Level**: Profile all services in a namespace
- **Service Level**: Profile all containers in a service
- **Job Level**: Profile specific job workloads
- **Container Level**: Profile specific containers
- **Process Level**: Profile specific processes
- **Host Level**: Profile specific hosts

### 2. Sub-Second Heartbeat Performance

The `HostHeartbeats` table is optimized for 165k QPM:
- Indexed on `host_id` for O(1) lookups
- Indexed on `timestamp_last_seen` for quick staleness checks
- Partial indexes on `service_name` and `namespace` for filtered queries
- Lightweight updates with minimal locking

### 3. Audit Trail

`ProfilingExecutions` table maintains complete audit history:
- Links to original requests and commands
- Tracks execution lifecycle
- Enables troubleshooting and compliance

### 4. Denormalized Mappings

Hierarchical mapping tables trade storage for query speed:
- Pre-computed relationships
- Eliminates complex JOINs
- Enables fast request-to-host resolution

## Database Tables

### Core Tables

#### ProfilingRequest
Stores profiling requests from API calls.

**Key Fields:**
- `request_id` (UUID) - Unique identifier
- `service_name`, `job_name`, `namespace`, etc. - Target specification
- `profiling_mode` - CPU, memory, allocation, native
- `duration_seconds` - How long to profile
- `sample_rate` - Sampling frequency (1-1000)
- `status` - pending, in_progress, completed, failed, cancelled

**Constraints:**
- At least one target specification must be provided
- Duration must be positive
- Sample rate must be between 1 and 1000

#### ProfilingCommand
Commands sent to agents on specific hosts.

**Key Fields:**
- `command_id` (UUID) - Unique identifier
- `profiling_request_id` - Links to original request
- `host_id` - Target host (indexed for fast lookup)
- `target_containers`, `target_processes` - Specific targets
- `command_type` - start, stop, reconfigure
- `command_json` - Serialized command for agent

#### HostHeartbeats
Tracks host availability and status.

**Key Fields:**
- `host_id` - Unique host identifier (indexed)
- `host_name`, `host_ip` - Host details
- `service_name`, `namespace` - Contextual info
- `containers`, `jobs`, `workloads` - Current state
- `timestamp_last_seen` - Last heartbeat (indexed)
- `last_command_id` - Last command received

**Performance:**
- Designed for 165k QPM
- Sub-second response times
- Optimized indexes for common queries

#### ProfilingExecutions
Audit trail of profiling executions.

**Key Fields:**
- `execution_id` (UUID) - Unique identifier
- `profiling_request_id` - Original request
- `profiling_command_id` - Executed command
- `host_name` - Where it executed
- `started_at`, `completed_at` - Execution timeline
- `status` - Execution status

### Mapping Tables

All mapping tables follow a similar pattern:
- Primary key (ID)
- Mapping fields (indexed)
- Timestamps (created_at, updated_at)
- Unique constraint on the mapping

#### NamespaceServices
Maps namespaces → services

#### ServiceContainers
Maps services → containers

#### JobContainers
Maps jobs → containers

#### ContainerProcesses
Maps containers → processes (includes process name)

#### ContainersHosts
Maps containers → hosts

#### ProcessesHosts
Maps processes → hosts

## Setup and Installation

### 1. Apply Database Schema

```bash
# Connect to PostgreSQL
psql -U postgres -d gprofiler

# Run the schema
\i scripts/setup/postgres/dynamic_profiling_schema.sql
```

### 2. Verify Tables Created

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name LIKE '%profiling%' 
   OR table_name LIKE '%heartbeat%';
```

Expected tables:
- profilingrequest
- profilingcommand
- hostheartbeats
- profilingexecutions
- namespaceservices
- servicecontainers
- jobcontainers
- containerprocesses
- containershosts
- processeshosts

### 3. Verify Indexes

```sql
SELECT tablename, indexname 
FROM pg_indexes 
WHERE tablename IN ('profilingrequest', 'profilingcommand', 'hostheartbeats', 'profilingexecutions')
ORDER BY tablename, indexname;
```

## API Models

Python Pydantic models are available in:
```
src/gprofiler/backend/models/dynamic_profiling_models.py
```

### Key Models

#### Request Models
- `ProfilingRequestCreate` - Create new profiling request
- `ProfilingRequestResponse` - Response with all fields
- `ProfilingRequestUpdate` - Update request status

#### Command Models
- `ProfilingCommandCreate` - Create command for agent
- `ProfilingCommandResponse` - Command details
- `ProfilingCommandUpdate` - Update command status

#### Heartbeat Models
- `HostHeartbeatCreate` - Register/update host heartbeat
- `HostHeartbeatResponse` - Heartbeat details
- `HostHeartbeatUpdate` - Update heartbeat timestamp

#### Execution Models
- `ProfilingExecutionCreate` - Create audit entry
- `ProfilingExecutionResponse` - Execution details
- `ProfilingExecutionUpdate` - Update execution status

#### Query Models
- `ProfilingRequestQuery` - Filter profiling requests
- `HostHeartbeatQuery` - Filter heartbeats
- `ProfilingExecutionQuery` - Filter executions

## Usage Examples

### Creating a Profiling Request

```python
from dynamic_profiling_models import ProfilingRequestCreate, ProfilingMode
from datetime import datetime, timedelta

# Profile all containers in a service
request = ProfilingRequestCreate(
    service_name="web-api",
    profiling_mode=ProfilingMode.CPU,
    duration_seconds=60,
    sample_rate=100,
    start_time=datetime.utcnow(),
    stop_time=datetime.utcnow() + timedelta(seconds=60)
)
```

### Recording a Host Heartbeat

```python
from dynamic_profiling_models import HostHeartbeatCreate

heartbeat = HostHeartbeatCreate(
    host_id="host-12345",
    host_name="worker-node-01",
    host_ip="10.0.1.42",
    service_name="web-api",
    namespace="production",
    containers=["web-api-container-1", "web-api-container-2"],
    jobs=["data-processing-job"],
    executors=["pyspy", "perf"]
)
```

### Querying Active Hosts

```python
from dynamic_profiling_models import HostHeartbeatQuery
from datetime import datetime, timedelta

# Find hosts seen in last 5 minutes in production namespace
query = HostHeartbeatQuery(
    namespace="production",
    last_seen_after=datetime.utcnow() - timedelta(minutes=5),
    limit=100
)
```

## Performance Considerations

### Heartbeat Optimization (165k QPM Target)

1. **Use Connection Pooling**: Minimize connection overhead
2. **Batch Updates**: Update multiple heartbeats in single transaction
3. **Index Usage**: Queries should use `host_id` or `timestamp_last_seen` indexes
4. **Avoid Full Scans**: Always filter on indexed columns

### Query Performance

1. **Use Denormalized Tables**: Mapping tables eliminate expensive JOINs
2. **Limit Result Sets**: Always use pagination with `limit` and `offset`
3. **Index Coverage**: Ensure queries can use existing indexes
4. **Monitor Query Plans**: Use `EXPLAIN ANALYZE` to verify performance

### Maintenance

1. **Regular VACUUM**: Prevent table bloat on frequently updated tables
2. **Analyze Statistics**: Keep query planner statistics up to date
3. **Monitor Index Usage**: Check `pg_stat_user_indexes`
4. **Archive Old Data**: Consider partitioning or archiving old executions

## Migration Path

### Phase 1: Schema Deployment (Current)
✅ Create database tables
✅ Create Python models
✅ Add indexes and constraints

### Phase 2: API Endpoints (Next)
- POST /api/profiling/requests
- GET /api/profiling/requests
- POST /api/profiling/heartbeats
- GET /api/profiling/heartbeats
- GET /api/profiling/executions

### Phase 3: Agent Integration
- Agent heartbeat loop
- Command polling/pulling
- Execution reporting

### Phase 4: Request Resolution
- Map requests to hosts
- Generate host commands
- Track execution lifecycle

## References

- Google Doc: [Dynamic Profiling Design](https://docs.google.com/document/d/1iwA_NN1YKDBqfig95Qevw0HcSCqgu7_ya8PGuCksCPc/edit)
- SQL Schema: `scripts/setup/postgres/dynamic_profiling_schema.sql`
- Python Models: `src/gprofiler/backend/models/dynamic_profiling_models.py`

## Contributing to Intel Open Source

This implementation is part of gProfiler Performance Studio's contribution to Intel's open source initiative. The dynamic profiling capability will enable:

1. **Hierarchical Profiling**: Profile at any level (namespace, service, job, container, process, host)
2. **Scalability**: Support 165k QPM with sub-second response times
3. **Auditability**: Complete execution history for compliance and troubleshooting
4. **Flexibility**: Extensible architecture for future profiling modes

## License

Copyright (C) 2023 Intel Corporation

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.




