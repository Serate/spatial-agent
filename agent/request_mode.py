"""Versioned, domain-neutral classification of one completed request.

The mode is derived from the Runtime result after the actual lifecycle has
run.  It is observability metadata, not a second planner or an authorization
decision.  Keeping the derivation here gives Result, persistence, recovery,
and transports one small interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REQUEST_MODE_SCHEMA_VERSION = "spatial-agent.request-mode.v1"
REQUEST_MODES = frozenset({"answer", "execute", "mixed", "clarify"})

_DEFAULT_REASON = {
    "answer": "direct_answer",
    "execute": "tool_execution",
    "mixed": "tool_and_answer",
    "clarify": "clarification_required",
}
_MAX_REASON_LENGTH = 64
_MAX_TOOL_COUNT = 128


def normalize_request_mode(value: Any) -> dict[str, Any]:
    """Return a bounded public request-mode projection.

    Old snapshots may not contain this field; callers should omit the field
    in that case.  Invalid optional values are normalized to a safe answer
    mode instead of leaking arbitrary model/provider metadata.
    """

    source = value if isinstance(value, Mapping) else {}
    mode = str(source.get("mode") or "answer").strip().lower()
    if mode not in REQUEST_MODES:
        mode = "answer"
    reason_code = str(source.get("reason_code") or _DEFAULT_REASON[mode]).strip()
    if not reason_code:
        reason_code = _DEFAULT_REASON[mode]
    try:
        tool_count = int(source.get("tool_count", 0))
    except (TypeError, ValueError):
        tool_count = 0
    tool_count = max(0, min(tool_count, _MAX_TOOL_COUNT))
    execution_started = source.get("execution_started", False)
    if not isinstance(execution_started, bool):
        execution_started = bool(execution_started)
    return {
        "schema_version": REQUEST_MODE_SCHEMA_VERSION,
        "mode": mode,
        "reason_code": reason_code[:_MAX_REASON_LENGTH],
        "tool_count": tool_count,
        "execution_started": execution_started,
    }


def derive_request_mode(result: Any) -> dict[str, Any]:
    """Derive request mode from actual steps, answer, and lifecycle status."""

    status = getattr(getattr(result, "status", None), "value", getattr(result, "status", ""))
    status = str(status or "").upper()
    steps = getattr(result, "steps", ()) or ()
    steps = list(steps)[:_MAX_TOOL_COUNT]
    tool_count = len(steps)
    execution_started = any(
        str(getattr(step, "status", "PENDING") or "PENDING").upper() != "PENDING"
        for step in steps
    )
    if status == "NEEDS_CLARIFICATION":
        mode = "clarify"
        reason_code = "clarification_required"
    elif status == "WAITING_FOR_DECISION":
        mode = "execute"
        reason_code = "approval_required"
    elif tool_count:
        mode = "mixed" if getattr(result, "answer", None) else "execute"
        reason_code = _DEFAULT_REASON[mode]
    elif status in {"FAILED", "REJECTED", "CANCELLED", "TIMED_OUT"}:
        mode = "answer"
        reason_code = "unavailable"
    else:
        mode = "answer"
        reason_code = "direct_answer"
    return normalize_request_mode(
        {
            "mode": mode,
            "reason_code": reason_code,
            "tool_count": tool_count,
            "execution_started": execution_started,
        }
    )


__all__ = [
    "REQUEST_MODE_SCHEMA_VERSION",
    "REQUEST_MODES",
    "derive_request_mode",
    "normalize_request_mode",
]
