#!/usr/bin/env python3
"""
Acceptance / spec tests for the ProfilingRequest validation contract.

Unlike the sibling ``test_metrics_profile_request.py`` (which drives a *live*
backend over HTTP), these tests import the ``ProfilingRequest`` pydantic model
directly and exercise its validation rules in-process. They are fast, need no
running server or database, and serve as the executable specification for the
start/stop targeting rules.

The central invariant (which the host/service stop regression violated):

    A host-/service-level STOP must not carry any PID — neither in
    ``target_hosts`` nor via a ``target_entities`` selector. The frontend
    request builder is expected to produce payloads that satisfy this spec
    (see ``profilingRequestBuilder.mjs`` / ``profilingRequestBuilder.test.mjs``).

Run just this file:

    cd src && python -m pytest tests/unit/backend/test_profiling_request_spec.py -v
"""

import sys
from pathlib import Path

import pytest

# Make the backend + gprofiler_dev packages importable without a full install:
#   .../src/gprofiler      contains the ``backend`` package
#   .../src/gprofiler-dev  contains the ``gprofiler_dev`` package
_SRC_ROOT = Path(__file__).resolve().parents[3]
for _pkg_root in (_SRC_ROOT / "gprofiler", _SRC_ROOT / "gprofiler-dev"):
    if str(_pkg_root) not in sys.path:
        sys.path.insert(0, str(_pkg_root))

# Skip cleanly if backend deps (pydantic, humps, ...) are not installed here.
pytest.importorskip("pydantic", reason="pydantic is required for the ProfilingRequest spec tests")
pytest.importorskip("humps", reason="pyhumps is required for the ProfilingRequest spec tests")

try:
    from pydantic import ValidationError
    from backend.models.metrics_models import ProfilingRequest
except Exception as exc:  # pragma: no cover - environment guard
    pytest.skip(f"backend.models.metrics_models not importable: {exc}", allow_module_level=True)


def _base(**overrides):
    """A minimal valid request skeleton; override per-case."""
    data = {
        "service_name": "svc-a",
        "request_type": "start",
        "target_scope": "host",
        "target_hosts": {"host-a": None},
    }
    data.update(overrides)
    return data


def _make(**overrides) -> ProfilingRequest:
    return ProfilingRequest(**_base(**overrides))


def _entity(**fields):
    """Build a target_entities selector dict (snake_case field names)."""
    return {"service_name": "svc-a", **fields}


# ---------------------------------------------------------------------------
# Host-/service-level STOP — the regression surface
# ---------------------------------------------------------------------------


class TestHostLevelStopSpec:
    def test_host_stop_without_pids_is_valid(self):
        req = _make(
            request_type="stop",
            target_scope="host",
            stop_level="host",
            target_hosts={"host-a": None},
            target_entities=[_entity(hostname="host-a")],
        )
        assert req.request_type == "stop"
        assert req.stop_level == "host"

    def test_service_stop_without_pids_is_valid(self):
        req = _make(
            request_type="stop",
            target_scope="service",
            stop_level="host",
            target_hosts=None,
            target_entities=[_entity(hostname="host-a")],
        )
        assert req.stop_level == "host"

    def test_host_stop_with_pids_in_target_hosts_is_rejected(self):
        with pytest.raises(ValidationError, match="No PIDs should be provided"):
            _make(
                request_type="stop",
                target_scope="host",
                stop_level="host",
                target_hosts={"host-a": [4242]},
            )

    def test_host_stop_with_pid_in_target_entity_is_rejected(self):
        # This is exactly what the buggy frontend used to send.
        with pytest.raises(ValidationError, match="No PIDs should be provided"):
            _make(
                request_type="stop",
                target_scope="host",
                stop_level="host",
                target_hosts={"host-a": None},
                target_entities=[_entity(hostname="host-a", pid=4242)],
            )

    def test_host_stop_with_pid_zero_in_entity_is_rejected(self):
        # A PID of 0 still counts as "a PID was provided" for a host-level stop.
        with pytest.raises(ValidationError, match="No PIDs should be provided"):
            _make(
                request_type="stop",
                target_scope="host",
                stop_level="host",
                target_hosts={"host-a": None},
                target_entities=[_entity(hostname="host-a", pid=0)],
            )


# ---------------------------------------------------------------------------
# Process-level STOP
# ---------------------------------------------------------------------------


class TestProcessLevelStopSpec:
    def test_process_stop_with_pids_in_target_hosts_is_valid(self):
        req = _make(
            request_type="stop",
            target_scope="process",
            stop_level="process",
            target_hosts={"host-a": [4242]},
        )
        assert req.stop_level == "process"

    def test_process_stop_with_pid_in_entity_is_valid(self):
        req = _make(
            request_type="stop",
            target_scope="process",
            stop_level="process",
            target_hosts=None,
            target_entities=[_entity(hostname="host-a", pid=4242, process_name="python")],
        )
        assert req.stop_level == "process"

    def test_process_stop_without_any_pid_is_rejected(self):
        with pytest.raises(ValidationError, match="At least one PID or workload selector"):
            _make(
                request_type="stop",
                target_scope="process",
                stop_level="process",
                target_hosts={"host-a": None},
            )


# ---------------------------------------------------------------------------
# START requests are unaffected by the PID rules
# ---------------------------------------------------------------------------


class TestStartSpec:
    def test_start_with_target_hosts_is_valid(self):
        req = _make(request_type="start", target_scope="host", target_hosts={"host-a": None})
        assert req.request_type == "start"

    def test_start_with_entities_carrying_pid_is_valid(self):
        # PID rules only apply to stop requests, so a start is fine either way.
        req = _make(
            request_type="start",
            target_scope="process",
            target_hosts=None,
            target_entities=[_entity(hostname="host-a", pid=4242)],
        )
        assert req.request_type == "start"


# ---------------------------------------------------------------------------
# Shared targeting requirements
# ---------------------------------------------------------------------------


class TestTargetingRequirementsSpec:
    def test_request_without_any_target_is_rejected(self):
        with pytest.raises(ValidationError, match="At least one target_hosts entry or target_entities"):
            ProfilingRequest(
                service_name="svc-a",
                request_type="start",
                target_scope="host",
                target_hosts=None,
                target_entities=None,
            )

    @pytest.mark.parametrize("bad_scope", ["cluster", "", "HOST"])
    def test_invalid_target_scope_is_rejected(self, bad_scope):
        with pytest.raises(ValidationError):
            _make(target_scope=bad_scope)

    @pytest.mark.parametrize("bad_stop_level", ["node", "pod", ""])
    def test_invalid_stop_level_is_rejected(self, bad_stop_level):
        with pytest.raises(ValidationError):
            _make(request_type="stop", stop_level=bad_stop_level, target_hosts={"host-a": None})
