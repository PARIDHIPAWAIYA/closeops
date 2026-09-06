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


def _trace_id_from_traceparent(traceparent: str):
    """Pull the 32-hex trace id out of a W3C ``traceparent`` header.

    Format: ``00-<32-hex trace id>-<16-hex span id>-<flags>``. Returns None for a
    malformed header or an all-zero (invalid/absent) trace id.
    """
    if not traceparent:
        return None
    parts = traceparent.split("-")
    if len(parts) < 3:
        return None
    trace_id = parts[1]
    if not trace_id or set(trace_id) == {"0"}:
        return None
    return trace_id


def current_trace_id(workflow_name: str = WORKFLOW_NAME) -> str:
    """Return ``neatlogs:<id>`` for the active span, else a stable fallback.

    neatlogs 1.4.21 runs an isolated tracer provider, so
    ``opentelemetry.trace.get_current_span()`` sees an invalid span (trace id 0)
    even inside ``@neatlogs.span``. The working call is
    ``neatlogs.inject_trace_context(carrier)``, which writes a W3C
    ``traceparent`` we parse for the real id. When injection yields nothing we
    fall back to ``neatlogs:<workflow_name>-<timestamp>`` so every judgment still
    gets an id.
    """
    if _enabled and neatlogs is not None:
        try:
            carrier: dict = {}
            neatlogs.inject_trace_context(carrier)
            trace_id = _trace_id_from_traceparent(carrier.get("traceparent"))
            if trace_id:
                return f"neatlogs:{trace_id}"
        except Exception:  # pragma: no cover - defensive; fall back to timestamp
            pass
    return f"neatlogs:{workflow_name}-{_now_iso()}"
