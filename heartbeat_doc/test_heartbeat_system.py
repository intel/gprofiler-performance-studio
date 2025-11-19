#!/usr/bin/env python3
"""
Test script to verify the heartbeat-based profiling control system.

This script demonstrates:
1. Agent sending heartbeat to backend
2. Backend responding with start/stop commands
3. Agent acting on commands with idempotency
"""

import json
import requests
import time
from datetime import datetime
from typing import Dict, Any, Optional, Set

# Configuration
BACKEND_URL = "http://localhost:5000"  # Updated to port 5000
SERVICE_NAME = "test-service"
HOSTNAME = "test-host"
IP_ADDRESS = "127.0.0.1"

class TestHeartbeatClient:
    """Test client to simulate agent heartbeat behavior"""
    
    def __init__(self, backend_url: str, service_name: str, hostname: str, ip_address: str):
        self.backend_url = backend_url.rstrip('/')
        self.service_name = service_name
        self.hostname = hostname
        self.ip_address = ip_address
        self.last_command_id: Optional[str] = None
        self.executed_commands: Set[str] = set()
    
    def send_heartbeat(self) -> Optional[Dict[str, Any]]:
        """Send heartbeat to backend and return response"""
        heartbeat_data = {
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "service_name": self.service_name,
            "last_command_id": self.last_command_id,
            "status": "active",
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            response = requests.post(
                f"{self.backend_url}/api/metrics/heartbeat",
                json=heartbeat_data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Heartbeat successful: {result.get('message')}")
                
                if result.get("profiling_command") and result.get("command_id"):
                    command_id = result["command_id"]
                    profiling_command = result["profiling_command"]
                    command_type = profiling_command.get("command_type", "unknown")
                    
                    print(f"📋 Received command: {command_type} (ID: {command_id})")
                    
                    # Check idempotency
                    if command_id in self.executed_commands:
                        print(f"⚠️  Command {command_id} already executed, skipping...")
                        return None
                    
                    # Mark as executed
                    self.executed_commands.add(command_id)
                    self.last_command_id = command_id
                    
                    return {
                        "command_type": command_type,
                        "command_id": command_id,
                        "profiling_command": profiling_command
                    }
                else:
                    print("📭 No pending commands")
                return None
            else:
                print(f"❌ Heartbeat failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Heartbeat error: {e}")
            return None
    
    def simulate_profiling_action(self, command_type: str, command_id: str):
        """Simulate profiling action (start/stop)"""
        if command_type == "start":
            print(f"🚀 Starting profiler for command {command_id}")
            # Simulate profiling work
            time.sleep(2)
            print(f"✅ Profiler started successfully")
        elif command_type == "stop":
            print(f"🛑 Stopping profiler for command {command_id}")
            # Simulate stopping
            time.sleep(1)
            print(f"✅ Profiler stopped successfully")
        else:
            print(f"⚠️  Unknown command type: {command_type}")

def create_test_profiling_request(backend_url: str, service_name: str, request_type: str = "start") -> bool:
    """Create a test profiling request"""
    request_data = {
        "service_name": service_name,
        "request_type": request_type,  # Updated to use request_type instead of command_type
        "duration": 60,
        "frequency": 11,
        "profiling_mode": "cpu",
        "target_hosts": {HOSTNAME: [1234, 5678]},  # Required field
        "additional_args": {"test": True}
    }
    
    try:
        response = requests.post(
            f"{backend_url}/api/metrics/profile_request",
            json=request_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Profiling request created: {result.get('message')}")
            print(f"   Request ID: {result.get('request_id')}")
            print(f"   Command ID: {result.get('command_id')}")
            return True
        else:
            print(f"❌ Failed to create profiling request: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error creating profiling request: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Testing Heartbeat-Based Profiling Control System")
    print("=" * 60)
    
    # Initialize test client
    client = TestHeartbeatClient(BACKEND_URL, SERVICE_NAME, HOSTNAME, IP_ADDRESS)
    
    # Test 1: Send initial heartbeat (should have no commands)
    print("\n1️⃣  Test: Initial heartbeat (no commands expected)")
    client.send_heartbeat()
    
    # Test 2: Create a START profiling request
    print("\n2️⃣  Test: Create START profiling request")
    if create_test_profiling_request(BACKEND_URL, SERVICE_NAME, "start"):
        time.sleep(1)  # Give backend time to process
        
        # Send heartbeat to receive the command
        print("\n   📡 Sending heartbeat to receive command...")
        command = client.send_heartbeat()
        
        if command:
            client.simulate_profiling_action(command["command_type"], command["command_id"])
        
        # Test idempotency - send heartbeat again
        print("\n   🔄 Testing idempotency - sending heartbeat again...")
        command = client.send_heartbeat()
        if command is None:
            print("✅ Idempotency working - no duplicate command received")
    
    # Test 3: Create a STOP profiling request
    print("\n3️⃣  Test: Create STOP profiling request")
    if create_test_profiling_request(BACKEND_URL, SERVICE_NAME, "stop"):
        time.sleep(1)  # Give backend time to process
        
        # Send heartbeat to receive the stop command
        print("\n   📡 Sending heartbeat to receive stop command...")
        command = client.send_heartbeat()
        
        if command:
            client.simulate_profiling_action(command["command_type"], command["command_id"])
    
    # Test 4: Multiple heartbeats with no commands
    print("\n4️⃣  Test: Multiple heartbeats with no pending commands")
    for i in range(3):
        print(f"\n   Heartbeat {i+1}/3:")
        client.send_heartbeat()
        time.sleep(1)
    
    print("\n✅ Test completed!")
    print("\nTest Summary:")
    print(f"   - Executed commands: {len(client.executed_commands)}")
    print(f"   - Last command ID: {client.last_command_id}")
    print(f"   - Commands executed: {list(client.executed_commands)}")

if __name__ == "__main__":
    main()
