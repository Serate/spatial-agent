"""Finite, bounded classification for failures crossing public seams.

The runtime has several historical error helpers.  This module is the single
place where an exception becomes safe governance metadata; callers may keep the
original human-readable error for compatibility, but public evidence should
use only the fields returned here.
"""

from __future__ import annotations

import builtins
import sqlite3
from typing import Any, Mapping

from .errors import (
    AnswerUnavailable,
    ClarificationNeeded,
    PersistenceError,
    RequestRejected,
    RunCancelled,
    RunTimedOut,
    ToolError,
)
from .tool_provider import ToolProviderError


FAILURE_CATEGORIES = frozenset(
    {
        "input",
        "clarification",
        "policy",
        "provider",
        "timeout",
        "data_unavailable",
        "persistence",
        "control",
        "cancelled",
        "internal",
        "tool",
        # Existing bounded labels remain valid while old artifacts migrate.
        "planning",
        "rejected",
        "decision",
        "approval",
        "budget",
        "concurrency_limited",
        "worker_exception",
        "tool_gate",
        "tool_validation",
        "reference",
        "backend_execution",
        "execution",
    }
)

FAILURE_PHASES = frozenset(
    {
        "planning",
        "execution",
        "answer",
        "control",
        "persistence",
        "transport",
        "recovery",
        "unknown",
    }
)


_CATEGORY_ALIASES = {
    "invalid_input": "input",
    "unavailable": "data_unavailable",
    "availability": "data_unavailable",
    "answer_unavailable": "data_unavailable",
    "database": "persistence",
    "sqlite": "persistence",
    "internal_error": "internal",
}


def classify_exception(
    exc: BaseException | None,
    *,
    phase: str | None = None,
    status: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Return bounded ``category/code/phase/retryable`` metadata.

    Explicit metadata attached by a typed error wins over text heuristics.  A
    text check is used only for legacy ``sqlite3``/timeout exceptions that do
    not carry metadata.  No exception message is copied into the result.
    """

    error = exc if isinstance(exc, BaseException) else None
    category = _category(error, status=status, source=source)
    code = _code(error, category=category, status=status)
    selected_phase = _phase(error, category=category, phase=phase, status=status)
    retryable = _retryable(error, category=category, status=status)
    return {
        "category": category,
        "code": code,
        "phase": selected_phase,
        "retryable": retryable,
    }


def classify_error_message(
    message: Any,
    *,
    phase: str | None = None,
    status: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Classify a legacy message without treating it as public evidence."""

    return classify_exception(
        _MessageError(str(message or "")),
        phase=phase,
        status=status,
        source=source,
    )


class _MessageError(Exception):
    pass


def normalize_failure_fields(
    value: Mapping[str, Any] | None,
    *,
    status: str | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    """Normalize stored fields without trusting arbitrary category strings."""

    raw = value if isinstance(value, Mapping) else {}
    category = _normalize_category(raw.get("category"))
    selected_phase = _normalize_phase(raw.get("phase") or phase, category, status)
    code = _bounded_code(raw.get("code")) or _default_code(category, status)
    retryable = (
        bool(raw["retryable"])
        if "retryable" in raw
        else _retryable(None, category=category, status=status)
    )
    return {
        "category": category,
        "code": code,
        "phase": selected_phase,
        "retryable": retryable,
    }


def _category(
    exc: BaseException | None,
    *,
    status: str | None,
    source: str | None,
) -> str:
    normalized_status = str(status or "").upper()
    if normalized_status == "CANCELLED":
        return "cancelled"
    if normalized_status == "TIMED_OUT":
        return "timeout"
    if normalized_status == "NEEDS_CLARIFICATION":
        return "clarification"
    if normalized_status == "REJECTED":
        return "rejected"
    if isinstance(exc, AnswerUnavailable):
        return "data_unavailable"
    if isinstance(exc, ClarificationNeeded):
        return "clarification"
    if isinstance(exc, RequestRejected):
        return "policy"
    if isinstance(exc, RunCancelled):
        return "cancelled"
    if isinstance(exc, RunTimedOut) or isinstance(exc, builtins.TimeoutError):
        return "timeout"
    if isinstance(exc, PersistenceError):
        return "persistence"
    if isinstance(exc, sqlite3.OperationalError) and _is_sqlite_contention(exc):
        return "persistence"
    if isinstance(exc, ToolProviderError):
        return "provider"
    if isinstance(exc, ToolError):
        return _normalize_category(getattr(exc, "category", None), default="tool")
    declared = getattr(exc, "category", None)
    if declared:
        return _normalize_category(declared)
    text = str(exc or "").lower()
    if any(token in text for token in ("policy", "rejected", "not authorized", "未授权", "拒绝")):
        return "policy"
    if any(token in text for token in ("data unavailable", "dataset unavailable", "数据不可用", "不可用")):
        return "data_unavailable"
    if any(token in text for token in ("timeout", "timed out", "超时")):
        return "timeout"
    if any(token in text for token in ("provider", "upstream", "network", "socket", "openai", "api")):
        return "provider"
    if any(token in text for token in ("planner", "plan", "schema", "规划")):
        return "planning"
    if any(token in text for token in ("tool", "backend", "dataset", "raster", "栅格", "数据")):
        return "tool"
    if isinstance(exc, ValueError):
        return "input"
    if source == "worker":
        # Keep the historical worker observation label until its consumers are
        # migrated; direct lifecycle classification remains ``internal``.
        return "worker_exception"
    if str(status or "").upper() == "FAILED":
        return "execution"
    return "internal"


def _code(exc: BaseException | None, *, category: str, status: str | None) -> str:
    declared = _bounded_code(getattr(exc, "code", None)) if exc is not None else None
    if declared:
        return declared
    return _default_code(category, status)


def _phase(
    exc: BaseException | None,
    *,
    category: str,
    phase: str | None,
    status: str | None,
) -> str:
    declared = getattr(exc, "phase", None) if exc is not None else None
    return _normalize_phase(declared or phase, category, status)


def _retryable(
    exc: BaseException | None,
    *,
    category: str,
    status: str | None,
) -> bool:
    declared = getattr(exc, "retryable", None) if exc is not None else None
    if declared is not None:
        return bool(declared)
    if category in {"provider", "timeout", "persistence"}:
        return True
    if str(status or "").upper() == "TIMED_OUT":
        return True
    return False


def _normalize_category(value: Any, default: str = "internal") -> str:
    normalized = str(value or "").strip()[:64]
    normalized = _CATEGORY_ALIASES.get(normalized, normalized)
    return normalized if normalized in FAILURE_CATEGORIES else default


def _normalize_phase(value: Any, category: str, status: str | None) -> str:
    normalized = str(value or "").strip().lower()[:32]
    if normalized in FAILURE_PHASES:
        return normalized
    if category == "persistence":
        return "persistence"
    if category == "data_unavailable":
        return "answer"
    if category in {"cancelled", "timeout", "control"} or str(status or "").upper() in {
        "CANCELLED",
        "TIMED_OUT",
    }:
        return "control"
    if category in {
        "clarification",
        "policy",
        "planning",
        "rejected",
        "input",
    } or str(status or "").upper() in {"NEEDS_CLARIFICATION", "REJECTED"}:
        return "planning"
    return "execution"


def _default_code(category: str, status: str | None) -> str:
    status_code = {
        "CANCELLED": "run_cancelled",
        "TIMED_OUT": "run_timeout",
        "REJECTED": "request_rejected",
        "NEEDS_CLARIFICATION": "clarification_required",
    }.get(str(status or "").upper())
    if status_code:
        return status_code
    return {
        "input": "invalid_request",
        "clarification": "clarification_required",
        "policy": "request_rejected",
        "provider": "provider_error",
        "timeout": "run_timeout",
        "data_unavailable": "answer_unavailable",
        "persistence": "sqlite_busy",
        "control": "control_error",
        "cancelled": "run_cancelled",
        "tool": "tool_error",
        "planning": "planning_error",
        "rejected": "request_rejected",
        "internal": "internal_error",
        "worker_exception": "worker_exception",
    }.get(category, "internal_error")


def _bounded_code(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized[:96] if normalized else None


def _is_sqlite_contention(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("locked", "busy", "cannot start a transaction"))


__all__ = [
    "FAILURE_CATEGORIES",
    "FAILURE_PHASES",
    "classify_error_message",
    "classify_exception",
    "normalize_failure_fields",
]
