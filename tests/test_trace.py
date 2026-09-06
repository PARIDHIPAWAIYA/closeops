"""Tests for closeops.trace — Neatlogs wiring that no-ops without a key.

None of these require NEATLOGS_API_KEY. When the key is unset, init() must skip
entirely and the span decorators must be transparent passthroughs, so the whole
suite runs with zero network calls and zero spend.
"""
from __future__ import annotations

from closeops import trace


def test_init_skips_without_key(monkeypatch):
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    assert trace.init(period="2026-09") is False


def test_workflow_span_is_transparent_without_key(monkeypatch):
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    trace.init(period="2026-09")

    @trace.workflow_span("decide", "bank-rec")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_tool_span_is_transparent_without_key(monkeypatch):
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    trace.init(period="2026-09")

    @trace.tool_span("C7")
    def control():
        return "ok"

    assert control() == "ok"


def test_current_trace_id_falls_back_to_workflow_and_timestamp(monkeypatch):
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    trace.init(period="2026-09")
    tid = trace.current_trace_id()
    assert isinstance(tid, str) and tid
    assert tid.startswith("neatlogs:")
    # no active span -> the fallback carries the workflow name
    assert "closeops" in tid


def test_current_trace_id_parses_injected_traceparent(monkeypatch):
    # With tracing enabled, current_trace_id must read the *real* id via
    # neatlogs.inject_trace_context (get_current_span sees trace id 0 under the
    # isolated tracer provider). Live-verified traceparent shape.
    traceparent = "00-f2d70ed9b9bb0c175665bc4a0b10604c-4dfe7a45c584f7b1-03"

    def fake_inject(carrier):
        carrier["traceparent"] = traceparent
        return True

    monkeypatch.setattr(trace, "_enabled", True)
    monkeypatch.setattr(trace.neatlogs, "inject_trace_context", fake_inject)
    assert trace.current_trace_id() == "neatlogs:f2d70ed9b9bb0c175665bc4a0b10604c"


def test_current_trace_id_falls_back_when_traceparent_is_zero(monkeypatch):
    # An all-zero trace id means no active span: fall back to workflow+timestamp.
    def fake_inject(carrier):
        carrier["traceparent"] = "00-00000000000000000000000000000000-0000000000000000-00"
        return False

    monkeypatch.setattr(trace, "_enabled", True)
    monkeypatch.setattr(trace.neatlogs, "inject_trace_context", fake_inject)
    tid = trace.current_trace_id()
    assert tid.startswith("neatlogs:closeops-")


def test_span_preserves_function_metadata(monkeypatch):
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)

    @trace.workflow_span("decide", "bank-rec")
    def documented():
        """docstring stays."""
        return 1

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "docstring stays."
