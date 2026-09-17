"""End-to-end acceptance tests for workload-level profiling (AT-S1 .. AT-S15).

These drive the *live* studio stack over HTTP and codify the acceptance criteria
from `heartbeat_doc/WORKLOAD_LEVEL_PROFILING_SPEC.md`. Each test uses a unique
service/host name so runs are isolated from each other and from any real agent.

Bring the stack up first (see deploy/Makefile.e2e), then:

    make -f Makefile.e2e e2e-test          # in-network
    # or from host:
    E2E_BASE_URL=https://localhost:4433 E2E_BASIC_AUTH_USER=admin \
      E2E_BASIC_AUTH_PASSWORD=admin pytest -q src/tests/e2e
"""
import json

import harness as h
import pytest


# --------------------------------------------------------------------------- #
# Inventory & status views (AT-S1 .. AT-S4)
# --------------------------------------------------------------------------- #

def test_at_s1_heartbeat_populates_inventory(client):
    """AT-S1: a fresh heartbeat shows up as a host row in workload_status."""
    service = h.unique("s1")
    host = h.unique("host")
    h.send_heartbeat(
        client,
        hostname=host,
        service_name=service,
        namespace="obs",
        pod_name="pod-a",
        containers=[h.container("app", [h.process(1234)], namespace="obs", pod_name="pod-a")],
    )

    status = h.get_workload_status(client, scope="host", service_name=service)
    hosts = {r["hostname"] for r in h.rows_for(status, service)}
    assert host in hosts


def test_at_s2_tab_counts_per_scope(client):
    """AT-S2: tabCounts reflect distinct groups per scope; activeHosts == hosts."""
    service = h.unique("s2")
    host = h.unique("host")
    h.send_heartbeat(
        client,
        hostname=host,
        service_name=service,
        namespace="team-a",
        pod_name="pod-1",
        containers=[
            h.container(
                "checkout",
                [h.process(11, "java"), h.process(22, "python")],
                namespace="team-a",
                pod_name="pod-1",
                workload_name="checkout",
                workload_kind="deployment",
            )
        ],
    )

    status = h.get_workload_status(client, scope="host", service_name=service)
    tabs = status["tabCounts"]
    assert tabs["service"] == 1
    assert tabs["host"] == 1
    assert tabs["namespace"] == 1
    assert tabs["pod"] == 1
    assert tabs["container"] == 1
    assert tabs["process"] == 2
    assert status["activeHosts"] == 1


def test_at_s3_service_tab_grouped_by_service(client):
    """AT-S3: scope=service returns exactly one aggregated row per service."""
    service = h.unique("s3")
    for host in (h.unique("host"), h.unique("host")):
        h.send_heartbeat(
            client,
            hostname=host,
            service_name=service,
            containers=[h.container("app", [h.process(1)])],
        )

    status = h.get_workload_status(client, scope="service", service_name=service)
    rows = h.rows_for(status, service)
    assert len(rows) == 1
    assert rows[0]["hostCount"] == 2


def test_at_s4_freshness_filtering(client):
    """AT-S4: a host whose latest heartbeat is stale is excluded from all tabs."""
    service = h.unique("s4")
    host = h.unique("host")
    # Backdate the heartbeat well beyond the 2-minute freshness window.
    h.send_heartbeat(
        client,
        hostname=host,
        service_name=service,
        age_seconds=h.FRESHNESS_SECONDS + 180,
        containers=[h.container("app", [h.process(1)])],
    )

    status = h.get_workload_status(client, scope="host", service_name=service)
    hosts = {r["hostname"] for r in h.rows_for(status, service)}
    assert host not in hosts


# --------------------------------------------------------------------------- #
# Resolution & command creation (AT-S5 .. AT-S9)
# --------------------------------------------------------------------------- #

def test_at_s5_host_level_start(client):
    """AT-S5: a host-scope start yields a start command returned to that host."""
    service = h.unique("s5")
    host = h.unique("host")
    h.send_heartbeat(client, hostname=host, service_name=service)

    resp = h.submit(client, h.start_request(service, target_scope="host", target_hosts={host: []}))
    assert resp.status_code == 200, resp.text

    beat = h.send_heartbeat(client, hostname=host, service_name=service)
    assert beat["profiling_command"] is not None
    assert beat["profiling_command"]["command_type"] == "start"


def test_at_s6_service_level_start_fans_out(client):
    """AT-S6: a service-scope start creates a command for every current host."""
    service = h.unique("s6")
    h1, h2 = h.unique("host"), h.unique("host")
    h.send_heartbeat(client, hostname=h1, service_name=service)
    h.send_heartbeat(client, hostname=h2, service_name=service)

    resp = h.submit(client, h.start_request(service, target_scope="service"))
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["command_ids"]) == 2

    for host in (h1, h2):
        beat = h.send_heartbeat(client, hostname=host, service_name=service)
        assert beat["profiling_command"] is not None, f"no command for {host}"
        assert beat["profiling_command"]["command_type"] == "start"


def test_at_s7_process_scope_resolves_to_pids(client):
    """AT-S7: a process selection resolves to hostname->[pid] and the command carries the PID."""
    service = h.unique("s7")
    host = h.unique("host")
    pid = 4242
    h.send_heartbeat(
        client,
        hostname=host,
        service_name=service,
        containers=[h.container("app", [h.process(pid, "java")])],
    )

    resp = h.submit(
        client,
        h.start_request(
            service,
            target_scope="process",
            target_entities=[{"service_name": service, "hostname": host, "pid": pid}],
        ),
    )
    assert resp.status_code == 200, resp.text

    beat = h.send_heartbeat(client, hostname=host, service_name=service)
    assert beat["profiling_command"] is not None
    assert str(pid) in json.dumps(beat["profiling_command"]["combined_config"])


def test_at_s8_empty_resolution_is_rejected(client):
    """AT-S8: a selection resolving to zero targets returns 422 and creates no command."""
    service = h.unique("s8")
    host = h.unique("host")
    h.send_heartbeat(
        client,
        hostname=host,
        service_name=service,
        containers=[h.container("app", [h.process(1234)])],
    )

    resp = h.submit(
        client,
        h.start_request(
            service,
            target_scope="process",
            target_entities=[{"service_name": service, "hostname": host, "pid": 999999}],
        ),
    )
    assert resp.status_code == 422, resp.text

    beat = h.send_heartbeat(client, hostname=host, service_name=service)
    assert beat["profiling_command"] is None


def test_at_s9_pmu_validation_rejects_unsupported_events(client):
    """AT-S9: a start requesting perf events a host doesn't support is rejected (bulk)."""
    service = h.unique("s9")
    host = h.unique("host")
    h.send_heartbeat(
        client,
        hostname=host,
        service_name=service,
        perf_supported_events=["cycles"],
    )

    req = h.start_request(
        service,
        target_scope="host",
        target_hosts={host: []},
        additional_args={"profiler_configs": {"perf": {"mode": "smart", "events": ["instructions"]}}},
    )
    resp = h.submit_bulk(client, [req])
    assert resp.status_code == 422, resp.text
    assert "perf" in resp.text.lower() or "event" in resp.text.lower()


# --------------------------------------------------------------------------- #
# Continuous service subscriptions & auto-enrollment (AT-S10 .. AT-S13)
# --------------------------------------------------------------------------- #

def _subscribe_service(client, service, seed_host):
    """Create an active service-wide continuous subscription."""
    h.send_heartbeat(client, hostname=seed_host, service_name=service)
    resp = h.submit(
        client, h.start_request(service, target_scope="service", continuous=True)
    )
    assert resp.status_code == 200, resp.text


def test_at_s10_new_host_auto_enrolls(client):
    """AT-S10: a new host under an active subscription gets a start on its first heartbeat."""
    service = h.unique("s10")
    seed, newcomer = h.unique("host"), h.unique("host")
    _subscribe_service(client, service, seed)

    beat = h.send_heartbeat(client, hostname=newcomer, service_name=service)
    assert beat["profiling_command"] is not None
    assert beat["profiling_command"]["command_type"] == "start"


def test_at_s11_no_subscription_no_enrollment(client):
    """AT-S11: with no active subscription, a new host gets no command."""
    service = h.unique("s11")
    host = h.unique("host")
    beat = h.send_heartbeat(client, hostname=host, service_name=service)
    assert beat["profiling_command"] is None


def test_at_s12_stop_deactivates_subscription(client):
    """AT-S12: after a service-wide stop, a new host is not enrolled."""
    service = h.unique("s12")
    seed, newcomer = h.unique("host"), h.unique("host")
    _subscribe_service(client, service, seed)

    resp = h.submit(
        client, h.stop_request(service, target_scope="service", stop_level="host")
    )
    assert resp.status_code == 200, resp.text

    beat = h.send_heartbeat(client, hostname=newcomer, service_name=service)
    assert beat["profiling_command"] is None or beat["profiling_command"]["command_type"] != "start"


def test_at_s13_existing_command_preserved(client):
    """AT-S13: auto-enroll does not overwrite a host's existing command."""
    service = h.unique("s13")
    seed = h.unique("host")
    _subscribe_service(client, service, seed)

    first = h.send_heartbeat(client, hostname=seed, service_name=service)
    assert first["profiling_command"] is not None
    command_id = first["command_id"]

    # Subsequent heartbeats under the active subscription must not replace it.
    second = h.send_heartbeat(client, hostname=seed, service_name=service)
    assert second["command_id"] == command_id


# --------------------------------------------------------------------------- #
# Compatibility & failure handling (AT-S14 .. AT-S15)
# --------------------------------------------------------------------------- #

def test_at_s14_legacy_heartbeat(client):
    """AT-S14: a heartbeat with no workload fields still yields host status + host commands."""
    service = h.unique("s14")
    host = h.unique("host")
    # No namespace/pod/containers at all.
    h.send_heartbeat(client, hostname=host, service_name=service)

    status = h.get_workload_status(client, scope="host", service_name=service)
    rows = h.rows_for(status, service)
    assert host in {r["hostname"] for r in rows}
    assert status["tabCounts"]["namespace"] == 0
    assert status["tabCounts"]["pod"] == 0
    assert status["tabCounts"]["container"] == 0

    # Host-level command path still works.
    resp = h.submit(client, h.start_request(service, target_scope="host", target_hosts={host: []}))
    assert resp.status_code == 200, resp.text
    beat = h.send_heartbeat(client, hostname=host, service_name=service)
    assert beat["profiling_command"] is not None


def test_at_s15_partial_inventory(client):
    """AT-S15: heartbeats missing some fields (no pod_name) don't break other scopes."""
    service = h.unique("s15")
    host = h.unique("host")
    # Container has a namespace + processes but no pod_name.
    h.send_heartbeat(
        client,
        hostname=host,
        service_name=service,
        namespace="team-x",
        containers=[h.container("app", [h.process(7)], namespace="team-x")],
    )

    status = h.get_workload_status(client, scope="host", service_name=service)
    tabs = status["tabCounts"]
    assert host in {r["hostname"] for r in h.rows_for(status, service)}
    assert tabs["namespace"] == 1
    assert tabs["container"] == 1
    assert tabs["process"] == 1
    # No invented pod relationships.
    assert tabs["pod"] == 0


# --------------------------------------------------------------------------- #
# Pagination & server-side sorting (AT-S16 .. AT-S17)
# --------------------------------------------------------------------------- #

def test_at_s16_host_scope_pagination(client):
    """AT-S16: host scope is paginated; pages are disjoint and total_count is the full match."""
    service = h.unique("s16")
    hosts = sorted(h.unique("host") for _ in range(5))
    for host in hosts:
        h.send_heartbeat(
            client,
            hostname=host,
            service_name=service,
            containers=[h.container("app", [h.process(1234)])],
        )

    first = h.get_workload_status(
        client, scope="host", service_name=service, page=0, page_size=2, sort_by="hostname", sort_order="asc"
    )
    assert first["totalCount"] == 5
    assert len(h.rows_for(first, service)) == 2

    seen = []
    for page in range(3):
        status = h.get_workload_status(
            client, scope="host", service_name=service, page=page, page_size=2, sort_by="hostname", sort_order="asc"
        )
        seen.extend(r["hostname"] for r in h.rows_for(status, service))

    # All five hosts appear exactly once across the three pages (no overlap, no drops).
    assert sorted(seen) == hosts


def test_at_s17_host_scope_sorting(client):
    """AT-S17: sort_order flips the first row (server-side sort over the full set)."""
    service = h.unique("s17")
    hosts = sorted(h.unique("host") for _ in range(3))
    for host in hosts:
        h.send_heartbeat(
            client,
            hostname=host,
            service_name=service,
            containers=[h.container("app", [h.process(1234)])],
        )

    asc = h.get_workload_status(
        client, scope="host", service_name=service, page=0, page_size=1, sort_by="hostname", sort_order="asc"
    )
    desc = h.get_workload_status(
        client, scope="host", service_name=service, page=0, page_size=1, sort_by="hostname", sort_order="desc"
    )
    assert h.rows_for(asc, service)[0]["hostname"] == hosts[0]
    assert h.rows_for(desc, service)[0]["hostname"] == hosts[-1]
