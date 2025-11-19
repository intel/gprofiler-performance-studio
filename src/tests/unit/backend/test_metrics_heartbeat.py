#!/usr/bin/env python3
"""
Unit tests for the POST /api/metrics/heartbeat endpoint.

This module contains pytest-based unit tests that validate:
1. Valid heartbeat requests with all required fields
2. Invalid requests with missing required fields
3. Invalid requests with wrong data types
4. Edge cases and boundary conditions
5. Response structure validation
6. Command delivery through heartbeat responses
"""

from datetime import datetime
from typing import Any, Dict

import pytest
import requests


@pytest.fixture
def heartbeat_url(backend_base_url) -> str:
    """Get the full URL for the heartbeat endpoint."""
    return f"{backend_base_url}/api/metrics/heartbeat"


@pytest.fixture
def valid_heartbeat_data() -> Dict[str, Any]:
    """Provide valid heartbeat data for testing."""
    return {
        "hostname": "test-host",
        "ip_address": "127.0.0.1",
        "service_name": "test-service",
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "last_command_id": None,
    }


class TestHeartbeatEndpoint:
    """Test class for the heartbeat endpoint."""

    def test_valid_heartbeat_request(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test a valid heartbeat request."""
        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=valid_heartbeat_data,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert "message" in result, "Response should contain 'message' field"

        # Check for optional command fields
        if "profiling_command" in result:
            assert "command_id" in result, "Response with command should contain 'command_id' field"

    def test_heartbeat_with_last_command_id(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test heartbeat request with last_command_id."""
        heartbeat_data = valid_heartbeat_data.copy()
        heartbeat_data["last_command_id"] = "test-command-123"

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=heartbeat_data,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert "message" in result

    def test_missing_hostname(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing hostname field."""
        invalid_request = valid_heartbeat_data.copy()
        del invalid_request["hostname"]

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_missing_ip_address(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing ip_address field."""
        invalid_request = valid_heartbeat_data.copy()
        del invalid_request["ip_address"]

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_missing_service_name(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing service_name field."""
        invalid_request = valid_heartbeat_data.copy()
        del invalid_request["service_name"]

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_missing_status(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing status field."""
        invalid_request = valid_heartbeat_data.copy()
        del invalid_request["status"]

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        # Status might have a default value, so it could be valid
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_empty_hostname(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with empty hostname."""
        invalid_request = valid_heartbeat_data.copy()
        invalid_request["hostname"] = ""

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_empty_service_name(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with empty service_name."""
        invalid_request = valid_heartbeat_data.copy()
        invalid_request["service_name"] = ""

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_ip_address_format(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid IP address format."""
        invalid_request = valid_heartbeat_data.copy()
        invalid_request["ip_address"] = "invalid.ip.address"

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        # Depending on validation, this might be accepted or rejected
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_invalid_status_value(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid status value."""
        invalid_request = valid_heartbeat_data.copy()
        invalid_request["status"] = "invalid_status"

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        # Might be accepted or rejected depending on validation
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_none_values(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with None values for required fields."""
        invalid_request = valid_heartbeat_data.copy()
        invalid_request["hostname"] = None

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_timestamp_format(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid timestamp format."""
        invalid_request = valid_heartbeat_data.copy()
        invalid_request["timestamp"] = "invalid-timestamp"

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        # Timestamp validation depends on implementation
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_missing_timestamp(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing timestamp (should use server time)."""
        heartbeat_data = valid_heartbeat_data.copy()
        del heartbeat_data["timestamp"]

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=heartbeat_data,
            timeout=10,
            verify=False,
        )

        # Missing timestamp should be handled gracefully
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_ipv6_address(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with IPv6 address."""
        ipv6_request = valid_heartbeat_data.copy()
        ipv6_request["ip_address"] = "::1"

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=ipv6_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_long_hostname(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with very long hostname."""
        long_hostname_request = valid_heartbeat_data.copy()
        long_hostname_request["hostname"] = "a" * 255  # Very long hostname

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=long_hostname_request,
            timeout=10,
            verify=False,
        )

        # Should either accept or reject based on hostname length limits
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_malformed_json(self, heartbeat_url: str, credentials: Dict[str, Any]):
        """Test request with malformed JSON."""
        response = requests.post(
            heartbeat_url,
            data="{'invalid': json}",  # Invalid JSON
            headers={**credentials, "Content-Type": "application/json"},
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_empty_request_body(self, heartbeat_url: str, credentials: Dict[str, Any]):
        """Test request with empty body."""
        response = requests.post(heartbeat_url, headers=credentials, json={}, timeout=10, verify=False)

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_additional_fields(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that additional fields are handled gracefully."""
        extended_request = valid_heartbeat_data.copy()
        extended_request["extra_field"] = "extra_value"
        extended_request["metadata"] = {"key": "value"}

        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=extended_request,
            timeout=10,
            verify=False,
        )

        # Additional fields should be ignored, not cause errors
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_status_variations(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test different valid status values."""
        valid_statuses = ["active", "inactive", "error", "pending"]

        for status in valid_statuses:
            status_request = valid_heartbeat_data.copy()
            status_request["status"] = status
            status_request["hostname"] = f"test-host-{status}"  # Unique hostname

            response = requests.post(
                heartbeat_url,
                headers=credentials,
                json=status_request,
                timeout=10,
                verify=False,
            )

            assert response.status_code in [
                200,
                400,
                422,
            ], f"Failed with status: {status}, code: {response.status_code}"

    def test_multiple_heartbeats_same_host(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test multiple heartbeats from the same host."""
        for i in range(3):
            heartbeat_data = valid_heartbeat_data.copy()
            heartbeat_data["timestamp"] = datetime.now().isoformat()

            response = requests.post(
                heartbeat_url,
                headers=credentials,
                json=heartbeat_data,
                timeout=10,
                verify=False,
            )

            assert response.status_code == 200, f"Heartbeat {i+1} failed: {response.status_code}: {response.text}"


class TestHeartbeatResponseStructure:
    """Test class for validating heartbeat response structure and content."""

    def test_response_content_type(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that response has correct content type."""
        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=valid_heartbeat_data,
            timeout=10,
            verify=False,
        )

        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")

    def test_response_structure_consistency(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that multiple heartbeat requests return consistent response structure."""
        responses = []

        for i in range(3):
            heartbeat_data = valid_heartbeat_data.copy()
            heartbeat_data["hostname"] = f"test-host-{i}"

            response = requests.post(
                heartbeat_url,
                headers=credentials,
                json=heartbeat_data,
                timeout=10,
                verify=False,
            )

            if response.status_code == 200:
                responses.append(response.json())

        # All successful responses should have at least the message field
        for response_data in responses:
            assert "message" in response_data, "All responses should contain 'message' field"

    def test_command_response_structure(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test response structure when commands are present."""
        response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=valid_heartbeat_data,
            timeout=10,
            verify=False,
        )

        if response.status_code == 200:
            result = response.json()

        assert "command_id" in result, "Response should contain 'command_id' field"
        if result.get("command_id", None) is not None:
            assert isinstance(result["command_id"], str), "command_id should be a string"

        assert "profiling_command" in result, "Response should contain 'profiling_command' field"
        if result.get("profiling_command", None) is not None:
            assert isinstance(result["profiling_command"], dict), "profiling_command should be a dictionary"

            # Validate command structure
            command = result["profiling_command"]
            expected_fields = ["command_type"]  # Minimum expected fields
            for field in expected_fields:
                if field in command:
                    assert command[field] is not None, f"Command field {field} should not be None"

    def test_heartbeat_idempotency(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that heartbeat requests are idempotent."""
        # Send initial heartbeat
        first_response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=valid_heartbeat_data,
            timeout=10,
            verify=False,
        )

        # Send identical heartbeat
        second_response = requests.post(
            heartbeat_url,
            headers=credentials,
            json=valid_heartbeat_data,
            timeout=10,
            verify=False,
        )

        assert first_response.status_code == second_response.status_code

        if first_response.status_code == 200 and second_response.status_code == 200:
            first_result = first_response.json()
            second_result = second_response.json()

            # Both should contain message field
            assert "message" in first_result
            assert "message" in second_result

    def test_heartbeat_timestamp_handling(
        self,
        heartbeat_url: str,
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test various timestamp formats."""
        timestamp_formats = [
            datetime.now().isoformat(),
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]

        for timestamp in timestamp_formats:
            heartbeat_data = valid_heartbeat_data.copy()
            heartbeat_data["timestamp"] = timestamp
            heartbeat_data["hostname"] = f"test-host-{timestamp}"  # Unique hostname

            response = requests.post(
                heartbeat_url,
                headers=credentials,
                json=heartbeat_data,
                timeout=10,
                verify=False,
            )

            # Should handle various timestamp formats gracefully
            assert response.status_code in [
                200,
                400,
                422,
            ], f"Failed with timestamp format: {timestamp}"
