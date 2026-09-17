"""Real-cluster acceptance tests (AT-K1 .. AT-K5).

Unlike the compose e2e suite (which POSTs *synthetic* heartbeats to fabricate an
inventory), these assert against inventory produced by a REAL gProfiler agent
DaemonSet enumerating the node's CRI socket. That is the capability docker-compose
cannot provide (no container runtime -> empty inventory), so this is the layer
that actually proves namespace/pod/container/process discovery and scope
resolution under Kubernetes.

Prerequisite: the sandbox is up with the SOURCE-built agent and the tenant
workloads deployed (see deploy/k8s-sandbox/Makefile.k8s):

    make -f Makefile.k8s k8s-up
    make -f Makefile.k8s k8s-test

The agent reports under service_name "k8s-sandbox". Because it enumerates the
whole node, inventory also contains system/studio containers; every assertion
therefore looks for the specific tenant entities we deployed rather than exact
totals, which keeps the suite robust on any cluster.
"""
import json
import time

import harness as h
import pytest

AGENT_SERVICE = "k8s-sandbox"

# What deploy/k8s-sandbox/manifests/40-workloads.yaml creates.
EXPECTED_NAMESPACES = ["team-a", "team-b"]
EXPECTED_PODS = ["checkout", "web", "payments", "search"]
EXPECTED_CONTAINERS = ["checkout", "web", "payments", "search-app", "search-sidecar"]

# The agent inventory refresh is 30s and heartbeats every 10s; give the first
# full snapshot generous time to propagate on a cold cluster.
DISCOVERY_TIMEOUT_S = 240
POLL_INTERVAL_S = 5


def _status_blob(client, scope):
    """workload_status for a scope, as (parsed, serialized) for tolerant matching.

    Per-scope row field names are intentionally not hard-coded; we match on the
    serialized document so the test doesn't break if the response key casing
    changes. tabCounts and host rows use the same stable contract as the compose
    suite.
    """
    status = h.get_workload_status(client, scope=scope)
    return status, json.dumps(status)


def _wait_for(client, scope, needles):
    """Poll workload_status[scope] until every needle appears, or time out."""
    deadline = time.time() + DISCOVERY_TIMEOUT_S
    missing = list(needles)
    blob = ""
    while time.time() < deadline:
        _, blob = _status_blob(client, scope)
        missing = [n for n in needles if n not in blob]
        if not missing:
            return blob
        time.sleep(POLL_INTERVAL_S)
    pytest.fail(
        f"scope={scope}: timed out after {DISCOVERY_TIMEOUT_S}s waiting for "
        f"{missing}. Is the SOURCE-built agent DaemonSet running with hostPID + "
        f"privileged and a reachable containerd socket? Last blob: {blob[:2000]}"
    )


def test_at_k1_agent_registers_as_host(client):
    """AT-K1: the real agent DaemonSet shows up as a host under its service."""
    deadline = time.time() + DISCOVERY_TIMEOUT_S
    hosts = []
    while time.time() < deadline:
        status = h.get_workload_status(client, scope="host", service_name=AGENT_SERVICE)
        hosts = [r["hostname"] for r in h.rows_for(status, AGENT_SERVICE)]
        if hosts:
            break
        time.sleep(POLL_INTERVAL_S)
    assert hosts, f"no host reported for service {AGENT_SERVICE!r} within {DISCOVERY_TIMEOUT_S}s"


def test_at_k2_namespaces_from_real_cri(client):
    """AT-K2: tenant namespaces are discovered from the node's CRI, not fabricated."""
    blob = _wait_for(client, "namespace", EXPECTED_NAMESPACES)
    for ns in EXPECTED_NAMESPACES:
        assert ns in blob


def test_at_k3_pods_from_real_cri(client):
    """AT-K3: pods for each tenant workload appear in the pod scope."""
    # Deployment pods are named <workload>-<replicaset>-<suffix>; the agent
    # derives the workload name, so matching the workload prefix is sufficient.
    blob = _wait_for(client, "pod", EXPECTED_PODS)
    for pod in EXPECTED_PODS:
        assert pod in blob


def test_at_k4_containers_including_multi_container_pod(client):
    """AT-K4: every container is discovered, including both in the 2-container pod."""
    blob = _wait_for(client, "container", EXPECTED_CONTAINERS)
    for container in EXPECTED_CONTAINERS:
        assert container in blob, f"missing container {container!r}"


def test_at_k5_host_scope_start_resolves_real_agent(client):
    """AT-K5: a host-scope start resolves the real agent's host and creates a command.

    Uses the same start/stop contract the compose suite validates (AT-S5), but the
    target host is the *real* DaemonSet host discovered from live inventory, so
    this proves the studio resolves and dispatches to an actual agent (not a
    synthetic heartbeat).
    """
    status = h.get_workload_status(client, scope="host", service_name=AGENT_SERVICE)
    hosts = [r["hostname"] for r in h.rows_for(status, AGENT_SERVICE)]
    assert hosts, "no real agent host to target"
    host = hosts[0]

    started = h.submit(
        client,
        h.start_request(AGENT_SERVICE, target_scope="host", target_hosts={host: []}),
    )
    assert started.status_code == 200, started.text

    stopped = h.submit(
        client,
        h.stop_request(AGENT_SERVICE, target_scope="host", stop_level="host", target_hosts={host: []}),
    )
    assert stopped.status_code == 200, stopped.text
