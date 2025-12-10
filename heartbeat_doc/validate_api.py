#!/usr/bin/env python3
"""
Quick validation script to test the heartbeat API endpoints.
"""

import requests
import json
import sys

def test_heartbeat_api():
    """Test the heartbeat API endpoints"""
    base_url = "http://localhost:5000"  # Updated to port 5000
    
    print("🧪 Testing Heartbeat API Endpoints")
    print("=" * 50)
    
    # Test 1: Valid profiling request
    print("\n1️⃣  Testing valid profiling request...")
    
    valid_request = {
        "service_name": "test-service",
        "request_type": "start",
        "duration": 60,
        "frequency": 11,
        "profiling_mode": "cpu",
        "target_hosts": {"test-host": [1234, 5678]},
        "additional_args": {"test": True}
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/metrics/profile_request",
            json=valid_request,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Valid request successful")
            print(f"   Request ID: {result.get('request_id')}")
            print(f"   Command ID: {result.get('command_id')}")
        else:
            print(f"❌ Valid request failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Valid request error: {e}")
    
    # Test 2: Invalid request (missing target_hosts)
    print("\n2️⃣  Testing invalid request (missing target_hosts)...")
    
    invalid_request = {
        "service_name": "test-service",
        "request_type": "start",
        "duration": 60,
        "frequency": 11,
        "profiling_mode": "cpu"
        # target_hosts missing
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/metrics/profile_request",
            json=invalid_request,
            timeout=10
        )
        
        if response.status_code == 422:  # Pydantic validation error
            print(f"✅ Invalid request correctly rejected with 422")
        elif response.status_code == 400:  # Our validation error
            print(f"✅ Invalid request correctly rejected with 400")
        else:
            print(f"⚠️  Unexpected response: {response.status_code}")
            
        print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Invalid request test error: {e}")
    
    # Test 3: Heartbeat request
    print("\n3️⃣  Testing heartbeat request...")
    
    heartbeat_request = {
        "hostname": "test-host",
        "ip_address": "127.0.0.1",
        "service_name": "test-service",
        "status": "active"
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/metrics/heartbeat",
            json=heartbeat_request,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Heartbeat successful")
            print(f"   Message: {result.get('message')}")
            if result.get('profiling_command'):
                print(f"   Command received: {result.get('command_id')}")
            else:
                print(f"   No pending commands")
        else:
            print(f"❌ Heartbeat failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Heartbeat error: {e}")
    
    print("\n✅ API validation complete!")

if __name__ == "__main__":
    test_heartbeat_api()
