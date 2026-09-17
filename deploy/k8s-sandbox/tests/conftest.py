"""Fixtures for the k8s-sandbox acceptance suite.

Reuses the HTTP harness from the compose e2e suite (copied in at image build
time) so the request/response contract stays in one place. Runs in-cluster as a
Job in the perf-studio namespace, reaching the backend at http://webapp.
"""
import pytest

from harness import Client


@pytest.fixture(scope="session")
def client() -> Client:
    return Client()
