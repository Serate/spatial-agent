"""Stable, credential-free run-level failure evidence."""

from typing import Any, Mapping


FAILURE_SCHEMA_VERSION = "spatial-agent.failure.v1"
_PHASES = {"planning", "execution", "control", "persistence", "unknown"}


def build_failure_evidence(
    *,
    status: Any,
    category: Any = None,
    code: Any = None,
    phase: Any = None,
    retryable: Any = None,
) -> dict[str, Any]:
    """Build bounded machine-readable failure metadata without raw messages."""
    normalized_status = str(status or "FAILED")[:32]
    normalized_category = _category_for_status(normalized_status, category)
    normalized_code = str(code or _default_code(normalized_status, normalized_category))[:96]
    normalized_phase = str(phase or _default_phase(normalized_status, normalized_category))
    if normalized_phase not in _PHASES:
        normalized_phase = "unknown"
    return {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "status": normalized_status,
        "category": normalized_category,
        "code": normalized_code,
        "phase": normalized_phase,
        "retryable": bool(retryable) if retryable is not None else False,
    }


def failure_from_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalize a run payload, keeping backward compatibility with old runs."""
    status = str(payload.get("status") or "")
    if status == "COMPLETED" or not payload.get("error"):
        return None
    existing = payload.get("failure")
    if isinstance(existing, Mapping):
        return build_failure_evidence(
            status=status,
            category=existing.get("category") or payload.get("error_category"),
            code=existing.get("code") or payload.get("error_code"),
            phase=existing.get("phase"),
            retryable=existing.get("retryable"),
        )
    return build_failure_evidence(
        status=status,
        category=payload.get("error_category"),
        code=payload.get("error_code"),
        retryable=payload.get("retryable"),
    )


def _category_for_status(status: str, category: Any) -> str:
    if status == "CANCELLED":
        return "cancelled"
    if status == "TIMED_OUT":
        return "timeout"
    if status == "REJECTED":
        return "rejected"
    if status == "NEEDS_CLARIFICATION":
        return "clarification"
    value = str(category or "execution")[:64]
    return value or "execution"


def _default_phase(status: str, category: str) -> str:
    if status in {"NEEDS_CLARIFICATION", "REJECTED"} or category in {
        "planning",
        "clarification",
        "rejected",
    }:
        return "planning"
    if status in {"CANCELLED", "TIMED_OUT"} or category in {"cancelled", "timeout"}:
        return "control"
    return "execution"


def _default_code(status: str, category: str) -> str:
    return {
        "CANCELLED": "run_cancelled",
        "TIMED_OUT": "run_timeout",
        "REJECTED": "request_rejected",
        "NEEDS_CLARIFICATION": "clarification_required",
        "provider": "provider_error",
        "planning": "planning_error",
        "policy": "policy_denied",
        "tool": "tool_error",
        "timeout": "run_timeout",
        "cancelled": "run_cancelled",
        "clarification": "clarification_required",
        "rejected": "request_rejected",
    }.get(category, "execution_failed")
