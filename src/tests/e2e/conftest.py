"""Fixtures for the in-network e2e acceptance suite.

Runs from a container on the compose network (see docker-compose.e2e.yml) so
services are reachable by their compose names (webapp, db_postgres, ...). Also
works from the host against nginx with basic auth via E2E_* env vars.
"""
import pytest

from harness import Client


@pytest.fixture(scope="session")
def client() -> Client:
    return Client()
