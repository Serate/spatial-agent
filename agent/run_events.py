"""Versioned, bounded lifecycle events for realtime Agent consumers.

Run events are notifications, not a second result or trace contract.  They
carry enough safe state for a Console to show real progress while the
canonical Result/Evidence remains the source of truth for conclusions.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Any, Dict, Optional


RUN_EVENT_SCHEMA_VERSION = "spatial-agent.run-event.v1"
MAX_EVENT_MESSAGE = 240
MAX_EVENT_DATA_ITEMS = 16
MAX_EVENT_DATA_TEXT = 512
MAX_EVENT_LIMIT = 200

RUN_EVENT_PHASES = frozenset(
    {"resolve", "clarify", "plan", "validate", "execute", "answer", "evidence"}
)
RUN_EVENT_KINDS = frozenset(
    {
        "stage_started",
        "stage_progress",
        "stage_completed",
        "stage_failed",
        "tool_started",
        "tool_completed",
        "tool_failed",
        "heartbeat",
        "answer_delta",
        "run_completed",
        "run_failed",
        "run_waiting",
        "run_finished",
    }
)
RUN_EVENT_STATUSES = frozenset(
    {
        "CREATED",
        "QUEUED",
        "PLANNING",
        "PLANNED",
        "EXECUTING",
        "WAITING_FOR_DECISION",
        "COMPLETED",
        "NEEDS_CLARIFICATION",
        "REJECTED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "PENDING",
        "RUNNING",
        "BLOCKED",
    }
)
RUN_EVENT_DATA_FIELDS = frozenset(
    {
        "stage_index",
        "stage_count",
        "step_id",
        "tool",
        "attempts",
        "retryable",
        "error_category",
        "reason_code",
        "event_count",
        "answer_delta",
        "answer_length",
        "recovery_count",
        "cursor",
        "fallback",
        "source",
        "artifact_available",
        "result_type",
        "run_duration_ms",
        "elapsed_ms",
        "summary",
    }
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class RunEventError(ValueError):
    """Raised when an event cannot cross the public event boundary."""


def new_run_event(
    *,
    run_id: str,
    phase: str,
    kind: str,
    status: str,
    message: str,
    data: Optional[Mapping[str, Any]] = None,
    event_id: Optional[str] = None,
    created_at: Optional[str] = None,
    terminal: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build one unsequenced event for a state-store append operation."""

    return normalize_run_event(
        {
            "schema_version": RUN_EVENT_SCHEMA_VERSION,
            "event_id": event_id or uuid.uuid4().hex,
            "run_id": run_id,
            "sequence": 0,
            "phase": phase,
            "kind": kind,
            "status": status,
            "message": message,
            "created_at": created_at or _now_iso(),
            "data": dict(data or {}),
            "terminal": bool(terminal)
            if terminal is not None
            else kind in {"run_completed", "run_failed"},
        }
    )


def normalize_run_event(
    value: Mapping[str, Any],
    *,
    expected_run_id: Optional[str] = None,
    sequence: Optional[int] = None,
) -> Dict[str, Any]:
    """Return the bounded wire shape used by stores, SSE and polling.

    Unknown event data is dropped rather than forwarded.  This keeps future
    internal fields from accidentally becoming a public transport contract.
    """

    if not isinstance(value, Mapping):
        raise RunEventError("run event must be an object")
    schema_version = str(value.get("schema_version") or "").strip()
    if schema_version != RUN_EVENT_SCHEMA_VERSION:
        raise RunEventError("run event schema_version is unsupported")
    run_id = _bounded_text(value.get("run_id"), "run_id", 128)
    if expected_run_id is not None and run_id != str(expected_run_id):
        raise RunEventError("run event belongs to another run")
    event_id = _bounded_text(value.get("event_id"), "event_id", 96)
    phase = _bounded_text(value.get("phase"), "phase", 32)
    kind = _bounded_text(value.get("kind"), "kind", 48)
    status = _bounded_text(value.get("status"), "status", 40).upper()
    if phase not in RUN_EVENT_PHASES:
        raise RunEventError("run event phase is unsupported")
    if kind not in RUN_EVENT_KINDS:
        raise RunEventError("run event kind is unsupported")
    if status not in RUN_EVENT_STATUSES:
        raise RunEventError("run event status is unsupported")
    cursor = sequence if sequence is not None else value.get("sequence", 0)
    if isinstance(cursor, bool):
        raise RunEventError("run event sequence must be an integer")
    try:
        cursor = int(cursor)
    except (TypeError, ValueError) as exc:
        raise RunEventError("run event sequence must be an integer") from exc
    if cursor < 0:
        raise RunEventError("run event sequence must not be negative")
    created_at = _bounded_text(value.get("created_at"), "created_at", 64)
    message = _safe_text(value.get("message"), MAX_EVENT_MESSAGE)
    if not message:
        raise RunEventError("run event message must be non-empty")
    data = _normalize_data(value.get("data"))
    terminal = value.get("terminal", kind in {"run_completed", "run_failed"})
    if not isinstance(terminal, bool):
        raise RunEventError("run event terminal must be boolean")
    return {
        "schema_version": RUN_EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "run_id": run_id,
        "sequence": cursor,
        "phase": phase,
        "kind": kind,
        "status": status,
        "message": message,
        "created_at": created_at,
        "data": data,
        "terminal": terminal,
    }


def validate_event_cursor(value: Any) -> int:
    """Normalize an SSE/polling cursor without accepting ambiguous values."""

    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise RunEventError("event cursor must be a non-negative integer")
    try:
        cursor = int(value)
    except (TypeError, ValueError) as exc:
        raise RunEventError("event cursor must be a non-negative integer") from exc
    if cursor < 0:
        raise RunEventError("event cursor must be a non-negative integer")
    return cursor


def validate_event_limit(value: Any, default: int = 100) -> int:
    if value is None or value == "":
        return min(MAX_EVENT_LIMIT, max(1, int(default)))
    if isinstance(value, bool):
        raise RunEventError("event limit must be a positive integer")
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise RunEventError("event limit must be a positive integer") from exc
    if limit < 1 or limit > MAX_EVENT_LIMIT:
        raise RunEventError("event limit is outside the supported range")
    return limit


def _normalize_data(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RunEventError("run event data must be an object")
    normalized: Dict[str, Any] = {}
    for key, raw in list(value.items())[:MAX_EVENT_DATA_ITEMS]:
        name = str(key)
        if name not in RUN_EVENT_DATA_FIELDS:
            continue
        safe = _safe_value(raw)
        if safe is not None:
            normalized[name] = safe
    return normalized


def _safe_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, str):
        return _safe_text(value, MAX_EVENT_DATA_TEXT)
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in list(value)[:8]]
    return None


def _bounded_text(value: Any, field: str, limit: int) -> str:
    text = _safe_text(value, limit)
    if not text:
        raise RunEventError(field + " must be non-empty")
    return text


def _safe_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = _CONTROL_CHARS.sub("", str(value)).strip()
    return text[:limit]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "MAX_EVENT_LIMIT",
    "RUN_EVENT_DATA_FIELDS",
    "RUN_EVENT_KINDS",
    "RUN_EVENT_PHASES",
    "RUN_EVENT_SCHEMA_VERSION",
    "RunEventError",
    "new_run_event",
    "normalize_run_event",
    "validate_event_cursor",
    "validate_event_limit",
]
