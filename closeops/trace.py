"""Neatlogs tracing wiring for closeops (free tier, zero LLM cost).

The whole close (prepare -> decide -> apply -> check) shows up as one Neatlogs
session with a WORKFLOW span per step and a TOOL span per control. None of this
calls a paid model API -- the spans only wrap deterministic code.

Everything here is a no-op unless ``NEATLOGS_API_KEY`` is set: ``init`` skips
entirely and the span decorators become transparent passthroughs. That keeps the
test suite and CI free of any key or network call. The decorators check the
enabled flag at *call* time, so decorating a function before ``init`` runs (as the
controls do at import) still traces once a key is present.
"""
from __future__ import annotations

import functools
import os
from datetime import datetime, timezone

try:  # neatlogs is an optional extra ([trace]); absence must never break a run
    import neatlogs
except Exception:  # pragma: no cover - only when the extra is not installed
    neatlogs = None

WORKFLOW_NAME = "closeops"

_enabled = False


def enabled() -> bool:
    return _enabled


def init(period: str = "2026-09", tags=None) -> bool:
    """Initialise Neatlogs when a key is present; otherwise skip cleanly.

    Returns True when tracing is live, False when it was skipped.
    """
    global _enabled
    key = os.environ.get("NEATLOGS_API_KEY")
    if not key or neatlogs is None:
        _enabled = False
        return False
    try:
        neatlogs.init(
            api_key=key,
            workflow_name=WORKFLOW_NAME,
            tags=list(tags) if tags is not None else ["syndicate", period],
        )
        _enabled = True
    except Exception:  # pragma: no cover - defensive: never fail the close on trace
        _enabled = False
    return _enabled


def span(kind: str, name: str, **kwargs):
    """Return a decorator that wraps a function in a Neatlogs span.

    When tracing is disabled the decorator is a transparent passthrough. The
    enabled check happens at call time so import-time decoration still traces
    once ``init`` has run.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kw):
            if _enabled and neatlogs is not None:
                try:
                    traced = neatlogs.span(kind, name, **kwargs)(fn)
                    return traced(*args, **kw)
                except Exception:  # pragma: no cover - tracing must not break work
                    return fn(*args, **kw)
            return fn(*args, **kw)

        return wrapper

    return decorator


def workflow_span(step: str, task: str, period: str = "2026-09"):
    """WORKFLOW span for a close step (prepare/decide/apply/check)."""
    return span("WORKFLOW", f"{step}:{task}", tags=[task], session_id=f"close-{period}")


def tool_span(name: str):
    """TOOL span for one control function (C1..C10)."""
    return span("TOOL", name)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_trace_id(workflow_name: str = WORKFLOW_NAME) -> str:
    """Return ``neatlogs:<id>`` for the active span, else a stable fallback.

    Reading the *current* trace id is an OpenTelemetry call (verified in plan
    section 7); ``neatlogs.extract_trace_context`` is for cross-process
    propagation, not for this. When no span is active we fall back to
    ``neatlogs:<workflow_name>-<timestamp>`` so every judgment still gets an id.
    """
    try:
        from opentelemetry import trace as _otel

        ctx = _otel.get_current_span().get_span_context()
        if ctx is not None and ctx.trace_id:
            return f"neatlogs:{format(ctx.trace_id, '032x')}"
    except Exception:
        pass
    return f"neatlogs:{workflow_name}-{_now_iso()}"
