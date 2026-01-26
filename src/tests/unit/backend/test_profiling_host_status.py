#!/usr/bin/env python3
"""
Unit tests for the GET /api/metrics/profiling/host_status endpoint.

This module contains pytest-based unit tests that validate:
1. N+1 query optimization (single query with LEFT JOIN)
2. Filter functionality for all parameters
3. Combined filters (AND logic)
4. Response structure validation
5. Performance improvements
6. NULL command handling (stopped status)
"""

from typing import Any, Dict, List

import pytest
import requests


@pytest.fixture
def profiling_host_status_url(backend_base_url) -> str:
    """Get the full URL for the profiling host status endpoint."""
    return f"{backend_base_url}/api/metrics/profiling/host_status"


class TestProfilingHostStatusEndpoint:
    """Test class for the profiling host status endpoint."""

    def test_get_all_hosts_no_filters(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 1: Get all hosts without any filters
        
        Expected: Returns all active hosts with heartbeats
        """
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # Validate response structure
        if len(result) > 0:
            host = result[0]
            required_fields = [
                "id", "service_name", "hostname", "ip_address",
                "pids", "command_type", "profiling_status", "heartbeat_timestamp"
            ]
            for field in required_fields:
                assert field in host, f"Response should contain '{field}' field"

    def test_filter_by_service_name(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 2: Filter by service name
        
        Expected: Returns only hosts matching service_name
        """
        response = requests.get(
            f"{profiling_host_status_url}?service_name=devapp",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should match the filter
        for host in result:
            assert "devapp" in host["service_name"].lower(), f"Host service_name should contain 'devapp'"

    def test_filter_by_hostname_partial(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 3: Filter by hostname (partial match)
        
        Expected: Returns hosts with hostnames containing the search term
        """
        response = requests.get(
            f"{profiling_host_status_url}?hostname=restricted",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should match the filter
        for host in result:
            assert "restricted" in host["hostname"].lower(), f"Host hostname should contain 'restricted'"

    def test_filter_by_ip_address_prefix(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 4: Filter by IP address prefix (subnet filtering)
        
        Expected: Returns hosts with IPs matching the prefix
        Note: Tests inet::text casting for PostgreSQL compatibility
        """
        response = requests.get(
            f"{profiling_host_status_url}?ip_address=10.9",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should match the filter
        for host in result:
            assert host["ip_address"].startswith("10.9"), f"Host IP should start with '10.9'"

    def test_filter_by_profiling_status_sent(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 5: Filter by profiling status (sent)
        
        Expected: Returns only hosts with sent commands
        """
        response = requests.get(
            f"{profiling_host_status_url}?profiling_status=sent",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should have status 'sent'
        for host in result:
            assert host["profiling_status"] == "sent", f"Host status should be 'sent'"

    def test_filter_by_profiling_status_stopped(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 6: Filter by profiling status (stopped)
        
        Expected: Returns hosts with no active commands (NULL → stopped)
        Note: Tests NULL handling in optimized query
        """
        response = requests.get(
            f"{profiling_host_status_url}?profiling_status=stopped",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should have status 'stopped' and command_type 'N/A'
        for host in result:
            assert host["profiling_status"] == "stopped", f"Host status should be 'stopped'"
            assert host["command_type"] == "N/A", f"Stopped hosts should have command_type 'N/A'"

    def test_filter_by_command_type(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 7: Filter by command type
        
        Expected: Returns only hosts with specified command type
        """
        response = requests.get(
            f"{profiling_host_status_url}?command_type=start",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should have command_type 'start'
        for host in result:
            assert host["command_type"] == "start", f"Host command_type should be 'start'"

    def test_combined_filters_service_and_hostname(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 8: Combined filters - service name + hostname
        
        Expected: Returns hosts matching BOTH filters (AND logic)
        """
        response = requests.get(
            f"{profiling_host_status_url}?service_name=devapp&hostname=restricted",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should match both filters
        for host in result:
            assert "devapp" in host["service_name"].lower(), f"Should match service filter"
            assert "restricted" in host["hostname"].lower(), f"Should match hostname filter"

    def test_combined_filters_service_ip_status(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 9: Combined filters - service + IP + status
        
        Expected: Returns hosts matching ALL THREE filters (AND logic)
        """
        response = requests.get(
            f"{profiling_host_status_url}?service_name=devapp&ip_address=10.9&profiling_status=sent",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # All returned hosts should match all filters
        for host in result:
            assert "devapp" in host["service_name"].lower(), f"Should match service filter"
            assert host["ip_address"].startswith("10.9"), f"Should match IP filter"
            assert host["profiling_status"] == "sent", f"Should match status filter"

    def test_exact_match_mode(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 10: Exact match mode
        
        Expected: Returns only exact matches when exact_match=true
        """
        response = requests.get(
            f"{profiling_host_status_url}?hostname=devrestricted-achatharajupalli&exact_match=true",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.status_code}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # Should return exact match only
        for host in result:
            assert host["hostname"] == "devrestricted-achatharajupalli", f"Should be exact match"

    def test_multiple_service_names(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 11: Multiple service names (OR logic)
        
        Expected: Returns hosts matching ANY of the service names
        """
        response = requests.get(
            f"{profiling_host_status_url}?service_name=devapp&service_name=web-service",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        
        # Hosts should match at least one of the service names
        for host in result:
            service = host["service_name"].lower()
            assert "devapp" in service or "web-service" in service, \
                f"Should match one of the service names"

    def test_no_results_for_invalid_filter(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 12: No results for invalid filter
        
        Expected: Returns empty array for non-existent filter value
        """
        response = requests.get(
            f"{profiling_host_status_url}?service_name=nonexistent-service-12345",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"
        assert len(result) == 0, "Should return empty array for non-existent filter"


class TestProfilingHostStatusPerformance:
    """Test class for performance validation."""

    def test_response_time_acceptable(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 13: Response time is acceptable
        
        Expected: Response time < 100ms (even with filters)
        Note: With N+1 problem, this would be much slower
        """
        import time
        
        start = time.time()
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert elapsed < 100, f"Response time should be < 100ms, got {elapsed:.2f}ms"

    def test_response_time_with_filters(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 14: Response time with multiple filters
        
        Expected: Response time < 100ms even with multiple filters
        Note: Database-side filtering ensures constant performance
        """
        import time
        
        start = time.time()
        response = requests.get(
            f"{profiling_host_status_url}?service_name=devapp&hostname=restricted&profiling_status=sent",
            headers=credentials,
            timeout=10,
            verify=False,
        )
        elapsed = (time.time() - start) * 1000

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert elapsed < 100, f"Response time should be < 100ms with filters, got {elapsed:.2f}ms"


class TestProfilingHostStatusDataValidation:
    """Test class for data validation."""

    def test_pids_array_structure(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 15: PIDs array structure
        
        Expected: pids field is always an array (may be empty)
        """
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        for host in result:
            assert isinstance(host["pids"], list), f"pids should be an array"
            # All elements should be integers
            for pid in host["pids"]:
                assert isinstance(pid, int), f"PIDs should be integers"

    def test_heartbeat_timestamp_format(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 16: Heartbeat timestamp format
        
        Expected: heartbeat_timestamp is valid ISO 8601 datetime
        """
        from datetime import datetime
        
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        for host in result:
            timestamp = host["heartbeat_timestamp"]
            # Should be parseable as ISO 8601
            try:
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                pytest.fail(f"Invalid timestamp format: {timestamp}")

    def test_profiling_status_valid_values(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 17: Profiling status contains only valid values
        
        Expected: profiling_status is one of: pending, sent, completed, failed, stopped
        """
        valid_statuses = {"pending", "sent", "completed", "failed", "stopped"}
        
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        for host in result:
            status = host["profiling_status"]
            assert status in valid_statuses, \
                f"Invalid status '{status}'. Must be one of: {valid_statuses}"

    def test_command_type_valid_values(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 18: Command type contains only valid values
        
        Expected: command_type is one of: start, stop, N/A
        """
        valid_command_types = {"start", "stop", "N/A"}
        
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        for host in result:
            cmd_type = host["command_type"]
            assert cmd_type in valid_command_types, \
                f"Invalid command_type '{cmd_type}'. Must be one of: {valid_command_types}"

    def test_stopped_hosts_have_na_command(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 19: Stopped hosts have N/A command type
        
        Expected: All hosts with status='stopped' have command_type='N/A'
        Note: Tests NULL command handling
        """
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        for host in result:
            if host["profiling_status"] == "stopped":
                assert host["command_type"] == "N/A", \
                    f"Stopped hosts should have command_type='N/A'"

    def test_active_hosts_have_valid_command(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 20: Active hosts have valid command type
        
        Expected: Hosts with status != 'stopped' have command_type = 'start' or 'stop'
        """
        response = requests.get(
            profiling_host_status_url,
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        for host in result:
            if host["profiling_status"] != "stopped":
                assert host["command_type"] in ["start", "stop"], \
                    f"Active hosts should have valid command_type"


class TestProfilingHostStatusEdgeCases:
    """Test class for edge cases."""

    def test_empty_filter_value(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 21: Empty filter value
        
        Expected: Empty filter value returns all results (ignored)
        """
        response = requests.get(
            f"{profiling_host_status_url}?service_name=",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        assert isinstance(result, list), "Response should be a list"

    def test_case_sensitivity(
        self,
        profiling_host_status_url: str,
        credentials: Dict[str, Any],
    ):
        """
        TEST 22: Case insensitivity
        
        Expected: Filters are case-insensitive (LIKE with ILIKE behavior)
        """
        # Test with lowercase
        response_lower = requests.get(
            f"{profiling_host_status_url}?service_name=devapp",
            headers=credentials,
            timeout=10,
            verify=False,
        )
        
        # Test with uppercase
        response_upper = requests.get(
            f"{profiling_host_status_url}?service_name=DEVAPP",
            headers=credentials,
            timeout=10,
            verify=False,
        )

        assert response_lower.status_code == 200
        assert response_upper.status_code == 200

        result_lower = response_lower.json()
        result_upper = response_upper.json()
        
        # Both should return the same results
        assert len(result_lower) == len(result_upper), \
            "Case variations should return same results"







