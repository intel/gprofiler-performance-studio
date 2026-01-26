import argparse
import os
import sys

import pytest

TEST_BACKEND = os.getenv("TEST_BACKEND", "True")
TEST_DB = os.getenv("TEST_DB", "True")

TEST_MANAGED_BACKEND = os.getenv("TEST_MANAGED_BACKEND", "True")
TEST_MANAGED_DB = os.getenv("TEST_MANAGED_DB", "True")

BACKEND_URL = os.getenv("BACKEND_URL", "https://localhost")
BACKEND_PORT = os.getenv("BACKEND_PORT", 4433)
BACKEND_USER = os.getenv("BACKEND_USER", "test-user")
BACKEND_PASSWORD = os.getenv("BACKEND_PASSWORD", "tester123")

POSTGRES_USER = os.getenv("POSTGRES_USER", "performance_studio")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "performance_studio_password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "performance_studio")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", 5432)
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")

"""
This script is used to run tests with configurable parameters.
The test options can be set at the command line or through environment variables.
The fallback strategy for the configuration is:
1. Command line arguments
2. Environment variables
3. Default values defined in the script
"""


def parse_arguments():
    """Parse command line arguments for test configuration."""
    parser = argparse.ArgumentParser(
        description="Run tests with configurable parameters",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Test flags
    parser.add_argument(
        "--test-backend",
        default=TEST_BACKEND,
        type=bool,
        help="Enable or disable backend tests",
    )

    parser.add_argument("--test-db", default=TEST_DB, type=bool, help="Enable or disable database tests")

    parser.add_argument(
        "--test-managed-backend",
        default=TEST_MANAGED_BACKEND,
        type=bool,
        help="Enable or disable managed backend tests",
    )

    parser.add_argument(
        "--test-managed-db",
        default=TEST_MANAGED_DB,
        type=bool,
        help="Enable or disable managed database tests",
    )

    # Backend configuration
    parser.add_argument("--backend-url", default=BACKEND_URL, help="Backend URL for testing")

    parser.add_argument(
        "--backend-port",
        type=int,
        default=BACKEND_PORT,
        help="Backend port for testing",
    )

    parser.add_argument(
        "--backend-user",
        default=BACKEND_USER,
        help="Backend username for authentication",
    )

    parser.add_argument(
        "--backend-password",
        default=BACKEND_PASSWORD,
        help="Backend password for authentication",
    )

    # PostgreSQL configuration
    parser.add_argument("--postgres-user", default=POSTGRES_USER, help="PostgreSQL username")

    parser.add_argument("--postgres-password", default=POSTGRES_PASSWORD, help="PostgreSQL password")

    parser.add_argument("--postgres-db", default=POSTGRES_DB, help="PostgreSQL database name")

    parser.add_argument("--postgres-port", type=int, default=POSTGRES_PORT, help="PostgreSQL port")

    parser.add_argument("--postgres-host", default=POSTGRES_HOST, help="PostgreSQL host")

    # Pytest configuration
    parser.add_argument("--test-path", default=".", help="Path to test files or directories")

    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Increase verbosity (can be used multiple times: -v, -vv, -vvv)",
    )

    parser.add_argument(
        "--capture",
        choices=["yes", "no", "all", "sys"],
        default="no",
        help="Capture output during test execution",
    )

    parser.add_argument("--markers", "-m", help="Run tests matching given mark expression")

    parser.add_argument("--keyword", "-k", help="Run tests matching given substring expression")

    parser.add_argument("--maxfail", type=int, help="Stop after first num failures or errors")

    parser.add_argument(
        "--tb",
        choices=["auto", "long", "short", "line", "native", "no"],
        default="short",
        help="Traceback print mode",
    )

    parser.add_argument("--junit-xml", help="Create junit-xml style report file at given path")

    parser.add_argument("--html", help="Create html report file at given path (requires pytest-html)")

    parser.add_argument("--extra-args", nargs="*", help="Additional arguments to pass to pytest")

    return parser.parse_args()


def build_pytest_args(args):
    """Build pytest arguments from parsed command line arguments."""
    pytest_args = []

    # Add test path
    if args.test_path:
        pytest_args.append(args.test_path)

    # Add verbosity
    if args.verbose > 0:
        pytest_args.append("-" + "v" * min(args.verbose, 3))

    # Add capture mode
    if args.capture == "no":
        pytest_args.append("-s")
    else:
        pytest_args.extend(["--capture", args.capture])

    # Add markers
    if args.markers:
        pytest_args.extend(["-m", args.markers])

    # Add keyword filtering
    if args.keyword:
        pytest_args.extend(["-k", args.keyword])

    # Add max failures
    if args.maxfail is not None:
        pytest_args.extend(["--maxfail", str(args.maxfail)])

    # Add traceback mode
    if args.tb:
        pytest_args.extend(["--tb", args.tb])

    # Add junit xml report
    if args.junit_xml:
        pytest_args.extend(["--junit-xml", args.junit_xml])

    # Add html report
    if args.html:
        pytest_args.extend(["--html", args.html])

    # Add any extra arguments
    if args.extra_args:
        pytest_args.extend(args.extra_args)

    # Add custom environment variables as pytest options
    pytest_args.extend(
        [
            f"--backend-url={args.backend_url}",
            f"--backend-port={args.backend_port}",
            f"--backend-user={args.backend_user}",
            f"--backend-password={args.backend_password}",
            f"--postgres-user={args.postgres_user}",
            f"--postgres-password={args.postgres_password}",
            f"--postgres-db={args.postgres_db}",
            f"--postgres-port={args.postgres_port}",
            f"--postgres-host={args.postgres_host}",
            f"--test-backend={args.test_backend}",
            f"--test-db={args.test_db}",
            f"--test-managed-backend={args.test_managed_backend}",
            f"--test-managed-db={args.test_managed_db}",
        ]
    )

    return pytest_args


def main():
    """Main function to run tests with parsed arguments."""
    args = parse_arguments()

    print("🧪 Running tests with configuration:")
    print("=" * 50)

    # Build pytest arguments
    pytest_args = build_pytest_args(args)

    print(f"\n📋 Pytest command: pytest {' '.join(pytest_args)}")
    print("=" * 50)

    # Run pytest
    exit_code = pytest.main(pytest_args)

    # Exit with the same code as pytest
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
