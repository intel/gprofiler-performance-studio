#!/usr/bin/env python3
"""
Integration tests for the normalized heartbeat workload inventory sync.

These validate the diff/upsert behavior of ``DBManager._sync_host_inventory`` end
to end: a heartbeat is POSTed to the live backend and the resulting rows in
``HeartbeatContainers`` / ``HeartbeatProcesses`` are inspected directly in
PostgreSQL.

The central regression this guards is write amplification at fleet scale: an
unchanged inventory must NOT rewrite rows on every heartbeat. We prove that by
asserting both the primary key ``id`` and the physical row version ``ctid`` are
unchanged across identical beats (a delete-then-insert or an unconditional
``DO UPDATE`` would change both), while a real change to a single process rewrites
only that row and leaves its siblings physically untouched.

Run just this file (needs the live stack + Postgres, see deploy/Makefile.e2e):

    cd src && python -m pytest tests/integration/backend_db/test_heartbeat_inventory_sync.py -v
"""

import uuid
from typing import Any, Dict, List

import psycopg2
import psycopg2.extras
import pytest
import requests


@pytest.fixture(scope="session")
def postgres_connection(pytestconfig):
    """Create a PostgreSQL connection for direct row inspection."""
    conn = psycopg2.connect(
        host=pytestconfig.getoption("--postgres-host", default="localhost"),
        port=pytestconfig.getoption("--postgres-port", default=5432),
        user=pytestconfig.getoption("--postgres-user", default="performance_studio"),
        password=pytestconfig.getoption("--postgres-password", default="performance_studio_password"),
        database=pytestconfig.getoption("--postgres-db", default="performance_studio_db"),
    )
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def heartbeat_url(backend_base_url) -> str:
    return f"{backend_base_url}/api/metrics/heartbeat"


def _container(container_id: str, name: str, processes: List[Dict[str, Any]], **overrides: Any) -> Dict[str, Any]:
    payload = {
        "container_id": container_id,
        "container_name": name,
        "runtime": "containerd",
        "namespace": "obs",
        "pod_name": "pod-a",
        "workload_name": "checkout",
        "workload_kind": "k8s",
        "processes": processes,
    }
    payload.update(overrides)
    return payload


def _send(heartbeat_url: str, credentials: Dict[str, str], hostname: str, service: str,
          containers: List[Dict[str, Any]]) -> None:
    body = {
        "ip_address": "127.0.0.1",
        "hostname": hostname,
        "service_name": service,
        "status": "active",
        "containers": containers,
    }
    response = requests.post(heartbeat_url, headers=credentials, json=body, timeout=10, verify=False)
    assert response.status_code == 200, f"Heartbeat failed: {response.status_code}: {response.text}"


def _containers(conn, hostname: str, service: str) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT hc.id, hc.ctid::text AS ctid, hc.container_id, hc.container_name
            FROM HeartbeatContainers hc
            JOIN HostHeartbeats h ON h.id = hc.host_id
            WHERE h.hostname = %s AND h.service_name = %s
            ORDER BY hc.container_id
            """,
            (hostname, service),
        )
        return [dict(row) for row in cursor.fetchall()]


def _processes(conn, hostname: str, service: str) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT hp.id, hp.ctid::text AS ctid, hp.pid, hp.process_name, hc.container_id
            FROM HeartbeatProcesses hp
            JOIN HeartbeatContainers hc ON hc.id = hp.container_row_id
            JOIN HostHeartbeats h ON h.id = hc.host_id
            WHERE h.hostname = %s AND h.service_name = %s
            ORDER BY hc.container_id, hp.pid
            """,
            (hostname, service),
        )
        return [dict(row) for row in cursor.fetchall()]


def _cleanup(conn, hostname: str) -> None:
    with conn.cursor() as cursor:
        # HeartbeatContainers/Processes cascade from HostHeartbeats.
        cursor.execute("DELETE FROM HostHeartbeats WHERE hostname = %s", (hostname,))


@pytest.fixture
def host_service(postgres_connection):
    hostname = f"inv-host-{uuid.uuid4().hex[:8]}"
    service = f"inv-svc-{uuid.uuid4().hex[:8]}"
    _cleanup(postgres_connection, hostname)
    yield hostname, service
    _cleanup(postgres_connection, hostname)


def test_non_containerized_host_stores_no_rows(heartbeat_url, credentials, postgres_connection, host_service):
    """A host with no containerized workload (empty list) stores zero inventory rows."""
    hostname, service = host_service
    _send(heartbeat_url, credentials, hostname, service, containers=[])

    assert _containers(postgres_connection, hostname, service) == []
    assert _processes(postgres_connection, hostname, service) == []


def test_stable_inventory_is_not_rewritten(heartbeat_url, credentials, postgres_connection, host_service):
    """Repeated identical heartbeats must not rewrite rows (stable id AND ctid)."""
    hostname, service = host_service
    containers = [
        _container("cid-a", "app", [{"pid": 11, "process_name": "java"}, {"pid": 22, "process_name": "python"}]),
        _container("cid-b", "sidecar", [{"pid": 33, "process_name": "envoy"}]),
    ]

    _send(heartbeat_url, credentials, hostname, service, containers)
    containers_first = _containers(postgres_connection, hostname, service)
    processes_first = _processes(postgres_connection, hostname, service)
    assert [c["container_id"] for c in containers_first] == ["cid-a", "cid-b"]
    assert [(p["container_id"], p["pid"]) for p in processes_first] == [
        ("cid-a", 11), ("cid-a", 22), ("cid-b", 33),
    ]

    # Second identical beat: nothing should be physically rewritten.
    _send(heartbeat_url, credentials, hostname, service, containers)
    containers_second = _containers(postgres_connection, hostname, service)
    processes_second = _processes(postgres_connection, hostname, service)

    assert {(c["id"], c["ctid"]) for c in containers_second} == {(c["id"], c["ctid"]) for c in containers_first}
    assert {(p["id"], p["ctid"]) for p in processes_second} == {(p["id"], p["ctid"]) for p in processes_first}


def test_process_change_is_isolated(heartbeat_url, credentials, postgres_connection, host_service):
    """Changing one process rewrites only that row; unchanged siblings keep their ctid."""
    hostname, service = host_service
    containers = [
        _container("cid-a", "app", [{"pid": 11, "process_name": "java"}, {"pid": 22, "process_name": "python"}]),
    ]
    _send(heartbeat_url, credentials, hostname, service, containers)
    before = {(p["pid"]): p for p in _processes(postgres_connection, hostname, service)}

    # Rename only pid 22.
    containers[0]["processes"] = [
        {"pid": 11, "process_name": "java"},
        {"pid": 22, "process_name": "python3"},
    ]
    _send(heartbeat_url, credentials, hostname, service, containers)
    after = {(p["pid"]): p for p in _processes(postgres_connection, hostname, service)}

    # Unchanged sibling: same physical row.
    assert after[11]["ctid"] == before[11]["ctid"]
    # Changed row: same logical row (id) but rewritten (new ctid) and new name.
    assert after[22]["id"] == before[22]["id"]
    assert after[22]["ctid"] != before[22]["ctid"]
    assert after[22]["process_name"] == "python3"


def test_removed_container_is_pruned(heartbeat_url, credentials, postgres_connection, host_service):
    """A container that stops being reported is deleted along with its processes."""
    hostname, service = host_service
    _send(
        heartbeat_url, credentials, hostname, service,
        containers=[
            _container("cid-a", "app", [{"pid": 11, "process_name": "java"}]),
            _container("cid-b", "sidecar", [{"pid": 33, "process_name": "envoy"}]),
        ],
    )
    assert {c["container_id"] for c in _containers(postgres_connection, hostname, service)} == {"cid-a", "cid-b"}

    # Drop cid-b.
    _send(
        heartbeat_url, credentials, hostname, service,
        containers=[_container("cid-a", "app", [{"pid": 11, "process_name": "java"}])],
    )
    assert {c["container_id"] for c in _containers(postgres_connection, hostname, service)} == {"cid-a"}
    assert {p["pid"] for p in _processes(postgres_connection, hostname, service)} == {11}


def test_null_container_id_is_skipped(heartbeat_url, credentials, postgres_connection, host_service):
    """Entries without a container_id are not stored (containerized-only model)."""
    hostname, service = host_service
    _send(
        heartbeat_url, credentials, hostname, service,
        containers=[
            _container("cid-a", "app", [{"pid": 11, "process_name": "java"}]),
            _container(None, "bare", [{"pid": 99, "process_name": "systemd"}]),
        ],
    )

    stored = _containers(postgres_connection, hostname, service)
    assert [c["container_id"] for c in stored] == ["cid-a"]
    assert {p["pid"] for p in _processes(postgres_connection, hostname, service)} == {11}
