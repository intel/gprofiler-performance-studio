import base64

import pytest


def pytest_addoption(parser):
    """Add custom command line options for pytest."""

    # Test flags
    parser.addoption(
        "--test-backend",
        action="store",
        default="True",
        help="Enable or disable backend tests",
    )

    parser.addoption(
        "--test-db",
        action="store",
        default="True",
        help="Enable or disable database tests",
    )

    parser.addoption(
        "--test-managed-backend",
        action="store",
        default="True",
        help="Enable or disable managed backend tests",
    )

    parser.addoption(
        "--test-managed-db",
        action="store",
        default="True",
        help="Enable or disable managed database tests",
    )

    # Backend configuration
    parser.addoption(
        "--backend-url",
        action="store",
        default="http://localhost",
        help="Backend URL for testing",
    )

    parser.addoption(
        "--backend-port",
        action="store",
        type=int,
        default=8080,
        help="Backend port for testing",
    )

    parser.addoption(
        "--backend-user",
        action="store",
        default="test-user",
        help="Backend username for authentication",
    )

    parser.addoption(
        "--backend-password",
        action="store",
        default="tester123",
        help="Backend password for authentication",
    )

    # PostgreSQL configuration
    parser.addoption(
        "--postgres-user",
        action="store",
        default="performance_studio",
        help="PostgreSQL username",
    )

    parser.addoption(
        "--postgres-password",
        action="store",
        default="performance_studio_password",
        help="PostgreSQL password",
    )

    parser.addoption(
        "--postgres-db",
        action="store",
        default="performance_studio_db",
        help="PostgreSQL database name",
    )

    parser.addoption(
        "--postgres-port",
        action="store",
        type=int,
        default=5432,
        help="PostgreSQL port",
    )

    parser.addoption("--postgres-host", action="store", default="localhost", help="PostgreSQL host")


@pytest.fixture(scope="session")
def backend_base_url(pytestconfig) -> str:
    """Get backend base URL from pytest config."""
    backend_url = pytestconfig.getoption("--backend-url", default="http://localhost")
    backend_port = pytestconfig.getoption("--backend-port", default=5000)
    return f"{backend_url}:{backend_port}"


@pytest.fixture(scope="session")
def credentials(pytestconfig) -> dict[str, str]:
    """Get credentials from pytest config."""
    username = pytestconfig.getoption("--backend-user", default="test-user")
    password = pytestconfig.getoption("--backend-password", default="tester123")
    basic_auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {basic_auth}"}
