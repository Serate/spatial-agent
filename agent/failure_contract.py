"""Stable, credential-free run-level failure evidence."""

from typing import Any, Mapping

from .error_taxonomy import FAILURE_CATEGORIES, FAILURE_PHASES, normalize_failure_fields


FAILURE_SCHEMA_VERSION = "spatial-agent.failure.v1"
_PHASES = set(FAILURE_PHASES)


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
    fields = normalize_failure_fields(
        {
            "category": normalized_category,
            "code": code,
            "phase": phase,
            "retryable": retryable,
        },
        status=normalized_status,
    )
    return {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "status": normalized_status,
        **fields,
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
    return value if value in FAILURE_CATEGORIES else "internal"


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
