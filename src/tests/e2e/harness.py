"""HTTP harness helpers for the in-network e2e acceptance suite.

The suite drives the *live* studio stack over HTTP (heartbeat ingress, profile
requests, workload status). It is designed to run from a container on the
compose network (E2E_BASE_URL=http://webapp, no auth) but also works from the
host against nginx (E2E_BASE_URL=https://localhost:4433 with basic auth).

Everything is keyed on unique service/host names per test, so runs are isolated
from each other and from any real agent reporting into the same stack.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEARTBEAT = "/api/metrics/heartbeat"
PROFILE_REQUEST = "/api/metrics/profile_request"
PROFILE_REQUEST_BULK = "/api/metrics/profile_request/bulk"
WORKLOAD_STATUS = "/api/metrics/profiling/workload_status"

# Freshness window used by workload_status (see db_manager: INTERVAL '2 minutes').
FRESHNESS_SECONDS = 120


class Client:
    """Thin requests wrapper that targets the studio API."""

    def __init__(self) -> None:
        self.base = os.environ.get("E2E_BASE_URL", "http://webapp").rstrip("/")
        user = os.environ.get("E2E_BASIC_AUTH_USER")
        password = os.environ.get("E2E_BASIC_AUTH_PASSWORD")
        self.auth = (user, password) if user else None
        self.session = requests.Session()

    def post(self, path: str, payload: Dict[str, Any]) -> requests.Response:
        return self.session.post(
            self.base + path, json=payload, auth=self.auth, verify=False, timeout=30
        )

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        return self.session.get(
            self.base + path, params=params, auth=self.auth, verify=False, timeout=30
        )


# --------------------------------------------------------------------------- #
# Payload builders
# --------------------------------------------------------------------------- #

def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def process(pid: int, name: str = "java") -> Dict[str, Any]:
    return {"pid": pid, "process_name": name}


def container(
    container_name: str,
    processes: Optional[List[Dict[str, Any]]] = None,
    *,
    namespace: Optional[str] = None,
    pod_name: Optional[str] = None,
    workload_name: Optional[str] = None,
    workload_kind: Optional[str] = None,
    container_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "container_id": container_id or unique("cid"),
        "container_name": container_name,
        "namespace": namespace,
        "pod_name": pod_name,
        "workload_name": workload_name,
        "workload_kind": workload_kind,
        "processes": processes or [],
    }


def heartbeat_payload(
    hostname: str,
    service_name: str,
    *,
    namespace: Optional[str] = None,
    pod_name: Optional[str] = None,
    containers: Optional[List[Dict[str, Any]]] = None,
    perf_supported_events: Optional[List[str]] = None,
    age_seconds: float = 0.0,
    agent_version: str = "e2e-1.0.0",
    run_mode: str = "container",
    status: str = "idle",
    last_command_id: Optional[str] = None,
) -> Dict[str, Any]:
    ts = datetime.now() - timedelta(seconds=age_seconds)
    return {
        "hostname": hostname,
        "ip_address": "10.0.0.1",
        "service_name": service_name,
        "agent_version": agent_version,
        "run_mode": run_mode,
        "namespace": namespace,
        "pod_name": pod_name,
        "containers": containers or [],
        "last_command_id": last_command_id,
        "status": status,
        "timestamp": ts.isoformat(),
        "perf_supported_events": perf_supported_events,
    }


# --------------------------------------------------------------------------- #
# API calls
# --------------------------------------------------------------------------- #

def send_heartbeat(client: Client, **kwargs: Any) -> Dict[str, Any]:
    resp = client.post(HEARTBEAT, heartbeat_payload(**kwargs))
    resp.raise_for_status()
    return resp.json()


def get_workload_status(
    client: Client,
    scope: str = "host",
    service_name: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"scope": scope}
    if service_name:
        params["service_name"] = service_name
        params["exact_match"] = "true"
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["page_size"] = page_size
    if sort_by is not None:
        params["sort_by"] = sort_by
    if sort_order is not None:
        params["sort_order"] = sort_order
    resp = client.get(WORKLOAD_STATUS, params=params)
    resp.raise_for_status()
    return resp.json()


def rows_for(status: Dict[str, Any], service_name: str) -> List[Dict[str, Any]]:
    """Rows belonging to our service (robust even if server-side filter is loose)."""
    return [r for r in status.get("rows", []) if r.get("serviceName") == service_name]


def _default_entities(service_name, target_scope, target_hosts, target_entities):
    """The request validator requires at least one target_hosts entry or
    target_entities selector. For non-host scopes with nothing else provided,
    mirror the UI by attaching a service selector (resolution uses the request's
    service_name; the entity just satisfies the contract)."""
    if target_entities:
        return target_entities
    if target_scope != "host" and not target_hosts:
        return [{"service_name": service_name}]
    return target_entities


def start_request(
    service_name: str,
    *,
    target_scope: str = "host",
    target_hosts: Optional[Dict[str, List[int]]] = None,
    target_entities: Optional[List[Dict[str, Any]]] = None,
    continuous: bool = False,
    duration: int = 30,
    frequency: int = 11,
    additional_args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    target_entities = _default_entities(service_name, target_scope, target_hosts, target_entities)
    return {
        "service_name": service_name,
        "request_type": "start",
        "continuous": continuous,
        "duration": duration,
        "frequency": frequency,
        "profiling_mode": "cpu",
        "target_scope": target_scope,
        "target_hosts": target_hosts,
        "target_entities": target_entities,
        "additional_args": additional_args or {},
    }


def stop_request(
    service_name: str,
    *,
    target_scope: str = "host",
    stop_level: str = "host",
    target_hosts: Optional[Dict[str, List[int]]] = None,
    target_entities: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    target_entities = _default_entities(service_name, target_scope, target_hosts, target_entities)
    return {
        "service_name": service_name,
        "request_type": "stop",
        "continuous": False,
        "duration": 30,
        "frequency": 11,
        "profiling_mode": "cpu",
        "target_scope": target_scope,
        "stop_level": stop_level,
        "target_hosts": target_hosts,
        "target_entities": target_entities,
        "additional_args": {},
    }


def submit(client: Client, payload: Dict[str, Any]) -> requests.Response:
    return client.post(PROFILE_REQUEST, payload)


def submit_bulk(client: Client, requests_list: List[Dict[str, Any]]) -> requests.Response:
    return client.post(PROFILE_REQUEST_BULK, {"requests": requests_list})
