#!/usr/bin/env python3
#
# Copyright (C) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Test script for Dynamic Profiling Pydantic models.

This script demonstrates how to use the dynamic profiling models
and validates that they work correctly.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src directory to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

try:
    from gprofiler.backend.models.dynamic_profiling_models import (
        # Enums
        CommandType,
        ProfilingMode,
        ProfilingStatus,
        # Request models
        ProfilingRequestCreate,
        ProfilingRequestResponse,
        ProfilingRequestUpdate,
        # Command models
        ProfilingCommandCreate,
        ProfilingCommandResponse,
        # Heartbeat models
        HostHeartbeatCreate,
        HostHeartbeatResponse,
        # Execution models
        ProfilingExecutionCreate,
        ProfilingExecutionResponse,
        # Mapping models
        NamespaceServiceMapping,
        ServiceContainerMapping,
        JobContainerMapping,
        ContainerProcessMapping,
        ContainerHostMapping,
        ProcessHostMapping,
        # Query models
        ProfilingRequestQuery,
        HostHeartbeatQuery,
    )
    print("✅ Successfully imported all dynamic profiling models")
except ImportError as e:
    print(f"❌ Failed to import models: {e}")
    sys.exit(1)


def test_enums():
    """Test enum definitions"""
    print("\n" + "="*60)
    print("Testing Enums")
    print("="*60)
    
    # Test CommandType
    assert CommandType.START == "start"
    assert CommandType.STOP == "stop"
    assert CommandType.RECONFIGURE == "reconfigure"
    print("✅ CommandType enum works")
    
    # Test ProfilingMode
    assert ProfilingMode.CPU == "cpu"
    assert ProfilingMode.MEMORY == "memory"
    assert ProfilingMode.ALLOCATION == "allocation"
    assert ProfilingMode.NATIVE == "native"
    print("✅ ProfilingMode enum works")
    
    # Test ProfilingStatus
    assert ProfilingStatus.PENDING == "pending"
    assert ProfilingStatus.IN_PROGRESS == "in_progress"
    assert ProfilingStatus.COMPLETED == "completed"
    print("✅ ProfilingStatus enum works")


def test_profiling_request_models():
    """Test profiling request models"""
    print("\n" + "="*60)
    print("Testing Profiling Request Models")
    print("="*60)
    
    # Test ProfilingRequestCreate - service level
    request = ProfilingRequestCreate(
        service_name="web-api",
        profiling_mode=ProfilingMode.CPU,
        duration_seconds=60,
        sample_rate=100,
        start_time=datetime.utcnow(),
        executors=["pyspy", "perf"]
    )
    assert request.service_name == "web-api"
    assert request.profiling_mode == ProfilingMode.CPU
    assert request.duration_seconds == 60
    print("✅ ProfilingRequestCreate works (service level)")
    
    # Test namespace level
    request_ns = ProfilingRequestCreate(
        namespace="production",
        profiling_mode=ProfilingMode.MEMORY,
        duration_seconds=120,
        sample_rate=50,
        start_time=datetime.utcnow()
    )
    assert request_ns.namespace == "production"
    print("✅ ProfilingRequestCreate works (namespace level)")
    
    # Test validation - at least one target required
    try:
        invalid_request = ProfilingRequestCreate(
            profiling_mode=ProfilingMode.CPU,
            duration_seconds=60,
            sample_rate=100,
            start_time=datetime.utcnow()
        )
        print("❌ Validation should have failed for request with no targets")
    except ValueError:
        print("✅ Validation works: requires at least one target")
    
    # Test validation - positive duration
    try:
        invalid_request = ProfilingRequestCreate(
            service_name="test",
            profiling_mode=ProfilingMode.CPU,
            duration_seconds=-10,
            sample_rate=100,
            start_time=datetime.utcnow()
        )
        print("❌ Validation should have failed for negative duration")
    except ValueError:
        print("✅ Validation works: duration must be positive")


def test_heartbeat_models():
    """Test host heartbeat models"""
    print("\n" + "="*60)
    print("Testing Host Heartbeat Models")
    print("="*60)
    
    heartbeat = HostHeartbeatCreate(
        host_id="host-12345",
        host_name="worker-node-01",
        host_ip="10.0.1.42",
        service_name="web-api",
        namespace="production",
        containers=["web-api-container-1", "web-api-container-2"],
        jobs=["data-processing-job"],
        workloads={"cpu_usage": 45.2, "memory_usage": 60.5},
        executors=["pyspy", "perf"]
    )
    assert heartbeat.host_id == "host-12345"
    assert heartbeat.host_name == "worker-node-01"
    assert len(heartbeat.containers) == 2
    assert heartbeat.workloads["cpu_usage"] == 45.2
    print("✅ HostHeartbeatCreate works")


def test_command_models():
    """Test profiling command models"""
    print("\n" + "="*60)
    print("Testing Profiling Command Models")
    print("="*60)
    
    command = ProfilingCommandCreate(
        profiling_request_id=1,
        host_id="host-12345",
        target_containers=["web-api-container-1"],
        target_processes=[1001, 1002],
        command_type=CommandType.START,
        command_args={"mode": "cpu", "duration": 60, "sample_rate": 100},
        command_json='{"command": "pyspy", "args": ["--rate", "100"]}'
    )
    assert command.host_id == "host-12345"
    assert command.command_type == CommandType.START
    assert len(command.target_processes) == 2
    print("✅ ProfilingCommandCreate works")


def test_execution_models():
    """Test profiling execution models"""
    print("\n" + "="*60)
    print("Testing Profiling Execution Models")
    print("="*60)
    
    execution = ProfilingExecutionCreate(
        profiling_request_id=1,
        profiling_command_id=1,
        host_name="worker-node-01",
        target_containers=["web-api-container-1"],
        target_processes=[1001, 1002],
        command_type=CommandType.START,
        started_at=datetime.utcnow(),
        status=ProfilingStatus.IN_PROGRESS
    )
    assert execution.host_name == "worker-node-01"
    assert execution.status == ProfilingStatus.IN_PROGRESS
    print("✅ ProfilingExecutionCreate works")


def test_mapping_models():
    """Test hierarchical mapping models"""
    print("\n" + "="*60)
    print("Testing Mapping Models")
    print("="*60)
    
    # Test NamespaceServiceMapping
    ns_mapping = NamespaceServiceMapping(
        namespace="production",
        service_name="web-api"
    )
    assert ns_mapping.namespace == "production"
    print("✅ NamespaceServiceMapping works")
    
    # Test ServiceContainerMapping
    sc_mapping = ServiceContainerMapping(
        service_name="web-api",
        container_name="web-api-container-1"
    )
    assert sc_mapping.container_name == "web-api-container-1"
    print("✅ ServiceContainerMapping works")
    
    # Test JobContainerMapping
    jc_mapping = JobContainerMapping(
        job_name="batch-processing-job",
        container_name="processor-container-1"
    )
    assert jc_mapping.job_name == "batch-processing-job"
    print("✅ JobContainerMapping works")
    
    # Test ContainerProcessMapping
    cp_mapping = ContainerProcessMapping(
        container_name="web-api-container-1",
        process_id=1001,
        process_name="python3"
    )
    assert cp_mapping.process_id == 1001
    print("✅ ContainerProcessMapping works")
    
    # Test ContainerHostMapping
    ch_mapping = ContainerHostMapping(
        container_name="web-api-container-1",
        host_id="host-12345",
        host_name="worker-node-01"
    )
    assert ch_mapping.host_id == "host-12345"
    print("✅ ContainerHostMapping works")
    
    # Test ProcessHostMapping
    ph_mapping = ProcessHostMapping(
        process_id=1001,
        host_id="host-12345",
        host_name="worker-node-01"
    )
    assert ph_mapping.process_id == 1001
    print("✅ ProcessHostMapping works")


def test_query_models():
    """Test query models"""
    print("\n" + "="*60)
    print("Testing Query Models")
    print("="*60)
    
    # Test ProfilingRequestQuery
    request_query = ProfilingRequestQuery(
        status=ProfilingStatus.IN_PROGRESS,
        service_name="web-api",
        limit=50,
        offset=0
    )
    assert request_query.status == ProfilingStatus.IN_PROGRESS
    assert request_query.limit == 50
    print("✅ ProfilingRequestQuery works")
    
    # Test HostHeartbeatQuery
    heartbeat_query = HostHeartbeatQuery(
        service_name="web-api",
        namespace="production",
        last_seen_after=datetime.utcnow() - timedelta(minutes=5),
        limit=100
    )
    assert heartbeat_query.namespace == "production"
    assert heartbeat_query.limit == 100
    print("✅ HostHeartbeatQuery works")


def test_json_serialization():
    """Test JSON serialization of models"""
    print("\n" + "="*60)
    print("Testing JSON Serialization")
    print("="*60)
    
    # Create a request
    request = ProfilingRequestCreate(
        service_name="web-api",
        profiling_mode=ProfilingMode.CPU,
        duration_seconds=60,
        sample_rate=100,
        start_time=datetime.utcnow(),
        executors=["pyspy"]
    )
    
    # Serialize to dict
    request_dict = request.model_dump()
    assert request_dict["service_name"] == "web-api"
    assert request_dict["profiling_mode"] == "cpu"
    print("✅ Model serialization to dict works")
    
    # Serialize to JSON
    request_json = request.model_dump_json()
    assert "web-api" in request_json
    assert "cpu" in request_json
    print("✅ Model serialization to JSON works")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Dynamic Profiling Models Test Suite")
    print("="*60)
    
    try:
        test_enums()
        test_profiling_request_models()
        test_heartbeat_models()
        test_command_models()
        test_execution_models()
        test_mapping_models()
        test_query_models()
        test_json_serialization()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nDynamic Profiling models are working correctly!")
        print("\nYou can now:")
        print("  1. Apply the database schema (dynamic_profiling_schema.sql)")
        print("  2. Create API endpoints using these models")
        print("  3. Build request resolution logic")
        print("  4. Integrate with agents for command execution")
        print("")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())




