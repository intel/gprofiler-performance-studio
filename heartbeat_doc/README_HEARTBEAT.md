# gProfiler Performance Studio - Heartbeat-Based Profiling Control

This document describes the heartbeat-based profiling control system that allows dynamic start/stop of profiling sessions through API commands.

## Overview

The heartbeat system enables remote control of gProfiler agents through a simple yet robust mechanism:

1. **Agents send periodic heartbeats** to the Performance Studio backend
2. **Backend responds with profiling commands** (start/stop) when available
3. **Agents execute commands with built-in idempotency** to prevent duplicate execution
4. **Commands are tracked and logged** for audit and debugging

## Architecture

```
┌─────────────────┐    heartbeat     ┌──────────────────────┐
│   gProfiler     │ ──────────────► │  Performance Studio  │
│    Agent        │                 │      Backend         │
│                 │ ◄────────────── │                      │
└─────────────────┘   commands      └──────────────────────┘
        │                                       │
        │                                       │
        ▼                                       ▼
┌─────────────────┐                 ┌──────────────────────┐
│  Profile Data   │                 │   PostgreSQL DB      │
│  (S3/Local)     │                 │   - Host Heartbeats  │
└─────────────────┘                 │   - Profiling Cmds   │
                                    └──────────────────────┘
```

## Database Schema

### Core Tables

1. **HostHeartbeats** - Track agent status and last seen information
2. **ProfilingRequests** - Store profiling requests from API calls
3. **ProfilingCommands** - Commands sent to agents (merged from multiple requests)
4. **ProfilingExecutions** - Execution history for audit trail

### Key Features
- **Simple DDL** with essential indexes only
- **No stored procedures** - all logic in application code
- **No triggers** - timestamps handled by application
- **Consistent naming** with `idx_` prefix for all indexes

## API Endpoints

### 1. Create Profiling Request
```http
POST /api/metrics/profile_request
Content-Type: application/json

{
  "service_name": "my-service",
  "request_type": "start",
  "duration": 60,
  "frequency": 11,
  "profiling_mode": "cpu",
  "target_hosts": {
    "host1": [1234, 5678],
    "host2": null
  },
  "stop_level": "process",
  "additional_args": {}
}
```

**Response:**
```json
{
  "success": true,
  "message": "Start profiling request submitted successfully",
  "request_id": "uuid",
  "command_id": "uuid",
  "estimated_completion_time": "2025-01-15T10:30:00Z"
}
```

### 2. Agent Heartbeat
```http
POST /api/metrics/heartbeat
Content-Type: application/json

{
  "hostname": "host1",
  "ip_address": "10.0.1.100",
  "service_name": "my-service",
  "last_command_id": "previous-command-uuid",
  "status": "active"
}
```

**Response (with command):**
```json
{
  "success": true,
  "message": "Heartbeat received. New profiling command available.",
  "command_id": "new-command-uuid",
  "profiling_command": {
    "command_type": "start",
    "combined_config": {
      "duration": 60,
      "frequency": 11,
      "profiling_mode": "cpu",
      "pids": "1234,5678"
    }
  }
}
```

### 3. Command Completion
```http
POST /api/metrics/command_completion
Content-Type: application/json

{
  "command_id": "command-uuid",
  "hostname": "host1",
  "status": "completed",
  "execution_time": 65,
  "results_path": "/path/to/results"
}
```

## Agent Integration

### Heartbeat Configuration
```bash
python3 gprofiler/main.py \
  --enable-heartbeat-server \
  --api-server "https://perf-studio.example.com" \
  --heartbeat-interval 30 \
  --service-name "my-service" \
  --token "api-token"
```

### Heartbeat Flow
1. **Agent sends heartbeat** every 30 seconds (configurable)
2. **Backend checks for pending commands** for this hostname/service
3. **If command available**, backend responds with command details
4. **Agent executes command** and reports completion
5. **Idempotency ensured** by tracking `last_command_id`

## Command Types

### START Commands
- Create new profiling sessions
- Merge multiple requests for same host
- Include combined configuration (duration, frequency, PIDs)

### STOP Commands
- **Process-level**: Stop specific PIDs
- **Host-level**: Stop entire profiling session
- Automatic conversion when only one PID remains

## Data Flow Example

### 1. Create Profiling Request
```bash
curl -X POST http://localhost:8000/api/metrics/profile_request \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "web-service",
    "request_type": "start",
    "duration": 120,
    "target_hostnames": ["web-01", "web-02"],
    "profiling_mode": "cpu"
  }'
```

### 2. Agent Heartbeat
```bash
# Agent automatically sends:
curl -X POST http://localhost:8000/api/metrics/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "web-01",
    "ip_address": "10.0.1.10",
    "service_name": "web-service",
    "status": "active"
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
      "profiling_mode": "cpu"
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
    "execution_time": 122
  }'
```

## Testing

### 1. Test Heartbeat System
```bash
cd gprofiler-performance-studio
python3 test_heartbeat_system.py
```

This script:
- Simulates agent heartbeat behavior
- Creates test profiling requests
- Verifies command delivery and idempotency
- Tests both start and stop commands

### 2. Run Test Agent
```bash
python3 run_heartbeat_agent.py
```

This script:
- Starts a real gProfiler agent in heartbeat mode
- Connects to the Performance Studio backend
- Receives and executes actual profiling commands

## Configuration

### Backend Configuration
```yaml
# Backend settings
database:
  host: localhost
  port: 5432
  database: gprofiler
  
heartbeat:
  max_age_minutes: 10  # Consider hosts offline after 10 minutes
  cleanup_interval: 300  # Clean up old records every 5 minutes
```

### Agent Configuration
```bash
# Required parameters
--enable-heartbeat-server          # Enable heartbeat mode
--api-server URL                   # Performance Studio backend URL
--service-name NAME                # Service identifier
--heartbeat-interval SECONDS       # Heartbeat frequency (default: 30)

# Optional parameters
--token TOKEN                      # Authentication token
--server-host URL                  # Profile upload server (can be same as api-server)
--no-verify                        # Skip SSL verification (testing only)
```

## Monitoring and Debugging

### Database Queries
```sql
-- Check active hosts
SELECT hostname, service_name, status, heartbeat_timestamp 
FROM HostHeartbeats 
WHERE status = 'active' AND heartbeat_timestamp > NOW() - INTERVAL '10 minutes';

-- Check pending commands
SELECT hostname, service_name, command_type, status, created_at 
FROM ProfilingCommands 
WHERE status = 'pending';

-- Check command execution history
SELECT pe.hostname, pr.request_type, pe.status, pe.execution_time
FROM ProfilingExecutions pe
JOIN ProfilingRequests pr ON pe.profiling_request_id = pr.ID
ORDER BY pe.created_at DESC;
```

### Log Monitoring
```bash
# Backend logs
tail -f /var/log/gprofiler-studio/backend.log | grep -E "(heartbeat|command)"

# Agent logs  
tail -f /tmp/gprofiler-heartbeat.log | grep -E "(heartbeat|command)"
```

## Troubleshooting

### Common Issues

1. **Agents not receiving commands**
   - Check heartbeat connectivity to backend
   - Verify service_name matches between request and agent
   - Check agent authentication (token)

2. **Commands executing multiple times**
   - Verify agent is tracking `last_command_id` correctly
   - Check for agent restarts that reset command tracking

3. **Commands not being created**
   - Verify `target_hostnames` includes the agent's hostname
   - Check database constraints and foreign key relationships

### Debug Commands
```bash
# Test backend connectivity
curl -v http://localhost:8000/api/metrics/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"hostname":"test","ip_address":"127.0.0.1","service_name":"test","status":"active"}'

# Check database state
psql -d gprofiler -c "SELECT * FROM HostHeartbeats ORDER BY heartbeat_timestamp DESC LIMIT 5;"
```

## Security Considerations

1. **Authentication**: Use API tokens for agent authentication
2. **Network**: Secure communication with HTTPS/TLS
3. **Authorization**: Validate service permissions before creating commands
4. **Rate Limiting**: Implement rate limits on heartbeat endpoints
5. **Input Validation**: Sanitize all input parameters

## Performance Considerations

1. **Database Indexes**: Essential indexes are created for all lookup patterns
2. **Heartbeat Frequency**: Balance between responsiveness and load (default: 30s)
3. **Command Cleanup**: Implement periodic cleanup of old commands/executions
4. **Connection Pooling**: Use connection pooling for database access

## Future Enhancements

1. **Agent Discovery**: Automatic service registration
2. **Command Queuing**: Support for command queues per host
3. **Conditional Commands**: Commands based on host metrics or state
4. **Command Templates**: Predefined command templates for common scenarios
5. **Real-time Dashboard**: Web UI for monitoring active agents and commands
