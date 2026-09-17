# PerfSpect Integration with Dynamic Profiling

<!--- Provide a general summary of your changes in the Title above -->

## Description
<!--- Describe your changes in detail -->

This feature integrates Intel PerfSpect hardware metrics collection with the gProfiler dynamic profiling system. It enables users to collect detailed hardware performance metrics (CPU utilization, memory bandwidth, cache statistics, etc.) alongside traditional CPU profiling data through a simple UI checkbox.

The integration provides:
- **UI Control**: A "PerfSpect HW Metrics" checkbox in the dynamic profiling interface
- **Auto-Installation**: Automatic PerfSpect binary download and setup on target agents
- **Seamless Integration**: Hardware metrics collection runs alongside CPU profiling
- **Centralized Management**: Control PerfSpect across multiple hosts from a single interface

## Related Issue
<!--- If there's an issue related, please link it here -->
<!--- If suggesting a new feature or a medium/big change, please discuss it in an issue first. -->
<!--- For small changes, it's okay to open a PR immediately. -->

This feature addresses the need for comprehensive performance analysis by combining CPU profiling with hardware-level metrics, enabling deeper insights into application performance bottlenecks.

## Motivation and Context
<!--- Why is this change required? What problem does it solve? What does it improve? -->

### Problem Solved
- **Limited Visibility**: Traditional CPU profiling only shows software-level performance, missing hardware bottlenecks
- **Manual Setup**: Previously required manual PerfSpect installation and configuration on each host
- **Fragmented Workflow**: Hardware metrics and CPU profiles were collected separately
- **Scalability Issues**: Difficult to enable hardware metrics collection across large deployments

### Improvements Delivered
- **Unified Interface**: Single UI to control both CPU profiling and hardware metrics
- **Zero-Touch Deployment**: Automatic PerfSpect installation eliminates manual setup
- **Enhanced Analysis**: Combined hardware and software metrics provide complete performance picture
- **Enterprise Scale**: Easily enable hardware metrics across hundreds of hosts simultaneously

## How Has This Been Tested?
<!--- Please describe in detail how you tested your changes. -->
<!--- Include details of your testing environment, and the tests you ran to -->
<!--- see how your change affects other areas of the code, etc. -->
<!--- If your changes are tested by the CI, you can just write that.-->

### Testing Environment
- **Local Development**: Docker Compose setup with PostgreSQL and ClickHouse
- **Test Services**: `test-service-1`, `test-service-2`
- **Test Hosts**: `test-host-001`, `test-host-202`, `test-host-1`

### Test Cases Executed

#### 1. UI Integration Testing
- ✅ **Checkbox Visibility**: Verified PerfSpect checkbox appears in dynamic profiling interface
- ✅ **Tooltip Functionality**: Confirmed tooltip displays helpful information about PerfSpect
- ✅ **State Management**: Tested checkbox state persistence and reset behavior
- ✅ **UX Improvement**: Verified checkbox auto-unchecks after profiling request submission

#### 2. API Integration Testing
- ✅ **Request Handling**: Tested API accepts `additional_args` with `enable_perfspect: true`
- ✅ **Data Persistence**: Verified profiling requests save PerfSpect settings to database
- ✅ **Error Handling**: Confirmed graceful handling of malformed requests

#### 3. Database Integration Testing
- ✅ **Schema Compatibility**: Verified `additional_args` JSONB field stores PerfSpect configuration
- ✅ **Query Performance**: Tested retrieval of PerfSpect settings from profiling requests
- ✅ **Data Integrity**: Confirmed proper JSON serialization/deserialization

#### 4. Command Generation Testing
- ✅ **Config Merging**: Verified `additional_args` merges into top-level `combined_config`
- ✅ **Agent Compatibility**: Confirmed `enable_perfspect: true` appears at correct config level
- ✅ **Command Persistence**: Tested profiling commands save with proper PerfSpect configuration

#### 5. End-to-End Integration Testing
```bash
# Test Case: Create profiling request with PerfSpect enabled
curl -X POST http://localhost:8080/api/metrics/profile_request \
  -u "prashantpatel:password" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "test-service-2",
    "request_type": "start",
    "continuous": true,
    "duration": 60,
    "frequency": 11,
    "profiling_mode": "cpu",
    "target_hosts": {
      "test-host-202": null
    },
    "additional_args": {
      "enable_perfspect": true
    }
  }'

# Verification: Check database entries
SELECT combined_config FROM ProfilingCommands 
WHERE service_name = 'test-service-2' AND hostname = 'test-host-202';

# Result: {"enable_perfspect": true, ...} ✅
```

#### 6. Agent Integration Testing
- ✅ **Heartbeat Protocol**: Verified agents receive PerfSpect configuration via heartbeat
- ✅ **Auto-Installation**: Confirmed PerfSpect binary downloads and extracts correctly
- ✅ **Command Generation**: Tested gProfiler starts with `--enable-hw-metrics-collection`
- ✅ **Path Configuration**: Verified `--perfspect-path` points to auto-installed binary

## Screenshots
<!--- (if appropriate) -->

### Dynamic Profiling Interface with PerfSpect Checkbox
```
┌─────────────────────────────────────────────────────────────┐
│ [Start (2)] [Stop (0)] [Refresh] ☑ PerfSpect HW Metrics   │
│                                    ℹ Enable Intel PerfSpect│
│                                      hardware metrics       │
│                                      collection             │
└─────────────────────────────────────────────────────────────┘
```

### Database Schema - ProfilingRequests Table
```sql
CREATE TABLE ProfilingRequests (
    request_id uuid NOT NULL,
    service_name text NOT NULL,
    request_type text NOT NULL,
    continuous boolean NOT NULL DEFAULT false,
    duration integer NULL DEFAULT 60,
    frequency integer NULL DEFAULT 11,
    profiling_mode ProfilingMode NOT NULL DEFAULT 'cpu',
    target_hostnames text[] NOT NULL,
    pids integer[] NULL,
    stop_level text NULL DEFAULT 'process',
    additional_args jsonb NULL,  -- ← PerfSpect config stored here
    status ProfilingRequestStatus NOT NULL DEFAULT 'pending',
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Combined Config Example
```json
{
  "duration": 60,
  "frequency": 11,
  "continuous": true,
  "command_type": "start",
  "profiling_mode": "cpu",
  "enable_perfspect": true  // ← Agent reads this flag
}
```

## Architecture Overview

### Component Flow
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Frontend  │───▶│   Backend   │───▶│  Database   │───▶│    Agent    │
│     UI      │    │     API     │    │ PostgreSQL  │    │ gProfiler   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                    │                    │                    │
      │ ☑ PerfSpect       │ additional_args    │ combined_config    │ --enable-hw-
      │   Checkbox        │ {"enable_perfspect"│ {"enable_perfspect"│   metrics-collection
      │                   │  : true}           │  : true}           │ --perfspect-path=...
```

### Data Flow
1. **User Action**: Checks PerfSpect checkbox and clicks "Start"
2. **API Request**: Frontend sends `additional_args: {"enable_perfspect": true}`
3. **Database Storage**: Backend saves request with PerfSpect configuration
4. **Command Generation**: System creates profiling command with merged config
5. **Agent Heartbeat**: Agent receives command with `enable_perfspect: true`
6. **Auto-Installation**: Agent downloads and installs PerfSpect binary
7. **Metrics Collection**: gProfiler starts with hardware metrics enabled

## Implementation Details

### Frontend Changes
- **File**: `src/gprofiler/frontend/src/components/console/header/ProfilingTopPanel.jsx`
  - Added PerfSpect checkbox with tooltip
  - Integrated with Material-UI components
- **File**: `src/gprofiler/frontend/src/components/console/ProfilingStatusPage.jsx`
  - Added state management for PerfSpect checkbox
  - Implemented auto-reset UX improvement
  - Integrated PerfSpect setting into API requests

### Backend Changes
- **File**: `src/gprofiler/backend/routers/metrics_routes.py`
  - Enhanced `/profile_request` endpoint to handle `additional_args`
  - Maintained backward compatibility with existing API
- **File**: `src/gprofiler-dev/gprofiler_dev/postgres/db_manager.py`
  - Updated `_get_profiling_request_details` to include `additional_args`
  - Enhanced `_build_combined_config` to merge `additional_args` into top-level config
  - Fixed database schema compatibility issues

### Agent Changes
- **File**: `gprofiler/gprofiler/heartbeat.py`
  - Enhanced `_create_profiler_args` to read `enable_perfspect` from config
  - Integrated PerfSpect auto-installation workflow
  - Added proper error handling for installation failures
- **File**: `gprofiler/gprofiler/perfspect_installer.py`
  - Implemented automatic PerfSpect download and extraction
  - Added binary verification and path resolution
  - Included timeout and error handling

## Configuration

### Environment Variables
```bash
# PerfSpect download URL (default: GitHub releases)
PERFSPECT_DOWNLOAD_URL="https://github.com/intel/PerfSpect/releases/latest/download/perfspect.tgz"

# Installation timeout in seconds (default: 300)
PERFSPECT_INSTALL_TIMEOUT=300

# Temporary directory for PerfSpect installation
TMPDIR="/tmp"
```

### Agent Command Line
When PerfSpect is enabled, the agent starts with:
```bash
gprofiler \
  --enable-hw-metrics-collection \
  --perfspect-path="/tmp/perfspect/perfspect -o /tmp" \
  [other profiling options...]
```

## Troubleshooting

### Common Issues

#### 1. PerfSpect Checkbox Not Visible
- **Cause**: Frontend build cache or outdated container
- **Solution**: Rebuild webapp container with `--no-cache` flag
```bash
docker-compose stop webapp
docker rmi -f deploy_webapp
docker-compose build webapp --no-cache
docker-compose up -d webapp
```

#### 2. Permission Denied During PerfSpect Installation
- **Cause**: Insufficient permissions to write to `/tmp` directory
- **Solution**: Ensure agent runs with appropriate user permissions
```bash
# Check directory permissions
ls -la /tmp/
# Fix permissions if needed
chmod 755 /tmp/
```

#### 3. PerfSpect Binary Not Found
- **Cause**: Download failure or network connectivity issues
- **Solution**: Check agent logs and network connectivity
```bash
# Check agent logs
tail -f /var/log/gprofiler.log | grep -i perfspect
# Test connectivity
curl -I https://github.com/intel/PerfSpect/releases/latest/download/perfspect.tgz
```

#### 4. Database Schema Mismatch
- **Cause**: Missing `continuous` column or `additional_args` field
- **Solution**: Update database schema
```sql
-- Add missing continuous column
ALTER TABLE ProfilingRequests ADD COLUMN continuous boolean NOT NULL DEFAULT false;
-- Verify additional_args exists
\d ProfilingRequests;
```

### Debug Commands

#### Check PerfSpect Configuration in Database
```sql
-- Check profiling requests with PerfSpect
SELECT request_id, service_name, additional_args, created_at 
FROM ProfilingRequests 
WHERE additional_args::text LIKE '%perfspect%' 
ORDER BY created_at DESC;

-- Check profiling commands with PerfSpect
SELECT command_id, hostname, service_name, combined_config, created_at 
FROM ProfilingCommands 
WHERE combined_config::text LIKE '%perfspect%' 
ORDER BY created_at DESC;
```

#### Verify Agent Configuration
```bash
# Check if PerfSpect is installed
ls -la /tmp/perfspect/
# Check agent process arguments
ps aux | grep gprofiler | grep perfspect
# Check hardware metrics collection
tail -f /var/log/gprofiler.log | grep -i "hw.*metrics"
```

## Checklist:
<!--- Go over all the following points, and put an `x` in all the boxes that apply. -->
<!--- If you're unsure about any of these, don't hesitate to ask. We're here to help! -->
- [x] I have updated the relevant documentation.
- [x] I have added tests for new logic.
- [x] Frontend UI components are properly integrated.
- [x] Backend API handles PerfSpect configuration correctly.
- [x] Database schema supports PerfSpect settings storage.
- [x] Agent auto-installation workflow is implemented.
- [x] Error handling and logging are comprehensive.
- [x] UX improvements enhance user experience.
- [x] End-to-end integration testing is complete.
- [x] Backward compatibility is maintained.

## Future Enhancements

### Planned Features
- **Custom PerfSpect Arguments**: Allow users to specify custom PerfSpect command-line options
- **Metrics Visualization**: Integrate PerfSpect HTML reports into the UI
- **Performance Thresholds**: Set alerts based on hardware metrics
- **Historical Analysis**: Compare hardware metrics across profiling sessions
- **Multi-Architecture Support**: Extend support beyond x86_64 systems

### Performance Optimizations
- **Caching**: Cache PerfSpect binaries to reduce download overhead
- **Batch Operations**: Optimize database queries for large-scale deployments
- **Async Processing**: Implement asynchronous PerfSpect installation
- **Resource Management**: Add CPU and memory limits for PerfSpect processes
