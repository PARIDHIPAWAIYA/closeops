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


def test_span_preserves_function_metadata(monkeypatch):
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)

    @trace.workflow_span("decide", "bank-rec")
    def documented():
        """docstring stays."""
        return 1

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "docstring stays."
