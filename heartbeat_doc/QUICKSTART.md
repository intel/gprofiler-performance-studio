# Quick Start Guide - Heartbeat-Based Profiling

This guide helps you quickly test the heartbeat-based profiling control system.

## Prerequisites

1. **Performance Studio Backend** running on `http://localhost:5000`
2. **PostgreSQL database** with heartbeat tables created
3. **Python dependencies** installed (`requests`, `fastapi`, etc.)

## Step 1: Start the Backend

```bash
# Start the Performance Studio backend
cd gprofiler-performance-studio
./src/run_local.sh  # This starts on port 5000
```

## Step 2: Validate API

```bash
# From the heartbeat_doc directory
cd heartbeat_doc
python3 validate_api.py
```

Expected output:
```
🧪 Testing Heartbeat API Endpoints
==================================================

1️⃣  Testing valid profiling request...
✅ Valid request successful
   Request ID: abc-123
   Command ID: def-456

2️⃣  Testing invalid request (missing target_hostnames)...
✅ Invalid request correctly rejected with 422

3️⃣  Testing heartbeat request...
✅ Heartbeat successful
   Message: Heartbeat received. New profiling command available.
   Command received: def-456
```

## Step 3: Test Full System

```bash
# Run the comprehensive test from heartbeat_doc directory
cd heartbeat_doc
python3 test_heartbeat_system.py
```

This will:
- Create profiling requests via API
- Simulate agent heartbeats
- Verify command delivery and idempotency
- Test both start and stop commands

## Step 4: Run Real Agent (Optional)

```bash
# Run actual gProfiler agent in heartbeat mode from heartbeat_doc directory
cd heartbeat_doc
python3 run_heartbeat_agent.py
```

## Troubleshooting

### "Connection refused" errors
- Ensure backend is running on `http://localhost:5000`
- Check firewall settings

### "target_hostnames required" errors
- ✅ This is expected for invalid requests
- Ensure you include `target_hostnames` in valid requests

### "No pending commands" in heartbeat
- ✅ This is normal when no profiling requests are active
- Create a profiling request first, then send heartbeat

### Database errors
- Ensure PostgreSQL is running
- Verify heartbeat tables exist (run DDL script)
- Check database connection settings

## Example Commands

### Create a START request
```bash
curl -X POST http://localhost:5000/api/metrics/profile_request \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "my-service",
    "request_type": "start",
    "duration": 60,
    "target_hostnames": ["host1"]
  }'
```

### Send a heartbeat
```bash
curl -X POST http://localhost:5000/api/metrics/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "host1",
    "ip_address": "127.0.0.1",
    "service_name": "my-service",
    "status": "active"
  }'
```

### Create a STOP request
```bash
curl -X POST http://localhost:5000/api/metrics/profile_request \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "my-service",
    "request_type": "stop",
    "target_hostnames": ["host1"],
    "stop_level": "host"
  }'
```

## Files Updated

- ✅ **metrics_routes.py** - Fixed field validation and imports
- ✅ **test_heartbeat_system.py** - Updated to use `request_type` 
- ✅ **validate_api.py** - Quick API validation script
- ✅ **README_HEARTBEAT.md** - Comprehensive documentation
- ✅ **Database DDL** - Simplified schema without stored procedures

All test files are now consistent with the simplified heartbeat implementation!
