#!/usr/bin/env python3
"""
Integration test for profile request creation and database verification.

This module contains integration tests that validate the complete flow from API request
to database storage, including:
1. Making API calls to create profile requests
2. Verifying database entries in PostgreSQL tables
3. Testing the full end-to-end flow from API to database
4. Validating data consistency between API responses and database state
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import pytest
import requests


@pytest.fixture(scope="session")
def postgres_connection(pytestconfig):
    """Create a PostgreSQL connection for database verification."""
    # Get PostgreSQL configuration from pytest config
    postgres_user = pytestconfig.getoption("--postgres-user", default="postgres")
    postgres_password = pytestconfig.getoption("--postgres-password", default="password")
    postgres_host = pytestconfig.getoption("--postgres-host", default="localhost")
    postgres_port = pytestconfig.getoption("--postgres-port", default=54321)
    postgres_db = pytestconfig.getoption("--postgres-db", default="gprofiler")

    # Create connection
    conn = psycopg2.connect(
        host=postgres_host,
        port=postgres_port,
        user=postgres_user,
        password=postgres_password,
        database=postgres_db,
    )
    conn.autocommit = True

    yield conn

    # Cleanup
    conn.close()


@pytest.fixture(scope="session")
def test_service_name() -> str:
    """Generate a unique service name for testing."""
    return f"test-service-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def test_hostname() -> str:
    """Generate a unique hostname for testing."""
    return f"test-host-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def profile_request_url(backend_base_url) -> str:
    """Get the full URL for the profile request endpoint."""
    return f"{backend_base_url}/api/metrics/profile_request"


@pytest.fixture(scope="session")
def heartbeat_url(backend_base_url) -> str:
    """Get the full URL for the heartbeat endpoint."""
    return f"{backend_base_url}/api/metrics/heartbeat"


@pytest.fixture(scope="session")
def db_setup_and_teardown(postgres_connection, test_service_name, test_hostname):
    print("\nCleaning up test data before tests...")
    cleanup_test_data(postgres_connection, test_service_name, test_hostname)

    yield  # This is where the tests will run

    print("\nCleaning up test data after tests...")
    cleanup_test_data(postgres_connection, test_service_name, test_hostname)


@pytest.fixture(scope="session")
def valid_heartbeat_data(test_hostname: str, test_service_name: str) -> Dict[str, Any]:
    """Provide valid heartbeat data for testing."""
    return {
        "hostname": test_hostname,
        "ip_address": "127.0.0.1",
        "service_name": test_service_name,
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "last_command_id": None,
    }


@pytest.fixture(scope="session")
def valid_start_request_data_single_host_stop_level_host(test_service_name: str, test_hostname: str) -> Dict[str, Any]:
    """Provide valid start request data for testing."""
    return {
        "service_name": test_service_name,
        "request_type": "start",
        "duration": 60,
        "frequency": 11,
        "profiling_mode": "cpu",
        "target_hosts": {
            test_hostname: None,
        },
        "stop_level": "host",
        "additional_args": {"test": True, "environment": "integration_test"},
    }


@pytest.fixture(scope="session")
def valid_stop_request_data_single_host_stop_level_host(test_service_name: str, test_hostname: str) -> Dict[str, Any]:
    """Provide valid stop request data for testing."""
    return {
        "service_name": test_service_name,
        "request_type": "stop",
        "target_hosts": {
            test_hostname: None,
        },
        "stop_level": "host",
    }


@pytest.fixture(scope="session")
def valid_start_request_data_single_host_stop_level_process_single_process(
    test_service_name: str, test_hostname: str
) -> Dict[str, Any]:
    """Provide valid start request data for testing."""
    return {
        "service_name": test_service_name,
        "request_type": "start",
        "duration": 60,
        "frequency": 11,
        "profiling_mode": "cpu",
        "target_hosts": {
            test_hostname: [1234],
        },  # Single PID for process-level profiling
        "stop_level": "process",
        "additional_args": {"test": True, "environment": "integration_test"},
    }


@pytest.fixture(scope="session")
def valid_stop_request_data_single_host_stop_level_process_single_process(
    test_service_name: str, test_hostname: str
) -> Dict[str, Any]:
    """Provide valid stop request data for testing."""
    return {
        "service_name": test_service_name,
        "request_type": "stop",
        "target_hosts": {
            test_hostname: [1234],  # Single PID for process-level stop
        },
        "stop_level": "process",
    }


@pytest.fixture(scope="session")
def valid_start_request_data_single_host_stop_level_process_multi_process(
    test_service_name: str, test_hostname: str
) -> Dict[str, Any]:
    """Provide valid start request data for testing."""
    return {
        "service_name": test_service_name,
        "request_type": "start",
        "duration": 60,
        "frequency": 11,
        "profiling_mode": "cpu",
        "target_hosts": {
            test_hostname: [1234, 5678],  # Multiple PIDs for process-level profiling
        },
        "stop_level": "process",
        "additional_args": {"test": True, "environment": "integration_test"},
    }


@pytest.fixture(scope="session")
def valid_stop_request_data_single_host_stop_level_process_multi_process(
    test_service_name: str, test_hostname: str
) -> Dict[str, Any]:
    """Provide valid stop request data for testing."""
    return {
        "service_name": test_service_name,
        "request_type": "stop",
        "target_hosts": {
            test_hostname: [1234, 5678],  # Multiple PIDs for process-level stop
        },
        "stop_level": "process",
    }


def get_profiling_request_from_db(conn, request_id: str) -> Optional[Dict[str, Any]]:
    """Get a profiling request from the database by request_id."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT * FROM ProfilingRequests
            WHERE request_id = %s
            """,
            (request_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_profiling_commands_from_db(
    conn, service_name: str, hostname: str = None, command_ids: list[str] = None
) -> List[Dict[str, Any]]:
    """Get profiling commands from the database by service and optionally hostname."""
    if command_ids:
        formatted_command_ids_ = [f"'{command_id}'" for command_id in command_ids]
        formatted_command_ids = f"({','.join(formatted_command_ids_)})"

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            f"""
            SELECT
                *
            FROM
                ProfilingCommands
            WHERE
                TRUE
                AND service_name = '{service_name}'
                AND {f"hostname = '{hostname}'" if hostname else "TRUE"}
                AND {f"command_id IN {formatted_command_ids}" if command_ids else "TRUE"}
            ORDER BY
                created_at DESC
            """,
        )

        results = cursor.fetchall()
        return [dict(result) for result in results]


def get_host_heartbeats_from_db(conn, hostname: str, service_name: str = None) -> List[Dict[str, Any]]:
    """Get host heartbeats from the database by hostname and optionally service."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        if service_name:
            cursor.execute(
                """
                SELECT * FROM HostHeartbeats
                WHERE hostname = %s AND service_name = %s
                ORDER BY heartbeat_timestamp DESC
                """,
                (hostname, service_name),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM HostHeartbeats
                WHERE hostname = %s
                ORDER BY heartbeat_timestamp DESC
                """,
                (hostname,),
            )
        results = cursor.fetchall()
        return [dict(result) for result in results]


def cleanup_test_data(conn, service_name: str, hostname: str = None):
    """Clean up test data from the database."""
    with conn.cursor() as cursor:
        # Clean up in reverse dependency order
        if hostname:
            cursor.execute("DELETE FROM HostHeartbeats WHERE hostname = %s", (hostname,))
            cursor.execute("DELETE FROM ProfilingCommands WHERE hostname = %s", (hostname,))
            cursor.execute("DELETE FROM ProfilingExecutions WHERE hostname = %s", (hostname,))

        cursor.execute("DELETE FROM ProfilingRequests WHERE service_name = %s", (service_name,))
        cursor.execute("DELETE FROM ProfilingCommands WHERE service_name = %s", (service_name,))


def send_heartbeat_and_verify(
    heartbeat_url: str,
    heartbeat_data: Dict[str, Any],
    credentials: Dict[str, Any],
    postgres_connection,
    expected_command_present: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Send a heartbeat request and verify the response and database entry.

    Returns the received command if any, None otherwise.
    """
    # Send heartbeat request
    response = requests.post(
        heartbeat_url,
        headers=credentials,
        json=heartbeat_data,
        timeout=10,
        verify=False,
    )

    # Verify heartbeat response
    assert response.status_code == 200, f"Heartbeat failed: {response.status_code}: {response.text}"
    result = response.json()
    assert "message" in result, "Heartbeat response should contain 'message' field"

    # Verify heartbeat was stored in database
    db_heartbeats = get_host_heartbeats_from_db(
        postgres_connection, heartbeat_data["hostname"], heartbeat_data["service_name"]
    )
    assert len(db_heartbeats) >= 1, "No heartbeat entries found in database"

    # Verify most recent heartbeat matches our data
    latest_heartbeat = db_heartbeats[0]
    assert latest_heartbeat["hostname"] == heartbeat_data["hostname"]
    assert latest_heartbeat["service_name"] == heartbeat_data["service_name"]
    assert latest_heartbeat["ip_address"] == heartbeat_data["ip_address"]
    assert latest_heartbeat["status"] == heartbeat_data["status"]

    # Check for command in response
    received_command = None
    profiling_command = result.get("profiling_command", None)
    command_id = result.get("command_id", None)
    if profiling_command and command_id:
        assert expected_command_present, "Received unexpected command in heartbeat response"
        received_command = {
            "command_id": result["command_id"],
            "profiling_command": result["profiling_command"],
        }
        print(
            f"📋 Received command via heartbeat: {result['profiling_command'].get('command_type', 'unknown')} (ID: {result['command_id']})"
        )
    else:
        assert not expected_command_present, "Expected command in heartbeat response but none received"
        print("📭 No commands received in heartbeat response")

    print(f"✅ Heartbeat successfully sent and verified in database for {heartbeat_data['hostname']}")
    return received_command


@pytest.mark.usefixtures("db_setup_and_teardown")
class TestProfileRequestIntegration:
    """Integration tests for profile request creation and database verification."""

    @pytest.mark.order(1)
    def test_create_start_profile_request_for_single_host_stop_level_host(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_start_request_data_single_host_stop_level_host: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test creating a start profile request, sending heartbeat, and verify database entries."""

        # Step 1: Make API call to create profile request
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_start_request_data_single_host_stop_level_host,
            timeout=10,
            verify=False,
        )

        # Verify API response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # Validate response structure
        assert "success" in result
        assert "message" in result
        assert "request_id" in result
        assert "command_ids" in result
        assert result["success"] is True

        request_id = result["request_id"]
        command_ids = result["command_ids"]

        # Verify request_id is a valid UUID
        assert request_id
        assert len(command_ids) >= 1

        # Step 2: Verify ProfilingRequests table entry
        db_request = get_profiling_request_from_db(postgres_connection, request_id)
        assert db_request is not None, f"Request {request_id} not found in database"

        # Verify request data matches what was sent
        assert db_request["service_name"] == valid_start_request_data_single_host_stop_level_host["service_name"]
        assert db_request["request_type"] == valid_start_request_data_single_host_stop_level_host["request_type"]
        assert db_request["duration"] == valid_start_request_data_single_host_stop_level_host["duration"]
        assert db_request["frequency"] == valid_start_request_data_single_host_stop_level_host["frequency"]
        assert db_request["profiling_mode"] == valid_start_request_data_single_host_stop_level_host["profiling_mode"]
        assert db_request["target_hostnames"] == list(
            valid_start_request_data_single_host_stop_level_host["target_hosts"].keys()
        )
        assert db_request["status"] == "pending"

        # Verify additional_args JSON
        stored_additional_args = db_request["additional_args"]
        if stored_additional_args:
            assert stored_additional_args == valid_start_request_data_single_host_stop_level_host["additional_args"]

        # Verify timestamps
        assert db_request["created_at"] is not None
        assert db_request["updated_at"] is not None

        # Step 3: Verify ProfilingCommands table entries
        db_commands = get_profiling_commands_from_db(
            postgres_connection,
            test_service_name,
            test_hostname,
            command_ids=command_ids,
        )
        assert len(db_commands) >= 1, "No commands found in database"

        # Verify at least one command matches our request
        command_found = False
        for db_command in db_commands:
            if db_command["command_id"] in command_ids:
                command_found = True
                assert db_command["hostname"] == test_hostname
                assert db_command["service_name"] == test_service_name
                assert db_command["command_type"] == "start"
                assert db_command["status"] == "pending"

                # Verify request_ids contains our request
                request_ids_in_command = db_command["request_ids"]
                assert request_id in request_ids_in_command

                # Verify combined_config contains expected fields
                combined_config = db_command["combined_config"]
                assert combined_config is not None
                assert (
                    combined_config.get("duration") == valid_start_request_data_single_host_stop_level_host["duration"]
                )
                assert (
                    combined_config.get("frequency")
                    == valid_start_request_data_single_host_stop_level_host["frequency"]
                )
                assert (
                    combined_config.get("profiling_mode")
                    == valid_start_request_data_single_host_stop_level_host["profiling_mode"]
                )

                break

        assert command_found, f"Command with ID in {command_ids} not found in database"

        # Step 4: Send heartbeat and verify command delivery
        print("🔄 Sending heartbeat to retrieve commands...")
        received_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 5: Verify the received command matches our created command
        assert received_command is not None, "Expected to receive a command via heartbeat"
        assert (
            received_command["command_id"] in command_ids
        ), f"Received command ID {received_command['command_id']} not in expected IDs {command_ids}"

        # Verify command content
        profiling_command = received_command["profiling_command"]
        assert profiling_command["command_type"] == "start"
        assert (
            profiling_command["combined_config"]["duration"]
            == valid_start_request_data_single_host_stop_level_host["duration"]
        )
        assert (
            profiling_command["combined_config"]["frequency"]
            == valid_start_request_data_single_host_stop_level_host["frequency"]
        )
        assert (
            profiling_command["combined_config"]["profiling_mode"]
            == valid_start_request_data_single_host_stop_level_host["profiling_mode"]
        )

        # Step 6: Send another heartbeat with last_command_id to simulate acknowledgment
        print("🔄 Sending acknowledgment heartbeat...")
        heartbeat_with_ack = valid_heartbeat_data.copy()
        heartbeat_with_ack["last_command_id"] = received_command["command_id"]

        ack_command = send_heartbeat_and_verify(
            heartbeat_url,
            heartbeat_with_ack,
            credentials,
            postgres_connection,
            expected_command_present=False,  # Should not receive the same command again
        )

        # Should not receive the same command again
        assert ack_command is None, "Should not receive the same command after acknowledgment"

        print(
            f"✅ End-to-end integration test passed: Request {request_id} created, command delivered via heartbeat, and acknowledged"
        )

    @pytest.mark.order(2)
    def test_create_stop_profile_request_for_single_host_stop_level_host(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_stop_request_data_single_host_stop_level_host: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test creating a stop profile request, sending heartbeat, and verify database entries."""

        # Step 1: Make API call to create stop profile request
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_stop_request_data_single_host_stop_level_host,
            timeout=10,
            verify=False,
        )

        # Verify API response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # Validate response structure
        assert "success" in result
        assert "message" in result
        assert "request_id" in result
        assert "command_ids" in result
        assert result["success"] is True

        request_id = result["request_id"]
        command_ids = result["command_ids"]

        # Step 2: Verify ProfilingRequests table entry
        db_request = get_profiling_request_from_db(postgres_connection, request_id)
        assert db_request is not None, f"Request {request_id} not found in database"

        # Verify request data matches what was sent
        assert db_request["service_name"] == valid_stop_request_data_single_host_stop_level_host["service_name"]
        assert db_request["request_type"] == valid_stop_request_data_single_host_stop_level_host["request_type"]
        assert db_request["target_hostnames"] == list(
            valid_stop_request_data_single_host_stop_level_host["target_hosts"].keys()
        )
        assert db_request["status"] == "pending"

        # Step 3: Verify ProfilingCommands table entries for stop command
        db_commands = get_profiling_commands_from_db(postgres_connection, test_service_name, test_hostname)

        # For stop commands, there should be at least one command
        if len(command_ids) > 0:
            assert len(db_commands) >= 1, "No stop commands found in database"

            # Verify stop command properties
            stop_command_found = False
            for db_command in db_commands:
                if db_command["command_id"] in command_ids:
                    stop_command_found = True
                    assert db_command["hostname"] == test_hostname
                    assert db_command["service_name"] == test_service_name
                    assert db_command["command_type"] == "stop"
                    assert db_command["status"] == "pending"
                    break

            assert stop_command_found, f"Stop command with ID in {command_ids} not found in database"

        # Step 4: Send heartbeat and verify stop command delivery
        print("🔄 Sending heartbeat to retrieve stop commands...")
        received_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 5: Verify the received command matches our created stop command
        assert received_command is not None, "Expected to receive a stop command via heartbeat"
        assert (
            received_command["command_id"] in command_ids
        ), f"Received command ID {received_command['command_id']} not in expected IDs {command_ids}"

        # Verify stop command content
        profiling_command = received_command["profiling_command"]
        assert profiling_command["command_type"] == "stop"
        assert (
            profiling_command["combined_config"]["stop_level"]
            == valid_stop_request_data_single_host_stop_level_host["stop_level"]
        )

        # Step 6: Send acknowledgment heartbeat
        print("🔄 Sending acknowledgment heartbeat for stop command...")
        heartbeat_with_ack = valid_heartbeat_data.copy()
        heartbeat_with_ack["last_command_id"] = received_command["command_id"]

        ack_command = send_heartbeat_and_verify(
            heartbeat_url,
            heartbeat_with_ack,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        assert ack_command is None, "Should not receive the same stop command after acknowledgment"

        print(
            f"✅ End-to-end stop integration test passed: Stop request {request_id} created, command delivered via heartbeat, and acknowledged"
        )

    @pytest.mark.order(3)
    def test_create_start_profile_request_for_single_host_stop_level_process_single_process(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_start_request_data_single_host_stop_level_process_single_process: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test creating a start profile request with single process PID, sending heartbeat, and verify database entries."""

        # Step 1: Make API call to create profile request
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_start_request_data_single_host_stop_level_process_single_process,
            timeout=10,
            verify=False,
        )

        # Verify API response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # Validate response structure
        assert "success" in result
        assert "message" in result
        assert "request_id" in result
        assert "command_ids" in result
        assert result["success"] is True

        request_id = result["request_id"]
        command_ids = result["command_ids"]

        # Verify request_id is a valid UUID
        assert request_id
        assert len(command_ids) >= 1

        # Step 2: Verify ProfilingRequests table entry
        db_request = get_profiling_request_from_db(postgres_connection, request_id)
        assert db_request is not None, f"Request {request_id} not found in database"

        # Verify request data matches what was sent
        assert (
            db_request["service_name"]
            == valid_start_request_data_single_host_stop_level_process_single_process["service_name"]
        )
        assert (
            db_request["request_type"]
            == valid_start_request_data_single_host_stop_level_process_single_process["request_type"]
        )
        assert (
            db_request["duration"] == valid_start_request_data_single_host_stop_level_process_single_process["duration"]
        )
        assert (
            db_request["frequency"]
            == valid_start_request_data_single_host_stop_level_process_single_process["frequency"]
        )
        assert (
            db_request["profiling_mode"]
            == valid_start_request_data_single_host_stop_level_process_single_process["profiling_mode"]
        )
        assert db_request["target_hostnames"] == list(
            valid_start_request_data_single_host_stop_level_process_single_process["target_hosts"].keys()
        )
        assert (
            db_request["stop_level"]
            == valid_start_request_data_single_host_stop_level_process_single_process["stop_level"]
        )
        assert db_request["status"] == "pending"

        # Verify additional_args JSON
        stored_additional_args = db_request["additional_args"]
        if stored_additional_args:
            assert (
                stored_additional_args
                == valid_start_request_data_single_host_stop_level_process_single_process["additional_args"]
            )

        # Verify timestamps
        assert db_request["created_at"] is not None
        assert db_request["updated_at"] is not None

        # Step 3: Verify ProfilingCommands table entries
        db_commands = get_profiling_commands_from_db(
            postgres_connection,
            test_service_name,
            test_hostname,
            command_ids=command_ids,
        )
        assert len(db_commands) >= 1, "No commands found in database"

        # Verify at least one command matches our request
        command_found = False
        for db_command in db_commands:
            if db_command["command_id"] in command_ids:
                command_found = True
                assert db_command["hostname"] == test_hostname
                assert db_command["service_name"] == test_service_name
                assert db_command["command_type"] == "start"
                assert db_command["status"] == "pending"

                # Verify request_ids contains our request
                request_ids_in_command = db_command["request_ids"]
                assert request_id in request_ids_in_command

                # Verify combined_config contains expected fields including PIDs
                combined_config = db_command["combined_config"]
                assert combined_config is not None
                assert (
                    combined_config.get("duration")
                    == valid_start_request_data_single_host_stop_level_process_single_process["duration"]
                )
                assert (
                    combined_config.get("frequency")
                    == valid_start_request_data_single_host_stop_level_process_single_process["frequency"]
                )
                assert (
                    combined_config.get("profiling_mode")
                    == valid_start_request_data_single_host_stop_level_process_single_process["profiling_mode"]
                )
                assert (
                    combined_config.get("pids")
                    == valid_start_request_data_single_host_stop_level_process_single_process["target_hosts"][
                        test_hostname
                    ]
                )

                break

        assert command_found, f"Command with ID in {command_ids} not found in database"

        # Step 4: Send heartbeat and verify command delivery
        print("🔄 Sending heartbeat to retrieve process-level start commands...")
        received_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 5: Verify the received command matches our created command
        assert received_command is not None, "Expected to receive a command via heartbeat"
        assert (
            received_command["command_id"] in command_ids
        ), f"Received command ID {received_command['command_id']} not in expected IDs {command_ids}"

        # Verify command content including process-level details
        profiling_command = received_command["profiling_command"]
        assert profiling_command["command_type"] == "start"
        assert (
            profiling_command["combined_config"]["duration"]
            == valid_start_request_data_single_host_stop_level_process_single_process["duration"]
        )
        assert (
            profiling_command["combined_config"]["frequency"]
            == valid_start_request_data_single_host_stop_level_process_single_process["frequency"]
        )
        assert (
            profiling_command["combined_config"]["profiling_mode"]
            == valid_start_request_data_single_host_stop_level_process_single_process["profiling_mode"]
        )
        assert (
            profiling_command["combined_config"]["pids"]
            == valid_start_request_data_single_host_stop_level_process_single_process["target_hosts"][test_hostname]
        )

        # Step 6: Send another heartbeat with last_command_id to simulate acknowledgment
        print("🔄 Sending acknowledgment heartbeat for process-level start command...")
        heartbeat_with_ack = valid_heartbeat_data.copy()
        heartbeat_with_ack["last_command_id"] = received_command["command_id"]

        ack_command = send_heartbeat_and_verify(
            heartbeat_url,
            heartbeat_with_ack,
            credentials,
            postgres_connection,
            expected_command_present=False,  # Should not receive the same command again
        )

        # Should not receive the same command again
        assert ack_command is None, "Should not receive the same command after acknowledgment"

        print(
            f"✅ End-to-end process-level start integration test passed: Request {request_id} with PID {valid_start_request_data_single_host_stop_level_process_single_process['target_hosts'][test_hostname]} created, command delivered via heartbeat, and acknowledged"
        )

    @pytest.mark.order(4)
    def test_create_stop_profile_request_for_single_host_stop_level_process_single_process(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_stop_request_data_single_host_stop_level_process_single_process: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test creating a stop profile request with single process PID, sending heartbeat, and verify database entries."""

        # Step 1: Make API call to create stop profile request
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_stop_request_data_single_host_stop_level_process_single_process,
            timeout=10,
            verify=False,
        )

        # Verify API response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # Validate response structure
        assert "success" in result
        assert "message" in result
        assert "request_id" in result
        assert "command_ids" in result
        assert result["success"] is True

        request_id = result["request_id"]
        command_ids = result["command_ids"]

        # Step 2: Verify ProfilingRequests table entry
        db_request = get_profiling_request_from_db(postgres_connection, request_id)
        assert db_request is not None, f"Request {request_id} not found in database"

        # Verify request data matches what was sent
        assert (
            db_request["service_name"]
            == valid_stop_request_data_single_host_stop_level_process_single_process["service_name"]
        )
        assert (
            db_request["request_type"]
            == valid_stop_request_data_single_host_stop_level_process_single_process["request_type"]
        )
        assert db_request["target_hostnames"] == list(
            valid_stop_request_data_single_host_stop_level_process_single_process["target_hosts"].keys()
        )
        assert db_request["status"] == "pending"

        # Step 3: Verify ProfilingCommands table entries for stop command
        db_commands = get_profiling_commands_from_db(postgres_connection, test_service_name, test_hostname)

        # For stop commands, there should be at least one command
        if len(command_ids) > 0:
            assert len(db_commands) >= 1, "No stop commands found in database"

            # Verify stop command properties
            stop_command_found = False
            for db_command in db_commands:
                if db_command["command_id"] in command_ids:
                    stop_command_found = True
                    assert db_command["hostname"] == test_hostname
                    assert db_command["service_name"] == test_service_name
                    assert db_command["command_type"] == "stop"
                    assert db_command["status"] == "pending"
                    break

            assert stop_command_found, f"Stop command with ID in {command_ids} not found in database"

        # Step 4: Send heartbeat and verify stop command delivery
        print("🔄 Sending heartbeat to retrieve stop commands...")
        received_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 5: Verify the received command matches our created stop command
        assert received_command is not None, "Expected to receive a stop command via heartbeat"
        assert (
            received_command["command_id"] in command_ids
        ), f"Received command ID {received_command['command_id']} not in expected IDs {command_ids}"

        # Verify stop command content
        profiling_command = received_command["profiling_command"]
        assert profiling_command["command_type"] == "stop"
        # For this test case, we stop all PIDs for the host
        # Then the stop command should stop the entire host
        assert profiling_command["combined_config"]["stop_level"] == "host"

        # Step 6: Send acknowledgment heartbeat
        print("🔄 Sending acknowledgment heartbeat for stop command...")
        heartbeat_with_ack = valid_heartbeat_data.copy()
        heartbeat_with_ack["last_command_id"] = received_command["command_id"]

        ack_command = send_heartbeat_and_verify(
            heartbeat_url,
            heartbeat_with_ack,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        assert ack_command is None, "Should not receive the same stop command after acknowledgment"

        print(
            f"✅ End-to-end process-level stop integration test passed: Stop request {request_id} with PID {valid_stop_request_data_single_host_stop_level_process_single_process['target_hosts'][test_hostname]} created, command delivered via heartbeat, and acknowledged"
        )

    @pytest.mark.order(5)
    def test_create_start_profile_request_for_single_host_stop_level_process_multi_process(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_start_request_data_single_host_stop_level_process_multi_process: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test creating a start profile request with multiple process PIDs, sending heartbeat, and verify database entries."""

        # Step 1: Make API call to create profile request
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_start_request_data_single_host_stop_level_process_multi_process,
            timeout=10,
            verify=False,
        )

        # Verify API response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # Validate response structure
        assert "success" in result
        assert "message" in result
        assert "request_id" in result
        assert "command_ids" in result
        assert result["success"] is True

        request_id = result["request_id"]
        command_ids = result["command_ids"]

        # Verify request_id is a valid UUID
        assert request_id
        assert len(command_ids) >= 1

        # Step 2: Verify ProfilingRequests table entry
        db_request = get_profiling_request_from_db(postgres_connection, request_id)
        assert db_request is not None, f"Request {request_id} not found in database"

        # Verify request data matches what was sent
        assert (
            db_request["service_name"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["service_name"]
        )
        assert (
            db_request["request_type"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["request_type"]
        )
        assert (
            db_request["duration"] == valid_start_request_data_single_host_stop_level_process_multi_process["duration"]
        )
        assert (
            db_request["frequency"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["frequency"]
        )
        assert (
            db_request["profiling_mode"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["profiling_mode"]
        )
        assert db_request["target_hostnames"] == list(
            valid_start_request_data_single_host_stop_level_process_multi_process["target_hosts"].keys()
        )
        assert (
            db_request["stop_level"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["stop_level"]
        )
        assert db_request["status"] == "pending"

        # Verify additional_args JSON
        stored_additional_args = db_request["additional_args"]
        if stored_additional_args:
            assert (
                stored_additional_args
                == valid_start_request_data_single_host_stop_level_process_multi_process["additional_args"]
            )

        # Verify timestamps
        assert db_request["created_at"] is not None
        assert db_request["updated_at"] is not None

        # Step 3: Verify ProfilingCommands table entries
        db_commands = get_profiling_commands_from_db(
            postgres_connection,
            test_service_name,
            test_hostname,
            command_ids=command_ids,
        )
        assert len(db_commands) >= 1, "No commands found in database"

        # Verify at least one command matches our request
        command_found = False
        for db_command in db_commands:
            if db_command["command_id"] in command_ids:
                command_found = True
                assert db_command["hostname"] == test_hostname
                assert db_command["service_name"] == test_service_name
                assert db_command["command_type"] == "start"
                assert db_command["status"] == "pending"

                # Verify request_ids contains our request
                request_ids_in_command = db_command["request_ids"]
                assert request_id in request_ids_in_command

                # Verify combined_config contains expected fields including multiple PIDs
                combined_config = db_command["combined_config"]
                assert combined_config is not None
                assert (
                    combined_config.get("duration")
                    == valid_start_request_data_single_host_stop_level_process_multi_process["duration"]
                )
                assert (
                    combined_config.get("frequency")
                    == valid_start_request_data_single_host_stop_level_process_multi_process["frequency"]
                )
                assert (
                    combined_config.get("profiling_mode")
                    == valid_start_request_data_single_host_stop_level_process_multi_process["profiling_mode"]
                )
                assert (
                    combined_config.get("pids")
                    == valid_start_request_data_single_host_stop_level_process_multi_process["target_hosts"][
                        test_hostname
                    ]
                )

                # Verify multiple PIDs are correctly stored
                expected_pids = valid_start_request_data_single_host_stop_level_process_multi_process["target_hosts"][
                    test_hostname
                ]
                assert len(combined_config.get("pids", [])) == len(
                    expected_pids
                ), f"Expected {len(expected_pids)} PIDs, got {len(combined_config.get('pids', []))}"
                for pid in expected_pids:
                    assert pid in combined_config.get("pids", []), f"PID {pid} not found in command config"

                break

        assert command_found, f"Command with ID in {command_ids} not found in database"

        # Step 4: Send heartbeat and verify command delivery
        print("🔄 Sending heartbeat to retrieve multi-process start commands...")
        received_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 5: Verify the received command matches our created command
        assert received_command is not None, "Expected to receive a command via heartbeat"
        assert (
            received_command["command_id"] in command_ids
        ), f"Received command ID {received_command['command_id']} not in expected IDs {command_ids}"

        # Verify command content including multi-process details
        profiling_command = received_command["profiling_command"]
        assert profiling_command["command_type"] == "start"
        assert (
            profiling_command["combined_config"]["duration"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["duration"]
        )
        assert (
            profiling_command["combined_config"]["frequency"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["frequency"]
        )
        assert (
            profiling_command["combined_config"]["profiling_mode"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["profiling_mode"]
        )
        assert (
            profiling_command["combined_config"]["pids"]
            == valid_start_request_data_single_host_stop_level_process_multi_process["target_hosts"][test_hostname]
        )

        # Step 6: Send another heartbeat with last_command_id to simulate acknowledgment
        print("🔄 Sending acknowledgment heartbeat for multi-process start command...")
        heartbeat_with_ack = valid_heartbeat_data.copy()
        heartbeat_with_ack["last_command_id"] = received_command["command_id"]

        ack_command = send_heartbeat_and_verify(
            heartbeat_url,
            heartbeat_with_ack,
            credentials,
            postgres_connection,
            expected_command_present=False,  # Should not receive the same command again
        )

        # Should not receive the same command again
        assert ack_command is None, "Should not receive the same command after acknowledgment"

        print(
            f"✅ End-to-end multi-process start integration test passed: Request {request_id} with PIDs {valid_start_request_data_single_host_stop_level_process_multi_process['target_hosts'][test_hostname]} created, command delivered via heartbeat, and acknowledged"
        )

    @pytest.mark.order(6)
    def test_create_stop_profile_request_for_single_host_stop_level_process_multi_process(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_start_request_data_single_host_stop_level_process_multi_process: Dict[str, Any],
        valid_stop_request_data_single_host_stop_level_process_multi_process: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test creating a stop profile request with multiple process PIDs, sending heartbeat, and verify database entries."""

        # Step 1: Make API call to create stop profile request
        response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_stop_request_data_single_host_stop_level_process_multi_process,
            timeout=10,
            verify=False,
        )

        # Verify API response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # Validate response structure
        assert "success" in result
        assert "message" in result
        assert "request_id" in result
        assert "command_ids" in result
        assert result["success"] is True

        request_id = result["request_id"]
        command_ids = result["command_ids"]

        # Step 2: Verify ProfilingRequests table entry
        db_request = get_profiling_request_from_db(postgres_connection, request_id)
        assert db_request is not None, f"Request {request_id} not found in database"

        # Verify request data matches what was sent
        assert (
            db_request["service_name"]
            == valid_stop_request_data_single_host_stop_level_process_multi_process["service_name"]
        )
        assert (
            db_request["request_type"]
            == valid_stop_request_data_single_host_stop_level_process_multi_process["request_type"]
        )
        assert db_request["target_hostnames"] == list(
            valid_stop_request_data_single_host_stop_level_process_multi_process["target_hosts"].keys()
        )
        assert (
            db_request["stop_level"]
            == valid_stop_request_data_single_host_stop_level_process_multi_process["stop_level"]
        )
        assert db_request["status"] == "pending"

        # Step 3: Verify ProfilingCommands table entries for stop command
        db_commands = get_profiling_commands_from_db(postgres_connection, test_service_name, test_hostname)

        # For stop commands, there should be at least one command
        if len(command_ids) > 0:
            assert len(db_commands) >= 1, "No stop commands found in database"

            # Verify stop command properties
            stop_command_found = False
            for db_command in db_commands:
                if db_command["command_id"] in command_ids:
                    stop_command_found = True
                    assert db_command["hostname"] == test_hostname
                    assert db_command["service_name"] == test_service_name
                    assert db_command["command_type"] == "stop"
                    assert db_command["status"] == "pending"

                    # For this test case, we stop all PIDs for the host
                    # Then the stop command should stop the entire host
                    combined_config = db_command["combined_config"]
                    assert combined_config is not None
                    assert combined_config.get("stop_level") == "host"
                    break

            assert stop_command_found, f"Stop command with ID in {command_ids} not found in database"

        # Step 4: Send heartbeat and verify stop command delivery
        print("🔄 Sending heartbeat to retrieve multi-process stop commands...")
        received_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 5: Verify the received command matches our created stop command
        assert received_command is not None, "Expected to receive a stop command via heartbeat"
        assert (
            received_command["command_id"] in command_ids
        ), f"Received command ID {received_command['command_id']} not in expected IDs {command_ids}"

        # Verify stop command content including multi-process details
        profiling_command = received_command["profiling_command"]
        assert profiling_command["command_type"] == "stop"
        # For this test case, we stop all PIDs for the host
        # Then the stop command should stop the entire host
        assert profiling_command["combined_config"]["stop_level"] == "host"

        # Step 6: Send acknowledgment heartbeat
        print("🔄 Sending acknowledgment heartbeat for multi-process stop command...")
        heartbeat_with_ack = valid_heartbeat_data.copy()
        heartbeat_with_ack["last_command_id"] = received_command["command_id"]

        ack_command = send_heartbeat_and_verify(
            heartbeat_url,
            heartbeat_with_ack,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        assert ack_command is None, "Should not receive the same stop command after acknowledgment"

        print(
            f"✅ End-to-end multi-process stop integration test passed: Stop request {request_id} with PID {valid_stop_request_data_single_host_stop_level_process_multi_process['target_hosts'][test_hostname]} created, command delivered via heartbeat, and acknowledged"
        )

    @pytest.mark.order(7)
    def test_start_multi_process_then_stop_single_process_verify_remaining_pids(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_start_request_data_single_host_stop_level_process_multi_process: Dict[str, Any],
        valid_stop_request_data_single_host_stop_level_process_single_process: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test starting multi-process profiling, then stopping single process, and verify remaining PIDs continue profiling."""

        # Step 1: Start profiling multiple PIDs
        print("🚀 Step 1: Starting profiling for multiple PIDs...")
        start_response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_start_request_data_single_host_stop_level_process_multi_process,
            timeout=10,
            verify=False,
        )

        assert (
            start_response.status_code == 200
        ), f"Start request failed: {start_response.status_code}: {start_response.text}"
        start_result = start_response.json()

        start_request_id = start_result["request_id"]

        print(f"✅ Multi-process start request created: {start_request_id}")

        # Step 2: Send heartbeat to get the initial start command
        print("🔄 Step 2: Retrieving initial multi-process start command...")
        initial_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Verify initial command has multiple PIDs
        assert initial_command is not None, "Expected to receive initial start command"
        initial_pids = initial_command["profiling_command"]["combined_config"]["pids"]
        expected_initial_pids = valid_start_request_data_single_host_stop_level_process_multi_process["target_hosts"][
            test_hostname
        ]

        assert len(initial_pids) == len(
            expected_initial_pids
        ), f"Expected {len(expected_initial_pids)} initial PIDs, got {len(initial_pids)}"
        for pid in expected_initial_pids:
            assert pid in initial_pids, f"PID {pid} not found in initial command"

        print(f"✅ Initial start command received with PIDs: {initial_pids}")

        # Step 3: Acknowledge the initial command
        print("🔄 Step 3: Acknowledging initial multi-process start command...")
        ack_heartbeat = valid_heartbeat_data.copy()
        ack_heartbeat["last_command_id"] = initial_command["command_id"]

        ack_response = send_heartbeat_and_verify(
            heartbeat_url,
            ack_heartbeat,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        assert ack_response is None, "Should not receive command after acknowledgment"
        print("✅ Initial command acknowledged successfully")

        # Step 4: Stop profiling for single PID
        print("🛑 Step 4: Stopping profiling for single PID...")
        stop_response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_stop_request_data_single_host_stop_level_process_single_process,
            timeout=10,
            verify=False,
        )

        assert (
            stop_response.status_code == 200
        ), f"Stop request failed: {stop_response.status_code}: {stop_response.text}"
        stop_result = stop_response.json()

        stop_request_id = stop_result["request_id"]

        print(f"✅ Single-process stop request created: {stop_request_id}")

        # Step 5: Send heartbeat to get the resulting command (should be start with remaining PIDs)
        print("🔄 Step 5: Retrieving command after stopping single PID...")
        resulting_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 6: Verify the resulting command is a start command with remaining PIDs
        assert resulting_command is not None, "Expected to receive resulting command"

        profiling_command = resulting_command["profiling_command"]
        assert (
            profiling_command["command_type"] == "start"
        ), f"Expected 'start' command, got '{profiling_command['command_type']}'"

        # Calculate expected remaining PIDs
        stopped_pids = valid_stop_request_data_single_host_stop_level_process_single_process["target_hosts"][
            test_hostname
        ]
        remaining_pids = [pid for pid in expected_initial_pids if pid not in stopped_pids]

        # Verify remaining PIDs in the command
        command_pids = profiling_command["combined_config"]["pids"]
        assert len(command_pids) == len(
            remaining_pids
        ), f"Expected {len(remaining_pids)} remaining PIDs, got {len(command_pids)}"

        for pid in remaining_pids:
            assert pid in command_pids, f"Remaining PID {pid} not found in command"

        for pid in stopped_pids:
            assert pid not in command_pids, f"Stopped PID {pid} should not be in command"

        print(f"✅ Resulting start command has correct remaining PIDs: {command_pids}")
        print(
            f"🎯 Successfully verified differential PID management: Started {expected_initial_pids}, stopped {stopped_pids}, remaining {remaining_pids}"
        )

        # Step 7: Acknowledge the resulting command
        print("🔄 Step 7: Acknowledging resulting command...")
        final_ack_heartbeat = valid_heartbeat_data.copy()
        assert resulting_command is not None, "resulting_command is None, cannot access 'command_id'"
        final_ack_heartbeat["last_command_id"] = resulting_command["command_id"]

        final_ack_response = send_heartbeat_and_verify(
            heartbeat_url,
            final_ack_heartbeat,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        assert final_ack_response is None, "Should not receive command after final acknowledgment"

        print(
            f"✅ End-to-end differential PID management test passed: Started PIDs {expected_initial_pids}, stopped PIDs {stopped_pids}, remaining PIDs {remaining_pids} continue profiling"
        )

    @pytest.mark.order(8)
    def test_start_multi_process_then_stop_single_process_database_consistency(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_start_request_data_single_host_stop_level_process_multi_process: Dict[str, Any],
        valid_stop_request_data_single_host_stop_level_process_single_process: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test database consistency when starting multi-process profiling then stopping single process."""

        # Step 1: Create start request for multiple PIDs
        print("🚀 Step 1: Creating start request for multiple PIDs...")
        start_response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_start_request_data_single_host_stop_level_process_multi_process,
            timeout=10,
            verify=False,
        )

        assert start_response.status_code == 200
        start_result = start_response.json()
        start_request_id = start_result["request_id"]

        # Verify start request in database
        db_start_request = get_profiling_request_from_db(postgres_connection, start_request_id)
        assert db_start_request is not None
        assert db_start_request["request_type"] == "start"
        assert db_start_request["target_hostnames"] == [test_hostname]

        print(f"✅ Start request verified in database: {start_request_id}")

        # Step 2: Get initial start command via heartbeat
        print("🔄 Step 2: Getting initial start command...")
        initial_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Acknowledge initial command
        ack_heartbeat = valid_heartbeat_data.copy()
        assert initial_command is not None, "Expected to receive initial command via heartbeat"
        ack_heartbeat["last_command_id"] = initial_command["command_id"]
        send_heartbeat_and_verify(
            heartbeat_url,
            ack_heartbeat,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        # Step 3: Create stop request for single PID
        print("🛑 Step 3: Creating stop request for single PID...")
        stop_response = requests.post(
            profile_request_url,
            headers=credentials,
            json=valid_stop_request_data_single_host_stop_level_process_single_process,
            timeout=10,
            verify=False,
        )

        assert stop_response.status_code == 200
        stop_result = stop_response.json()
        stop_request_id = stop_result["request_id"]

        # Step 4: Verify database entries for both requests
        print("🔍 Step 4: Verifying database consistency...")

        # Verify stop request in database
        db_stop_request = get_profiling_request_from_db(postgres_connection, stop_request_id)
        assert db_stop_request is not None
        assert db_stop_request["request_type"] == "stop"
        assert db_stop_request["target_hostnames"] == [test_hostname]

        # Verify ProfilingCommands table has correct entries
        db_commands = get_profiling_commands_from_db(postgres_connection, test_service_name, test_hostname)

        # Should have at least one command entry for the resulting state
        assert len(db_commands) >= 1, "No commands found in database"

        # Find the most recent command (should be start with remaining PIDs)
        most_recent_command = db_commands[0]  # Commands are ordered by created_at DESC

        # Step 5: Get the resulting command via heartbeat and verify database consistency
        print("🔄 Step 5: Getting resulting command and verifying database consistency...")
        resulting_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Verify command consistency between database and heartbeat response
        assert resulting_command is not None, "Expected to receive resulting command via heartbeat"
        assert resulting_command["command_id"] == most_recent_command["command_id"]
        assert resulting_command["profiling_command"]["command_type"] == most_recent_command["command_type"]

        # Verify PID consistency
        assert resulting_command is not None, "resulting_command is None, cannot access 'profiling_command'"
        heartbeat_pids = resulting_command["profiling_command"]["combined_config"]["pids"]
        db_pids = most_recent_command["combined_config"]["pids"]

        assert heartbeat_pids == db_pids, f"PID mismatch: heartbeat={heartbeat_pids}, database={db_pids}"

        # Calculate and verify expected remaining PIDs
        initial_pids = valid_start_request_data_single_host_stop_level_process_multi_process["target_hosts"][
            test_hostname
        ]
        stopped_pids = valid_stop_request_data_single_host_stop_level_process_single_process["target_hosts"][
            test_hostname
        ]
        expected_remaining_pids = [pid for pid in initial_pids if pid not in stopped_pids]

        assert set(heartbeat_pids) == set(
            expected_remaining_pids
        ), f"Expected remaining PIDs {expected_remaining_pids}, got {heartbeat_pids}"

        # Step 6: Verify HostHeartbeats table entries
        print("🔍 Step 6: Verifying heartbeat history in database...")
        heartbeat_entries = get_host_heartbeats_from_db(postgres_connection, test_hostname, test_service_name)

        # Should have multiple heartbeat entries from our test
        assert len(heartbeat_entries) == 1, f"Expected one heartbeat entry, got {len(heartbeat_entries)}"

        # Verify latest heartbeat entry
        latest_heartbeat = heartbeat_entries[0]
        assert latest_heartbeat["hostname"] == test_hostname
        assert latest_heartbeat["service_name"] == test_service_name
        assert latest_heartbeat["status"] == "active"

        # Final acknowledgment
        final_ack_heartbeat = valid_heartbeat_data.copy()
        assert resulting_command is not None, "resulting_command is None, cannot access 'command_id'"
        final_ack_heartbeat["last_command_id"] = resulting_command["command_id"]
        send_heartbeat_and_verify(
            heartbeat_url,
            final_ack_heartbeat,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        print(
            "✅ Database consistency test passed: All database tables (ProfilingRequests, ProfilingCommands, HostHeartbeats) maintain consistency throughout differential PID management workflow"
        )
        print(f"🎯 Verified workflow: Start {initial_pids} → Stop {stopped_pids} → Continue {expected_remaining_pids}")

    @pytest.mark.order(9)
    def test_start_profiling_then_update_frequency_verify_command_update(
        self,
        profile_request_url: str,
        heartbeat_url: str,
        valid_start_request_data_single_host_stop_level_host: Dict[str, Any],
        valid_heartbeat_data: Dict[str, Any],
        credentials: Dict[str, Any],
        postgres_connection,
        test_service_name: str,
        test_hostname: str,
    ):
        """Test creating a profiling request, then updating it with different frequency, and verify the resulting command has updated frequency."""

        # Step 1: Create initial profiling request
        print("🚀 Step 1: Creating initial profiling request...")
        initial_request_data = valid_start_request_data_single_host_stop_level_host.copy()
        initial_frequency = initial_request_data["frequency"]

        initial_response = requests.post(
            profile_request_url,
            headers=credentials,
            json=initial_request_data,
            timeout=10,
            verify=False,
        )

        assert (
            initial_response.status_code == 200
        ), f"Initial request failed: {initial_response.status_code}: {initial_response.text}"
        initial_result = initial_response.json()

        initial_request_id = initial_result["request_id"]

        print(f"✅ Initial profiling request created: {initial_request_id} with frequency {initial_frequency}")

        # Step 2: Send heartbeat to get the initial command
        print("🔄 Step 2: Retrieving initial profiling command...")
        initial_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Verify initial command has the original frequency
        assert initial_command is not None, "Expected to receive initial command"
        initial_cmd_frequency = initial_command["profiling_command"]["combined_config"]["frequency"]
        assert (
            initial_cmd_frequency == initial_frequency
        ), f"Expected initial frequency {initial_frequency}, got {initial_cmd_frequency}"

        print(f"✅ Initial command received with frequency: {initial_cmd_frequency}")

        # Step 3: Acknowledge the initial command
        print("🔄 Step 3: Acknowledging initial command...")
        ack_heartbeat = valid_heartbeat_data.copy()
        ack_heartbeat["last_command_id"] = initial_command["command_id"]

        ack_response = send_heartbeat_and_verify(
            heartbeat_url,
            ack_heartbeat,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        assert ack_response is None, "Should not receive command after acknowledgment"
        print("✅ Initial command acknowledged successfully")

        # Step 4: Create updated profiling request with different frequency
        print("🔄 Step 4: Creating updated profiling request with different frequency...")
        updated_request_data = initial_request_data.copy()
        updated_frequency = initial_frequency + 5  # Change frequency by adding 5
        updated_request_data["frequency"] = updated_frequency

        updated_response = requests.post(
            profile_request_url,
            headers=credentials,
            json=updated_request_data,
            timeout=10,
            verify=False,
        )

        assert (
            updated_response.status_code == 200
        ), f"Updated request failed: {updated_response.status_code}: {updated_response.text}"
        updated_result = updated_response.json()

        updated_request_id = updated_result["request_id"]
        updated_command_ids = updated_result["command_ids"]

        print(f"✅ Updated profiling request created: {updated_request_id} with frequency {updated_frequency}")

        # Step 5: Send heartbeat to get the updated command
        print("🔄 Step 5: Retrieving updated profiling command...")
        updated_command = send_heartbeat_and_verify(
            heartbeat_url,
            valid_heartbeat_data,
            credentials,
            postgres_connection,
            expected_command_present=True,
        )

        # Step 6: Verify the updated command is a start command with the new frequency
        assert updated_command is not None, "Expected to receive updated command"

        profiling_command = updated_command["profiling_command"]
        assert (
            profiling_command["command_type"] == "start"
        ), f"Expected 'start' command, got '{profiling_command['command_type']}'"

        # Verify the command has the updated frequency
        command_frequency = profiling_command["combined_config"]["frequency"]
        assert (
            command_frequency == updated_frequency
        ), f"Expected updated frequency {updated_frequency}, got {command_frequency}"

        # Verify other configuration remains the same
        assert (
            profiling_command["combined_config"]["duration"] == initial_request_data["duration"]
        ), "Duration should remain unchanged"
        assert (
            profiling_command["combined_config"]["profiling_mode"] == initial_request_data["profiling_mode"]
        ), "Profiling mode should remain unchanged"

        print(f"✅ Updated command received with frequency: {command_frequency}")
        print(f"🎯 Successfully verified frequency update: {initial_frequency} → {updated_frequency}")

        # Step 7: Verify database consistency
        print("🔍 Step 7: Verifying database consistency...")

        # Verify both requests exist in database
        db_initial_request = get_profiling_request_from_db(postgres_connection, initial_request_id)
        db_updated_request = get_profiling_request_from_db(postgres_connection, updated_request_id)

        assert db_initial_request is not None, "Initial request should exist in database"
        assert db_updated_request is not None, "Updated request should exist in database"

        # Verify frequencies in database
        assert db_initial_request["frequency"] == initial_frequency, "Initial request frequency mismatch in database"
        assert db_updated_request["frequency"] == updated_frequency, "Updated request frequency mismatch in database"

        # Verify the command in database has the updated frequency
        db_commands = get_profiling_commands_from_db(
            postgres_connection,
            test_service_name,
            test_hostname,
            command_ids=updated_command_ids,
        )

        assert len(db_commands) >= 1, "No updated commands found in database"

        # Find the command that matches our updated command
        matching_command = None
        for db_command in db_commands:
            if db_command["command_id"] == updated_command["command_id"]:
                matching_command = db_command
                break

        assert matching_command is not None, "Updated command not found in database"
        assert (
            matching_command["combined_config"]["frequency"] == updated_frequency
        ), "Command frequency mismatch in database"

        print("✅ Database consistency verified")

        # Step 8: Acknowledge the updated command
        print("🔄 Step 8: Acknowledging updated command...")
        final_ack_heartbeat = valid_heartbeat_data.copy()
        final_ack_heartbeat["last_command_id"] = updated_command["command_id"]

        final_ack_response = send_heartbeat_and_verify(
            heartbeat_url,
            final_ack_heartbeat,
            credentials,
            postgres_connection,
            expected_command_present=False,
        )

        assert final_ack_response is None, "Should not receive command after final acknowledgment"

        print(
            f"✅ End-to-end frequency update test passed: Initial frequency {initial_frequency} → Updated frequency {updated_frequency}, command properly updated and delivered"
        )
