#!/usr/bin/env python3
"""
Fast acceptance tests for pre-dispatch profiling guardrails:

* PMU event validation  -> WORKLOAD_LEVEL_PROFILING_SPEC.md AT-S9
* Profiling capacity     -> capacity guardrails referenced by AT-S6 fan-out

These exercise the pure decision logic in
``backend.utils.dynamic_profiling_utils`` with an in-memory fake DBManager, so
they run in-process with no database or HTTP server (fast).

Run:
    cd src && python -m pytest tests/spec/backend/test_pmu_and_capacity_spec.py -v
"""

import pytest

pytest.importorskip("pydantic", reason="pydantic is required for these spec tests")
pytest.importorskip("humps", reason="pyhumps is required for these spec tests")

try:
    from backend.models.metrics_models import BulkProfilingRequest, ProfilingRequest
    from backend.utils.dynamic_profiling_utils import validate_pmu_events, validate_profiling_capacity
except Exception as exc:  # pragma: no cover - environment guard
    pytest.skip(f"backend modules not importable: {exc}", allow_module_level=True)


class FakeDBManager:
    """Minimal stand-in for DBManager covering only the methods the guardrails call."""

    def __init__(
        self,
        *,
        active_hosts=0,
        profiling_total=0,
        profiling_inside=0,
        profiling_outside=0,
        unsupported_events=None,
    ):
        self._active_hosts = active_hosts
        self._profiling_total = profiling_total
        self._profiling_inside = profiling_inside
        self._profiling_outside = profiling_outside
        self._unsupported_events = set(unsupported_events or [])

    # -- capacity --
    def get_active_hosts_count(self, service_name=None):
        return self._active_hosts

    def get_actively_profiling_hosts_count(
        self, service_name=None, host_inclusion_list=None, host_exclusion_list=None
    ):
        if host_inclusion_list is not None:
            return self._profiling_inside
        if host_exclusion_list is not None:
            return self._profiling_outside
        return self._profiling_total

    # -- PMU --
    def validate_perf_events_support(self, service_name, requested_events, target_hostnames=None):
        bad = sorted(self._unsupported_events.intersection(requested_events))
        if bad:
            return {"valid": False, "error_message": f"Unsupported perf events: {', '.join(bad)}"}
        return {"valid": True, "error_message": None}


def _start_request(**overrides) -> ProfilingRequest:
    data = {
        "service_name": "svc-a",
        "request_type": "start",
        "target_scope": "host",
        "target_hosts": {"host-a": None},
    }
    data.update(overrides)
    return ProfilingRequest(**data)


def _bulk(*requests) -> BulkProfilingRequest:
    return BulkProfilingRequest(requests=list(requests))


def _perf_args(events, mode="enabled_restricted"):
    return {"profiler_configs": {"perf": {"mode": mode, "events": events}}}


# ---------------------------------------------------------------------------
# AT-S9 — PMU validation
# ---------------------------------------------------------------------------


class TestPmuValidationSpec:
    def test_supported_events_pass(self):
        db = FakeDBManager(unsupported_events=[])
        req = _start_request(additional_args=_perf_args(["cycles", "instructions"]))
        ok, err = validate_pmu_events(_bulk(req), db)
        assert ok is True
        assert err is None

    def test_unsupported_event_is_rejected_with_clear_error(self):
        db = FakeDBManager(unsupported_events=["cache-misses"])
        req = _start_request(additional_args=_perf_args(["cycles", "cache-misses"]))
        ok, err = validate_pmu_events(_bulk(req), db)
        assert ok is False
        assert "svc-a" in err
        assert "cache-misses" in err

    def test_perf_disabled_skips_pmu_validation(self):
        db = FakeDBManager(unsupported_events=["cache-misses"])
        req = _start_request(additional_args=_perf_args(["cache-misses"], mode="disabled"))
        ok, err = validate_pmu_events(_bulk(req), db)
        assert ok is True and err is None

    def test_stop_requests_are_not_pmu_validated(self):
        db = FakeDBManager(unsupported_events=["cache-misses"])
        req = ProfilingRequest(
            service_name="svc-a",
            request_type="stop",
            target_scope="host",
            stop_level="host",
            target_hosts={"host-a": None},
            additional_args=_perf_args(["cache-misses"]),
        )
        ok, err = validate_pmu_events(_bulk(req), db)
        assert ok is True and err is None

    def test_workload_scope_without_target_hosts_does_not_crash(self):
        # AT-S9 for non-host scopes: target_hosts is None; events are validated
        # against the whole service instead of blowing up on None.keys().
        db = FakeDBManager(unsupported_events=[])
        req = _start_request(
            target_scope="service",
            target_hosts=None,
            target_entities=[{"service_name": "svc-a"}],
            additional_args=_perf_args(["cycles"]),
        )
        ok, err = validate_pmu_events(_bulk(req), db)
        assert ok is True and err is None


# ---------------------------------------------------------------------------
# Capacity guardrails
# ---------------------------------------------------------------------------


class TestCapacitySpec:
    def test_within_capacity_passes(self):
        # 100 active hosts, 10% cap => 10 allowed; request of 1 with 0 already profiling.
        db = FakeDBManager(active_hosts=100, profiling_total=0, profiling_outside=0)
        req = _start_request(target_hosts={"host-a": None})
        ok, err, hosts = validate_profiling_capacity(_bulk(req), db)
        assert ok is True
        assert err is None
        assert hosts == ["host-a"]

    def test_exceeding_percentage_capacity_is_rejected(self):
        # 100 active hosts, 10% cap => 10 allowed; 10 already profiling outside selection
        # + 1 new = 11 > 10 => rejected.
        db = FakeDBManager(active_hosts=100, profiling_total=10, profiling_outside=10)
        req = _start_request(target_hosts={"host-new": None})
        ok, err, _ = validate_profiling_capacity(_bulk(req), db)
        assert ok is False
        assert "capacity exceeded" in err.lower()

    def test_request_size_limit_is_rejected(self):
        db = FakeDBManager(active_hosts=10_000)
        many_hosts = {f"host-{i}": None for i in range(21)}  # MAX_PROFILING_REQUEST_HOSTS default = 20
        req = _start_request(target_hosts=many_hosts)
        ok, err, _ = validate_profiling_capacity(_bulk(req), db)
        assert ok is False
        assert "request size exceeded" in err.lower()

    def test_stop_only_bulk_skips_capacity(self):
        db = FakeDBManager(active_hosts=0)
        stop = ProfilingRequest(
            service_name="svc-a",
            request_type="stop",
            target_scope="host",
            stop_level="host",
            target_hosts={"host-a": None},
        )
        ok, err, _ = validate_profiling_capacity(_bulk(stop), db)
        assert ok is True and err is None
