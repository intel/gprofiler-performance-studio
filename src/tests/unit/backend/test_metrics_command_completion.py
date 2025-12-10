#!/usr/bin/env python3
"""
Unit tests for the POST /api/metrics/command_completion endpoint.

This module contains pytest-based unit tests that validate:
1. Valid command completion requests with all required fields
2. Invalid requests with missing required fields
3. Invalid requests with wrong data types
4. Edge cases and boundary conditions
5. Response structure validation
6. Command status updates and related request updates
"""

import uuid
from typing import Any, Dict

import pytest
import requests


@pytest.fixture
def command_completion_url(backend_base_url) -> str:
    """Get the full URL for the command completion endpoint."""
    return f"{backend_base_url}/api/metrics/command_completion"


@pytest.fixture
def valid_completion_data() -> Dict[str, Any]:
    """Provide valid command completion data for testing."""
    return {
        "command_id": str(uuid.uuid4()),  # Unique command ID
        "hostname": "test-host",
        "status": "completed",
        "execution_time": 30,
        "error_message": None,
        "results_path": "/path/to/results",
    }


class TestCommandCompletionEndpoint:
    """Test class for the command completion endpoint."""

    def test_valid_completion_request(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test a valid command completion request."""
        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=valid_completion_data,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert "success" in result, "Response should contain 'success' field"
        assert "message" in result, "Response should contain 'message' field"
        assert result["success"] is True, "Success should be True"
        assert "Command completion recorded" in result["message"]

    def test_valid_failed_completion(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test a valid failed command completion request."""
        failed_completion = valid_completion_data.copy()
        failed_completion.update(
            {
                "status": "failed",
                "error_message": "Profiling process crashed",
                "execution_time": 15,
                "results_path": None,
            }
        )

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=failed_completion,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert result["success"] is True
        assert "Command completion recorded" in result["message"]

    def test_missing_command_id(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing command_id field."""
        invalid_request = valid_completion_data.copy()
        del invalid_request["command_id"]

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_missing_hostname(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing hostname field."""
        invalid_request = valid_completion_data.copy()
        del invalid_request["hostname"]

        response = requests.post(
            command_completion_url,
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
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with missing status field."""
        invalid_request = valid_completion_data.copy()
        del invalid_request["status"]

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_empty_command_id(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with empty command_id."""
        invalid_request = valid_completion_data.copy()
        invalid_request["command_id"] = ""

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_empty_hostname(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with empty hostname."""
        invalid_request = valid_completion_data.copy()
        invalid_request["hostname"] = ""

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_status_value(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid status value."""
        invalid_request = valid_completion_data.copy()
        invalid_request["status"] = "invalid_status"

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_invalid_execution_time_type(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with invalid execution_time data type."""
        invalid_request = valid_completion_data.copy()
        invalid_request["execution_time"] = "not_a_number"

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_negative_execution_time(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with negative execution_time value."""
        invalid_request = valid_completion_data.copy()
        invalid_request["execution_time"] = -10

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        # Negative execution time might be allowed or rejected depending on validation
        assert response.status_code in [
            200,
            400,
            422,
        ], f"Unexpected status code: {response.status_code}"

    def test_zero_execution_time(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with zero execution_time value."""
        valid_request = valid_completion_data.copy()
        valid_request["execution_time"] = 0

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=valid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_none_values_for_optional_fields(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with None values for optional fields."""
        completion_data = valid_completion_data.copy()
        completion_data.update({"execution_time": None, "error_message": None, "results_path": None})

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=completion_data,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_none_values_for_required_fields(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with None values for required fields."""
        invalid_request = valid_completion_data.copy()
        invalid_request["command_id"] = None

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_large_execution_time(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with very large execution_time value."""
        large_time_request = valid_completion_data.copy()
        large_time_request["execution_time"] = 86400  # 24 hours

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=large_time_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_long_error_message(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test request with very long error message."""
        long_error_request = valid_completion_data.copy()
        long_error_request.update({"status": "failed", "error_message": "A" * 1000})  # Very long error message

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=long_error_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_malformed_json(self, command_completion_url: str, credentials: Dict[str, Any]):
        """Test request with malformed JSON."""
        response = requests.post(
            command_completion_url,
            data="{'invalid': json}",  # Invalid JSON
            headers={**credentials, "Content-Type": "application/json"},
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_empty_request_body(self, command_completion_url: str, credentials: Dict[str, Any]):
        """Test request with empty body."""
        response = requests.post(
            command_completion_url,
            headers=credentials,
            json={},
            timeout=10,
            verify=False,
        )

        assert response.status_code in [
            400,
            422,
        ], f"Expected 400 or 422, got {response.status_code}"

    def test_additional_fields(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that additional fields are handled gracefully."""
        extended_request = valid_completion_data.copy()
        extended_request["extra_field"] = "extra_value"
        extended_request["metadata"] = {"key": "value"}

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=extended_request,
            timeout=10,
            verify=False,
        )

        # Additional fields should be ignored, not cause errors
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_different_status_values(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test different valid status values."""
        valid_statuses = ["completed", "failed"]

        for status in valid_statuses:
            status_request = valid_completion_data.copy()
            status_request["status"] = status
            status_request["command_id"] = str(uuid.uuid4())  # Unique command ID

            response = requests.post(
                command_completion_url,
                headers=credentials,
                json=status_request,
                timeout=10,
                verify=False,
            )

            assert response.status_code == 200, f"Failed with status: {status}, code: {response.status_code}"

    def test_results_path_variations(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test different results path formats."""
        path_variations = [
            "/local/path/to/results",
            "s3://bucket/key/results.tar.gz",
            "gs://bucket/results/file.json",
            "https://example.com/results",
            "",  # Empty string
        ]

        for i, path in enumerate(path_variations):
            path_request = valid_completion_data.copy()
            path_request["results_path"] = path
            path_request["command_id"] = str(uuid.uuid4())  # Unique command ID

            response = requests.post(
                command_completion_url,
                headers=credentials,
                json=path_request,
                timeout=10,
                verify=False,
            )

            assert response.status_code == 200, f"Failed with path: {path}, code: {response.status_code}"

    def test_command_completion_without_optional_fields(
        self,
        command_completion_url: str,
        credentials: Dict[str, Any],
    ):
        """Test minimal valid request with only required fields."""
        minimal_request = {
            "command_id": str(uuid.uuid4()),  # Unique command ID
            "hostname": "test-minimal-host",
            "status": "completed",
        }

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=minimal_request,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert result["success"] is True

    def test_multiple_completions_same_command(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test multiple completion reports for the same command."""
        # First completion
        first_response = requests.post(
            command_completion_url,
            headers=credentials,
            json=valid_completion_data,
            timeout=10,
            verify=False,
        )

        # Second completion (should still succeed)
        second_completion = valid_completion_data.copy()
        second_completion["execution_time"] = 45  # Different execution time

        second_response = requests.post(
            command_completion_url,
            headers=credentials,
            json=second_completion,
            timeout=10,
            verify=False,
        )

        # Both should succeed (idempotent or update behavior)
        assert first_response.status_code == 200
        assert second_response.status_code == 200


class TestCommandCompletionResponseStructure:
    """Test class for validating command completion response structure and content."""

    def test_response_content_type(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that response has correct content type."""
        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=valid_completion_data,
            timeout=10,
            verify=False,
        )

        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")

    def test_response_structure_consistency(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that multiple completion requests return consistent response structure."""
        responses = []

        for i in range(3):
            completion_data = valid_completion_data.copy()
            completion_data["command_id"] = str(uuid.uuid4())  # Unique command ID for each request

            response = requests.post(
                command_completion_url,
                headers=credentials,
                json=completion_data,
                timeout=10,
                verify=False,
            )

            if response.status_code == 200:
                responses.append(response.json())

        # All successful responses should have the same structure
        if len(responses) > 1:
            first_keys = set(responses[0].keys())
            for response_data in responses[1:]:
                assert set(response_data.keys()) == first_keys, "Response structure should be consistent"

        # All responses should contain required fields
        for response_data in responses:
            assert "success" in response_data, "All responses should contain 'success' field"
            assert "message" in response_data, "All responses should contain 'message' field"

    def test_error_response_structure(
        self,
        command_completion_url: str,
        credentials: Dict[str, Any],
    ):
        """Test error response structure for invalid requests."""
        invalid_request = {
            "command_id": "",  # Empty command ID should cause error
            "hostname": "test-host",
            "status": "completed",
        }

        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=invalid_request,
            timeout=10,
            verify=False,
        )

        # Should return error status
        assert response.status_code in [400, 422, 500]

    def test_success_message_format(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that success message contains command ID."""
        response = requests.post(
            command_completion_url,
            headers=credentials,
            json=valid_completion_data,
            timeout=10,
            verify=False,
        )

        if response.status_code == 200:
            result = response.json()
            assert result["success"] is True
            assert valid_completion_data["command_id"] in result["message"]

    def test_completion_request_idempotency(
        self,
        command_completion_url: str,
        valid_completion_data: Dict[str, Any],
        credentials: Dict[str, Any],
    ):
        """Test that completion requests are handled appropriately when repeated."""
        # Send initial completion
        first_response = requests.post(
            command_completion_url,
            headers=credentials,
            json=valid_completion_data,
            timeout=10,
            verify=False,
        )

        # Send identical completion
        second_response = requests.post(
            command_completion_url,
            headers=credentials,
            json=valid_completion_data,
            timeout=10,
            verify=False,
        )

        # Both should succeed (system should handle duplicates gracefully)
        assert first_response.status_code == 200
        assert second_response.status_code == 200

        if first_response.status_code == 200 and second_response.status_code == 200:
            first_result = first_response.json()
            second_result = second_response.json()

            # Both should indicate success
            assert first_result["success"] is True
            assert second_result["success"] is True
