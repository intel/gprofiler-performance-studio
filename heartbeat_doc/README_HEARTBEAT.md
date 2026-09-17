# gProfiler Performance Studio - Heartbeat-Based Profiling Control

This document describes the heartbeat-based profiling control system that allows dynamic start/stop of profiling sessions through API commands.

## Overview

The heartbeat system enables remote control of gProfiler agents through a simple yet robust mechanism:

1. **Agents send periodic heartbeats** to the Performance Studio backend
2. **Backend responds with profiling commands** (start/stop) when available
3. **Agents execute commands with built-in idempotency** to prevent duplicate execution
4. **Commands are tracked and logged** for audit and debugging
5. **Agents report hardware performance-counter (PMU) capabilities** so the backend can validate event-level profiling requests before dispatch

## Architecture

```
┌─────────────────────────────┐
│   gProfiler Agent           │
│                             │
│  ┌───────────────────────┐  │
│  │ ContinuousProfilerSlot│  │    heartbeat (POST /api/metrics/heartbeat)
│  └───────────────────────┘  │ ──────────────────────────────────────────►
│  ┌───────────────────────┐  │                                            │
│  │  AdhocProfilerSlot    │  │ ◄──────────────────────────────────────── │
│  └───────────────────────┘  │    commands + combined_config              │
│  ┌───────────────────────┐  │                                            │
│  │   CommandManager      │  │                               ┌────────────┴─────────────┐
│  │ (priority queue)      │  │                               │  Performance Studio      │
│  └───────────────────────┘  │                               │      Backend (FastAPI)   │
└─────────────────────────────┘                               │                          │
             │                                                │  - PMU event validation  │
             │ profile data                                   │  - Slack notifications   │
             ▼                                                │  - Capacity enforcement  │
┌─────────────────┐                                          └────────────┬─────────────┘
│  Profile Data   │                                                       │
│  (S3/Local)     │                                                       │
└─────────────────┘                                          ┌────────────▼─────────────┐
                                                             │   PostgreSQL DB           │
                                                             │   - HostHeartbeats        │
                                                             │   - ProfilingRequests     │
                                                             │   - ProfilingCommands     │
                                                             │   - ProfilingExecutions   │
                                                             └──────────────────────────┘
```

## Database Schema

### ENUMs

```sql
ProfilingMode          = ('cpu', 'allocation', 'none')
ProfilingRequestStatus = ('pending', 'assigned', 'completed', 'failed', 'cancelled')
CommandStatus          = ('pending', 'sent', 'completed', 'failed')
HostStatus             = ('active', 'idle', 'error', 'offline')
```

### `HostHeartbeats`

Tracks agent status and last-seen information. Upserted on `(hostname, service_name)` at every heartbeat.

| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial PK` | |
| `hostname` | `text NOT NULL` | |
| `ip_address` | `inet NOT NULL` | |
| `service_name` | `text NOT NULL` | |
| `last_command_id` | `uuid NULL` | Last command acknowledged by the agent |
| `received_command_ids` | `uuid[] NULL` | All command IDs the agent has received |
| `executed_command_ids` | `uuid[] NULL` | All command IDs the agent has executed |
| `status` | `HostStatus DEFAULT 'active'` | |
| `heartbeat_timestamp` | `timestamp` | Set by server on upsert |
| `supported_perf_events` | `text[] NULL` | PMU events reported by the agent; used for bulk request validation |
| `created_at` / `updated_at` | `timestamp` | |

Indexes: `hostname`, `service_name`, `status`, `heartbeat_timestamp`.

### `ProfilingRequests`

One row per API-level profiling request. Multiple requests for the same host are merged into a single `ProfilingCommands` row.

| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial PK` | |
| `request_id` | `uuid NOT NULL UNIQUE` | |
| `service_name` | `text NOT NULL` | |
| `request_type` | `text` | `'start'` or `'stop'` |
| `continuous` | `boolean DEFAULT false` | Whether the profiler should run in continuous mode |
| `duration` | `integer DEFAULT 60` | Seconds |
| `frequency` | `integer DEFAULT 11` | Hz |
| `profiling_mode` | `ProfilingMode DEFAULT 'cpu'` | |
| `target_hostnames` | `text[] NOT NULL` | |
| `pids` | `integer[] NULL` | **Deprecated** — always `NULL`; per-host PIDs are stored in the backend process memory (`DBManager.request_host_pid_mappings`) and lost on restart |
| `stop_level` | `text DEFAULT 'process'` | `'process'` or `'host'` |
| `additional_args` | `jsonb NULL` | Merged flat into `combined_config` |
| `status` | `ProfilingRequestStatus DEFAULT 'pending'` | |
| `estimated_completion_time` | `timestamp NULL` | |
| `created_at` / `updated_at` | `timestamp` | |

### `ProfilingCommands`

One active command per `(hostname, service_name)` pair. When a new request arrives for a host that already has a `pending` command, the configs are **merged** (max duration, max frequency, union of PIDs, OR of `continuous`) rather than replaced.

| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial PK` | |
| `command_id` | `uuid NOT NULL` | |
| `hostname` | `text NOT NULL` | |
| `service_name` | `text NOT NULL` | |
| `command_type` | `text` | `'start'` or `'stop'` |
| `request_ids` | `uuid[] NOT NULL` | All request UUIDs merged into this command |
| `combined_config` | `jsonb NULL` | Merged configuration delivered to the agent |
| `status` | `CommandStatus DEFAULT 'pending'` | `'pending'` → `'sent'` at heartbeat; `'completed'`/`'failed'` at completion |
| `sent_at` | `timestamp NULL` | Set when delivered via heartbeat response |
| `completed_at` | `timestamp NULL` | |
| `execution_time` | `integer NULL` | Seconds, as reported by the agent |
| `error_message` | `text NULL` | |
| `results_path` | `text NULL` | |

Unique constraint: `(hostname, service_name)` — one active command per host/service pair.

### `ProfilingExecutions`

Audit table. One row is inserted (with `status='assigned'`) when the command is delivered to the agent at heartbeat time — not at completion.

| Column | Type | Notes |
|---|---|---|
| `id` | `bigserial PK` | |
| `command_id` | `uuid NOT NULL` | |
| `hostname` | `text NOT NULL` | |
| `profiling_request_id` | `uuid FK → ProfilingRequests` | |
| `status` | `ProfilingRequestStatus DEFAULT 'pending'` | |
| `started_at` / `completed_at` | `timestamp NULL` | |
| `execution_time` | `integer NULL` | |
| `error_message` | `text NULL` | |
| `results_path` | `text NULL` | |

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/metrics/profile_request` | Create a profiling request for one or more hosts |
| `POST` | `/api/metrics/profile_request/bulk` | Create multiple profiling requests atomically |
| `POST` | `/api/metrics/heartbeat` | Agent heartbeat — returns pending commands |
| `POST` | `/api/metrics/command_completion` | Agent reports command execution result |
| `GET` | `/api/metrics/profiling/host_status` | Dashboard: per-host profiling status |

### 1. Create Profiling Request

```http
POST /api/metrics/profile_request
Content-Type: application/json
```

**Request:**

```json
{
  "service_name": "my-service",
  "request_type": "start",
  "continuous": false,
  "duration": 60,
  "frequency": 11,
  "profiling_mode": "cpu",
  "target_hosts": {
    "host1": [1234, 5678],
    "host2": null
  },
  "stop_level": "process",
  "additional_args": {},
  "dry_run": false
}
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `service_name` | yes | — | |
| `request_type` | yes | — | `"start"` or `"stop"` |
| `target_hosts` | yes | — | Dict of `hostname → [pids]` or `hostname → null` |
| `continuous` | no | `false` | Keep profiling running until an explicit stop |
| `duration` | no | `60` | Seconds; must be > 0 |
| `frequency` | no | `11` | Hz; must be > 0 |
| `profiling_mode` | no | `"cpu"` | `"cpu"`, `"allocation"`, or `"none"` |
| `stop_level` | no | `"process"` | `"process"` requires at least one host to have PIDs; `"host"` forbids PIDs |
| `additional_args` | no | `{}` | Merged flat into `combined_config` |
| `dry_run` | no | `false` | Validates and returns a response without writing to the database |

#### `additional_args.profiler_configs`

The `profiler_configs` key inside `additional_args` controls which profilers are enabled and how they run. All keys are optional; omitting a key uses the profiler's default.

**Async Profiler (Java)**

```json
"profiler_configs": {
  "async_profiler": {
    "enabled": true,
    "time": "cpu",
    "alloc_interval": "2MB"
  }
}
```

| Field | Default | Values | Notes |
|---|---|---|---|
| `enabled` | `true` | `true` / `false` | Set `false` to disable Java profiling entirely |
| `time` | `"cpu"` | `"cpu"`, `"itimer"`, `"wall"`, `"auto"`, `"alloc"` | Profiling mode for async-profiler (see table below) |
| `alloc_interval` | `"2MB"` | valid size string using bitmath notation e.g. `"2MB"`, `"512KiB"`, `"1GiB"` | Allocation interval; **required** when `time` is `"alloc"` |

| `time` value | Description |
|---|---|
| `"cpu"` | CPU time — samples only while the thread is on-CPU |
| `"itimer"` | Interval timer — uses OS `SIGPROF`; lower overhead than `cpu` |
| `"wall"` | Wall-clock time — includes threads blocked on I/O or locks |
| `"auto"` | Auto-select between `cpu` and `itimer` at runtime based on host capabilities |
| `"alloc"` | Allocation profiling — samples on heap allocations instead of time; `alloc_interval` controls the sampling granularity |

> **Validation:** The server rejects any `time` value outside the five listed above with HTTP 422. For `"alloc"` mode, `alloc_interval` must be a non-empty, parseable size string in bitmath notation (e.g. `"2MB"`, `"512KiB"`, `"1GiB"`); absent, empty, or malformed values (e.g. `"2 bananas"`, `"2mb"`) are rejected with HTTP 422.

**Other profilers** (`perf`, `pyperf`, `pyspy`, `phpspy`, `rbspy`, `dotnet_trace`, `nodejs_perf`) are unchanged and described in the Agent Integration section.

**Response:**

```json
{
  "success": true,
  "message": "Start profiling request submitted successfully for service 'my-service' across 2 hosts",
  "request_id": "req-uuid",
  "command_ids": ["cmd-uuid-host1", "cmd-uuid-host2"],
  "estimated_completion_time": "2026-03-04T10:30:00Z"
}
```

> **Note:** `command_ids` is a list — one UUID per target host. For `"stop"` requests `estimated_completion_time` is `null`. For `dry_run=true`, `request_id` is `null` and `command_ids` is empty.

### 2. Bulk Create Profiling Requests

Atomically submit multiple profiling requests. Capacity validation (`MAX_PROFILING_REQUEST_HOSTS`, `MAX_SIMULTANEOUS_PROFILING_HOSTS`) runs once across the entire batch before any individual request is processed.

```http
POST /api/metrics/profile_request/bulk
Content-Type: application/json
```

**Request:**

```json
{
  "requests": [
    { "service_name": "svc-a", "request_type": "start", "target_hosts": {"host1": null} },
    { "service_name": "svc-b", "request_type": "start", "target_hosts": {"host2": [1234]} }
  ],
  "dry_run": false
}
```

`dry_run` at the bulk level overrides every individual request's `dry_run`.

**Response:**

```json
{
  "total_submitted": 2,
  "successful_count": 2,
  "failed_count": 0,
  "results": [
    {
      "index": 0,
      "service_name": "svc-a",
      "success": true,
      "response": { "success": true, "request_id": "...", "command_ids": ["..."] },
      "error": null
    }
  ]
}
```

### 3. Agent Heartbeat

```http
POST /api/metrics/heartbeat
Content-Type: application/json
```

**Request:**

```json
{
  "hostname": "host1",
  "ip_address": "10.0.1.100",
  "service_name": "my-service",
  "last_command_id": "previous-command-uuid",
  "received_command_ids": ["uuid-a", "uuid-b"],
  "executed_command_ids": ["uuid-a"],
  "status": "active",
  "timestamp": "2026-03-04T10:00:00Z",
  "perf_supported_events": ["cpu-cycles", "cache-misses", "instructions"]
}
```

| Field | Required | Notes |
|---|---|---|
| `hostname` | yes | |
| `ip_address` | yes | |
| `service_name` | yes | |
| `last_command_id` | no | Last command ID the agent acknowledged |
| `received_command_ids` | no | All command IDs the agent has received (for fine-grained tracking) |
| `executed_command_ids` | no | All command IDs the agent has started executing |
| `status` | no | `"active"` (default), `"idle"`, or `"error"` |
| `timestamp` | no | ISO 8601; set by the server if absent |
| `perf_supported_events` | no | PMU events available on this host; used for bulk request validation |

**Response — no pending command:**

```json
{
  "success": true,
  "message": "Heartbeat received. No profiling commands.",
  "profiling_command": null,
  "command_id": null
}
```

**Response — command available:**

```json
{
  "success": true,
  "message": "Heartbeat received. New profiling command available.",
  "command_id": "cmd-uuid",
  "profiling_command": {
    "command_type": "start",
    "combined_config": {
      "continuous": false,
      "duration": 60,
      "frequency": 11,
      "profiling_mode": "cpu",
      "pids": [1234, 5678],
      "stop_level": "process"
    }
  }
}
```

> **Note:** `combined_config.pids` is a JSON integer array `[1234, 5678]`, not a comma-delimited string.

The heartbeat endpoint always returns HTTP 200. If an internal error occurs while looking up commands, the response body will contain `success: true` with an error message — it never returns 5xx from this path.

### 4. Command Completion

```http
POST /api/metrics/command_completion
Content-Type: application/json
```

**Request:**

```json
{
  "command_id": "cmd-uuid",
  "hostname": "host1",
  "status": "completed",
  "execution_time": 65,
  "error_message": null,
  "results_path": "/path/to/results"
}
```

| Field | Required | Notes |
|---|---|---|
| `command_id` | yes | |
| `hostname` | yes | |
| `status` | yes | `"completed"` or `"failed"` |
| `execution_time` | no | Seconds |
| `error_message` | no | Populated on `"failed"` status |
| `results_path` | no | |

**Response:**

```json
{
  "success": true,
  "message": "Command completion recorded for cmd-uuid"
}
```

Or, if the command is not found / not in `'assigned'` state for this host:

```json
{
  "success": false,
  "message": "Command cmd-uuid not found for host host1"
}
```

> **Note:** If the agent reports a `command_id` that no longer matches the host's current active command (i.e., a stale completion), `ProfilingRequests` status is not updated — only completions for the current active command trigger request status propagation.

### 5. Host Status Dashboard

```http
GET /api/metrics/profiling/host_status
```

Query parameters (all optional, repeatable): `service_name[]`, `hostname[]`, `ip_address[]`, `profiling_status[]`, `command_type[]`, `pids[]`, `exact_match`.

**Response:**

```json
{
  "hosts": [
    {
      "id": 1,
      "service_name": "my-service",
      "hostname": "host1",
      "ip_address": "10.0.1.100",
      "pids": [1234],
      "command_type": "start",
      "profiling_status": "sent",
      "heartbeat_timestamp": "2026-03-04T10:00:00Z"
    }
  ],
  "active_count": 1,
  "total_count": 5
}
```

`profiling_status` reflects the current `ProfilingCommands.status`. If no command exists for a host, it reports `"stopped"`.

## Agent Integration

### Two-Slot Architecture

The agent uses two independent execution slots so that non-overlapping profiler types can run in parallel:

```
DynamicGProfilerManager
├── continuous: ContinuousProfilerSlot   ← main continuous / single-run profiler
├── adhoc:   AdhocProfilerSlot        ← parallel ad-hoc profiler
└── command_manager: CommandManager   ← priority queue (stop > adhoc > continuous)
```

#### ContinuousProfilerSlot

Handles commands where `combined_config.continuous=true` or single-run commands sent to the continuous slot. Can be paused (preempted) when a new higher-priority command arrives, and will resume after the ad-hoc command finishes.

#### AdhocProfilerSlot

Handles ad-hoc (non-continuous) commands. Can run **in parallel** with `ContinuousProfilerSlot` if the two commands profile different runtime types (no overlapping profiler types). If there is overlap, the continuous command is paused (time-sliced) until the ad-hoc command completes.

Profiler type overlap is detected from `profiler_configs` keys using this mapping:

| Config Key | Canonical Type |
|---|---|
| `perf` | `perf` |
| `async_profiler` | `java` |
| `pyperf` / `pyspy` | `python` |
| `phpspy` | `php` |
| `rbspy` | `ruby` |
| `dotnet_trace` | `dotnet` |
| `nodejs_perf` | `nodejs` |

#### CommandManager Priority Queue

Three queues with fixed capacities. `get_next_command()` peeks (non-destructively) in priority order:

1. **Stop queue** (max 1) — processed immediately; clears all other queues
2. **Ad-hoc queue** (max 10)
3. **Continuous queue** (max 1) — if a second continuous command arrives, earlier pending continuous commands are silently discarded

Commands are dequeued by the profiler thread's `finally` block after the run completes. Paused continuous commands are deliberately kept in the queue so they can be resumed by the next heartbeat tick.

### Heartbeat Loop

Every `--heartbeat-interval` seconds the agent:

1. Sends `POST /api/metrics/heartbeat` with current state
2. If a command is returned, enqueues it (idempotency check against `received_command_ids`)
3. Cleans up any completed ad-hoc profiler threads
4. Peeks at the next command and dispatches it if conditions are met
5. Sleeps until next tick (interruptible)

Idempotency is enforced by two sets (`received_command_ids`, `executed_command_ids`) capped at 1000 entries each, trimmed by keeping the most recent entries.

### `send_command_completion` Timing

`POST /api/metrics/command_completion` is called when a profiler is **started** (not when it finishes). Consequently, `execution_time` is always sent as `0` from the agent. The actual duration is not reported back to the backend.

### Startup Command

```bash
python3 gprofiler/main.py \
  --enable-heartbeat-server \
  --upload-results \
  --api-server "https://perf-studio.example.com" \
  --service-name "my-service" \
  --token "api-token" \
  --heartbeat-interval 30
```

### CLI Reference

#### Heartbeat Flags (the `--enable-heartbeat-server` group requires all three starred flags)

| Flag | Default | Notes |
|---|---|---|
| `--enable-heartbeat-server` | off | Activates heartbeat mode; mutually exclusive with normal profiling |
| `--upload-results` / `-u` | off | ★ Required with `--enable-heartbeat-server` |
| `--token TOKEN` | — | ★ Required; sent as `Authorization: Bearer` on profile uploads |
| `--service-name NAME` | — | ★ Required |
| `--api-server URL` | (default address) | Backend base URL; `--server` is a deprecated alias |
| `--heartbeat-interval SECONDS` | `30` | Sleep between heartbeat POST requests |
| `--no-verify` | — | Skip TLS server certificate verification |

> **Note:** `--heartbeat-file PATH` is an **unrelated** feature — it touches a filesystem timestamp inside the normal snapshot loop as a liveness probe. It does not interact with the heartbeat protocol described here.

#### mTLS Flags

| Flag | Default | Notes |
|---|---|---|
| `--tls-client-cert PATH` | — | PEM client certificate |
| `--tls-client-key PATH` | — | PEM client private key; both cert and key must be provided for mTLS to activate |
| `--tls-ca-bundle PATH` | — | PEM CA bundle; overrides system CA store |
| `--tls-cert-refresh-enabled` | off | Enables background cert rotation thread |
| `--tls-cert-refresh-interval SECONDS` | `21600` | Cert refresh interval (default: 6 hours) |

## Data Flow Example

### 1. Create Profiling Request

Basic request (defaults):

```bash
curl -X POST http://localhost:8000/api/metrics/profile_request \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "web-service",
    "request_type": "start",
    "duration": 120,
    "target_hosts": {"web-01": null, "web-02": null},
    "profiling_mode": "cpu"
  }'
```

With explicit async-profiler mode (wall-clock):

```bash
curl -X POST http://localhost:8000/api/metrics/profile_request \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "web-service",
    "request_type": "start",
    "duration": 120,
    "target_hosts": {"web-01": null},
    "additional_args": {
      "profiler_configs": {
        "async_profiler": { "enabled": true, "time": "wall" }
      }
    }
  }'
```

Allocation profiling:

```bash
curl -X POST http://localhost:8000/api/metrics/profile_request \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "web-service",
    "request_type": "start",
    "duration": 60,
    "target_hosts": {"web-01": null},
    "additional_args": {
      "profiler_configs": {
        "async_profiler": { "enabled": true, "time": "alloc", "alloc_interval": "2MB" }
      }
    }
  }'
```

### 2. Agent Heartbeat (sent automatically by the agent)

```bash
curl -X POST http://localhost:8000/api/metrics/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "web-01",
    "ip_address": "10.0.1.10",
    "service_name": "web-service",
    "status": "active",
    "received_command_ids": [],
    "executed_command_ids": [],
    "perf_supported_events": ["cpu-cycles", "instructions"]
  }'
```

### 3. Agent Receives Command

```json
{
  "success": true,
  "command_id": "cmd-12345",
  "profiling_command": {
    "command_type": "start",
    "combined_config": {
      "duration": 120,
      "frequency": 11,
      "profiling_mode": "cpu",
      "continuous": false
    }
  }
}
```

### 4. Agent Reports Completion

```bash
curl -X POST http://localhost:8000/api/metrics/command_completion \
  -H "Content-Type: application/json" \
  -d '{
    "command_id": "cmd-12345",
    "hostname": "web-01",
    "status": "completed",
    "execution_time": 0
  }'
```

## Configuration

### Backend Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MAX_PROFILING_REQUEST_HOSTS` | `20` | Max number of target hosts per single profiling request |
| `MAX_SIMULTANEOUS_PROFILING_HOSTS` | `10` (%) | Max percentage of the total fleet that can be profiled simultaneously; enforced at bulk-request level |
| `ACTIVE_HOST_HEARTBEAT_MAX_DELTA_HOURS` | `24` | Hours of inactivity before a host is excluded from capacity calculations |
| `SLACK_BOT_TOKEN` | — | If set, Slack notifications are sent on every profiling request |
| `SLACK_CHANNELS` | `#gprofiler-notifications` | Comma-separated Slack channels for notifications |
| `METRICS_ENABLED` | `false` | Enable internal SLI metric publishing via ZMQ |
| `METRICS_AGENT_URL` | `tcp://localhost:18126` | ZMQ metrics agent address |
| `METRICS_SERVICE_NAME` | `gprofiler-webapp` | Service label for SLI metrics |

### Agent Configuration Summary

See the [CLI Reference](#cli-reference) above. The minimum viable invocation for heartbeat mode:

```bash
python3 gprofiler/main.py \
  --enable-heartbeat-server \
  --upload-results \
  --token "api-token" \
  --service-name "my-service" \
  --api-server "https://perf-studio.example.com"
```

## Monitoring and Debugging

### Database Queries

```sql
-- Check active hosts (default: hosts seen within last 24 hours)
SELECT hostname, service_name, status, heartbeat_timestamp
FROM HostHeartbeats
WHERE heartbeat_timestamp > NOW() - INTERVAL '24 hours'
ORDER BY heartbeat_timestamp DESC;

-- Check pending commands
SELECT hostname, service_name, command_type, status, created_at
FROM ProfilingCommands
WHERE status = 'pending';

-- Check command execution history
SELECT pe.hostname, pr.request_type, pe.status, pe.execution_time, pe.error_message
FROM ProfilingExecutions pe
JOIN ProfilingRequests pr ON pe.profiling_request_id = pr.request_id
ORDER BY pe.created_at DESC;
```

### Log Monitoring

```bash
# Backend logs
tail -f /var/log/gprofiler-studio/backend.log | grep -E "(heartbeat|command)"

# Agent logs
tail -f /tmp/gprofiler-heartbeat.log | grep -E "(heartbeat|command)"
```

## Testing

### Heartbeat System Tests

Test scripts are located in `heartbeat_doc/`:

```bash
cd gprofiler-performance-studio/heartbeat_doc
python3 test_heartbeat_system.py
```

This script:
- Simulates agent heartbeat behavior
- Creates test profiling requests
- Verifies command delivery and idempotency
- Tests both start and stop commands

### Run Test Agent

```bash
cd gprofiler-performance-studio/heartbeat_doc
python3 run_heartbeat_agent.py
```

## Troubleshooting

### Common Issues

1. **Agents not receiving commands**
   - Verify `service_name` matches exactly between the profiling request and the agent's `--service-name` flag
   - Confirm the agent's hostname appears in `target_hosts` in the profiling request
   - Check that the agent's heartbeat is reaching the backend (use the debug `curl` below)

2. **Commands executing multiple times**
   - The agent tracks `received_command_ids` and `executed_command_ids` across heartbeats; a process restart clears these in-memory sets, which can allow re-execution of previously seen commands
   - Check for rapid agent restarts

3. **Commands not appearing for the agent**
   - The command `status` may already be `'sent'` or `'completed'` from a previous heartbeat; only `'pending'` commands are dispatched
   - Ensure no stale `ProfilingCommands` row with `(hostname, service_name)` unique constraint is blocking new commands

4. **Bulk request rejected**
   - Check `MAX_PROFILING_REQUEST_HOSTS` (default 20) and `MAX_SIMULTANEOUS_PROFILING_HOSTS` (default 10%) limits
   - The bulk endpoint validates capacity across all requests in the batch before processing any of them

### Debug Commands

```bash
# Test backend connectivity
curl -s -X POST http://localhost:8000/api/metrics/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"hostname":"test","ip_address":"127.0.0.1","service_name":"test","status":"active"}' | python3 -m json.tool

# Check database state
psql -d gprofiler -c "SELECT hostname, service_name, status, heartbeat_timestamp FROM HostHeartbeats ORDER BY heartbeat_timestamp DESC LIMIT 10;"

# Check pending and sent commands
psql -d gprofiler -c "SELECT hostname, service_name, command_type, status, created_at, sent_at FROM ProfilingCommands WHERE status IN ('pending','sent') ORDER BY created_at DESC;"
```

## Security Considerations

1. **Authentication on heartbeat endpoints**: The `/api/metrics/heartbeat`, `/api/metrics/profile_request`, and `/api/metrics/command_completion` endpoints do **not** currently enforce authentication. The agent's `--token` flag is used for profile-upload API calls, not for the heartbeat protocol endpoints.
2. **Network**: Secure all communication with HTTPS. Use `--tls-client-cert` / `--tls-client-key` for mTLS where required.
3. **mTLS cert rotation**: Enable `--tls-cert-refresh-enabled` with an appropriate `--tls-cert-refresh-interval` to periodically rotate the client certificate without restarting the agent.
4. **TLS verification**: Never use `--no-verify` in production.
5. **Input Validation**: All request payloads are validated via Pydantic models; invalid inputs return HTTP 422.

## Performance Considerations

1. **Database Indexes**: All high-frequency lookup patterns (`hostname`, `service_name`, `status`, `heartbeat_timestamp`) are indexed.
2. **Heartbeat Frequency**: Default 30 s balances responsiveness against backend load. Reduce `--heartbeat-interval` for faster command pickup.
3. **Command Merging**: Multiple profiling requests for the same host are merged into a single `ProfilingCommands` row (max duration, max frequency, union of PIDs). This avoids parallel command dispatch to the same host.
4. **Connection Pooling**: Use connection pooling (e.g., PgBouncer) for database access at scale.
5. **Capacity Limits**: `MAX_SIMULTANEOUS_PROFILING_HOSTS` prevents fleet-wide profiling storms; tune this percentage for your environment.
