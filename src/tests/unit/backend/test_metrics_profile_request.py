#!/usr/bin/env python3
"""
Unit tests for the POST /api/metrics/profile_request endpoint.

This module contains pytest-based unit tests that validate:
1. Valid profiling requests with all required fields
2. Invalid requests with missing required fields
3. Invalid requests with wrong data types
4. Edge cases and boundary conditions
5. Response structure validation
"""

from typing import Any, Dict

import pytest
import requests


@pytest.fixture
def profile_request_url(backend_base_url) -> str:
    """Get the full URL for the profile request endpoint."""
    return f"{backend_base_url}/api/metrics/profile_request"


@pytest.fixture
def valid_request_data() -> Dict[str, Any]:
    """Provide valid request data for testing."""
    return {
        "service_name": "test-service",
        "request_type": "start",
        "duration": 60,
        "frequency": 11,
        "profiling_mode": "cpu",
        "target_hostnames": ["test-host"],
        "additional_args": {"test": True},
        "stop_level": "host",
    }


class TestProfileRequestEndpoint:
    """Test class for the profile request endpoint."""

    def test_valid_start_request(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test a valid start profiling request."""
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_request_data,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert "message" in result, "Response should contain 'message' field"
        assert "request_id" in result, "Response should contain 'request_id' field"
        assert "command_ids" in result, "Response should contain 'command_ids' field"

        # Validate that IDs are non-empty strings
        assert isinstance(result["request_id"], str) and result["request_id"], "request_id should be a non-empty string"
        assert (
            isinstance(result["command_ids"], list) and result["command_ids"]
        ), "command_id should be a non-empty list"

    def test_valid_stop_request(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test a valid stop profiling request."""
        stop_request_data = valid_request_data.copy()
        stop_request_data["request_type"] = "stop"

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=stop_request_data,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert "message" in result
        assert "request_id" in result
        assert "command_ids" in result

    def test_missing_service_name(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing service_name field."""
        invalid_request = valid_request_data.copy()
        del invalid_request["service_name"]

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_missing_request_type(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing request_type field."""
        invalid_request = valid_request_data.copy()
        del invalid_request["request_type"]

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_missing_target_hostnames(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing target_hostnames field."""
        invalid_request = valid_request_data.copy()
        del invalid_request["target_hostnames"]

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_empty_target_hostnames(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with empty target_hostnames list."""
        invalid_request = valid_request_data.copy()
        invalid_request["target_hostnames"] = []

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_request_type(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid request_type value."""
        invalid_request = valid_request_data.copy()
        invalid_request["request_type"] = "invalid_type"

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_duration_type(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid duration data type."""
        invalid_request = valid_request_data.copy()
        invalid_request["duration"] = "not_a_number"

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_frequency_type(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid frequency data type."""
        invalid_request = valid_request_data.copy()
        invalid_request["frequency"] = "not_a_number"

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_negative_duration(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with negative duration value."""
        invalid_request = valid_request_data.copy()
        invalid_request["duration"] = -1

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_zero_duration(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with zero duration value."""
        invalid_request = valid_request_data.copy()
        invalid_request["duration"] = 0

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_profiling_mode(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid profiling_mode value."""
        invalid_request = valid_request_data.copy()
        invalid_request["profiling_mode"] = "invalid_mode"

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        # This might be valid depending on backend implementation
        # Adjust assertion based on actual backend behavior
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_multiple_target_hostnames(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with multiple target hostnames."""
        multi_host_request = valid_request_data.copy()
        multi_host_request["target_hostnames"] = ["host1", "host2", "host3"]

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=multi_host_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert "request_id" in result
        assert "command_id" in result

    def test_large_duration_value(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with large duration value."""
        large_duration_request = valid_request_data.copy()
        large_duration_request["duration"] = 86400  # 24 hours

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=large_duration_request,
            timeout=10,
            verify=False,
        )

        # Should either accept or reject based on business rules
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_high_frequency_value(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with high frequency value."""
        high_freq_request = valid_request_data.copy()
        high_freq_request["frequency"] = 1000

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=high_freq_request,
            timeout=10,
            verify=False,
        )

        # Should either accept or reject based on business rules
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_empty_service_name(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with empty service_name."""
        invalid_request = valid_request_data.copy()
        invalid_request["service_name"] = ""

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_none_values(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with None values for required fields."""
        invalid_request = valid_request_data.copy()
        invalid_request["service_name"] = None

        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_malformed_json(self, profile_request_url: str, credentials: Dict[str, Any]):
        """Test request with malformed JSON."""
        response = requests.post(
            profile_request_url,
            data="{'invalid': json}",  # Invalid JSON
            headers={**credentials, "Content-Type": "application/json"},
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_empty_request_body(self, profile_request_url: str, credentials: Dict[str, Any]):
        """Test request with empty body."""
        response = requests.post(profile_request_url, headers=credentials, json={}, timeout=10, verify=False)

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_additional_args_structure(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that additional_args accepts various data structures."""
        test_cases = [
            {"key": "value"},
            {"nested": {"key": "value"}},
            {"list": [1, 2, 3]},
            {"boolean": True},
            {"number": 42},
        ]

        for additional_args in test_cases:
            request_data = valid_request_data.copy()
            request_data["additional_args"] = additional_args

            response = requests.post(
                profile_request_url,
                headers=credentials,
                json=request_data,
                timeout=10,
                verify=False,
            )

            assert (
                response.status_code == 200
            ), f"Failed with additional_args: {additional_args}, status: {response.status_code}"


class TestProfileRequestResponseStructure:
    """Test class for validating response structure and content."""

    def test_response_content_type(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that response has correct content type."""
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_request_data,
            timeout=10,
            verify=False,
        )

        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")

    def test_response_structure_consistency(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that multiple requests return consistent response structure."""
        responses = []

        for i in range(3):
            request_data = valid_request_data.copy()
            request_data["service_name"] = f"test-service-{i}"

            response = requests.post(
                profile_request_url,
                headers=credentials,
                json=request_data,
                timeout=10,
                verify=False,
            )

            if response.status_code == 200:
                responses.append(response.json())

        # All successful responses should have the same structure
        if len(responses) > 1:
            first_keys = set(responses[0].keys())
            for response in responses[1:]:
                assert set(response.json().keys()) == first_keys, "Response structure should be consistent"

    def test_unique_identifiers(
        self,
        profile_request_url: str,
        valid_request_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that each request generates unique identifiers."""
        request_id_set = set()
        command_id_set = set()

        for i in range(5):
            request_data = valid_request_data.copy()
            request_data["service_name"] = f"test-service-{i}"

            response = requests.post(
                profile_request_url,
                headers=credentials,
                json=request_data,
                timeout=10,
                verify=False,
            )

            if response.status_code == 200:
                result = response.json()
                request_id = result.get("request_id")
                command_ids = result.get("command_ids")

                assert request_id not in request_id_set, "request_id should be unique"
                request_id_set.add(request_id)

                for command_id in command_ids:
                    assert command_id not in command_id_set, "command_id should be unique"
                    command_id_set.add(command_id)
