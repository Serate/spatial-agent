"""Bounded, provider-neutral Planner repair contracts.

Repair can correct only a small set of structural Planner mistakes.  It never
expands the capability/tool allowlist and never carries raw provider output.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PLANNER_REPAIR_REQUEST_SCHEMA_VERSION = "spatial-agent.planner-repair-request.v1"
PLANNER_REPAIR_LINEAGE_SCHEMA_VERSION = "spatial-agent.planner-repair-lineage.v1"
REPAIRABLE_PLANNER_ERRORS = frozenset(
    {
        "plan_response_field_invalid",
        "plan_component_field_invalid",
        "plan_components_unexpected",
        "plan_components_invalid",
        "plan_component_field_missing",
    }
)
_LINEAGE_STATUSES = {"not_attempted", "repaired", "failed", "skipped"}


class PlannerRepairError(ValueError):
    """Invalid repair input; safe for application-level projection."""

    def __init__(self, message: str, *, code: str = "planner_repair_invalid") -> None:
        self.code = str(code or "planner_repair_invalid")[:96]
        super().__init__(str(message)[:320])


def is_repairable_planner_error(reason_code: Any) -> bool:
    """Return whether a bounded model repair may be attempted."""

    return str(reason_code or "").strip() in REPAIRABLE_PLANNER_ERRORS


def build_planner_repair_request(
    reason_code: Any,
    *,
    request_fingerprint: Any = None,
    context_schema_version: Any = None,
    attempt: int = 1,
    max_attempts: int = 1,
) -> dict[str, Any]:
    """Build the only repair instruction the provider may receive."""

    code = str(reason_code or "").strip()[:96]
    if code not in REPAIRABLE_PLANNER_ERRORS:
        raise PlannerRepairError(
            "planner error is not repairable", code="repair_not_allowed"
        )
    if int(attempt) != 1 or int(max_attempts) != 1:
        raise PlannerRepairError(
            "planner repair allows one attempt", code="repair_attempt_limit"
        )
    return {
        "schema_version": PLANNER_REPAIR_REQUEST_SCHEMA_VERSION,
        "reason_code": code,
        "request_fingerprint": str(request_fingerprint or "").strip()[:128] or None,
        "context_schema_version": str(context_schema_version or "").strip()[:96] or None,
        "allowed_outcome": "success|needs_clarification|rejected",
        "attempt": 1,
        "max_attempts": 1,
    }


def build_repair_lineage(
    *,
    reason_code: Any,
    status: str,
    attempted: bool,
    count: int,
    request_fingerprint: Any = None,
) -> dict[str, Any]:
    """Build a safe, bounded repair receipt for result/evidence persistence."""

    normalized_status = str(status or "").strip().lower()
    if normalized_status not in _LINEAGE_STATUSES:
        normalized_status = "failed"
    bounded_count = max(0, min(1, int(count)))
    return {
        "schema_version": PLANNER_REPAIR_LINEAGE_SCHEMA_VERSION,
        "attempted": bool(attempted),
        "count": bounded_count,
        "reason_code": str(reason_code or "planner_repair_unavailable")[:96],
        "status": normalized_status,
        "request_fingerprint": str(request_fingerprint or "").strip()[:128] or None,
    }


def safe_repair_request(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Project a repair request without accepting arbitrary provider fields."""

    if not isinstance(value, Mapping):
        return None
    try:
        result = build_planner_repair_request(
            value.get("reason_code"),
            request_fingerprint=value.get("request_fingerprint"),
            context_schema_version=value.get("context_schema_version"),
            attempt=value.get("attempt", 1),
            max_attempts=value.get("max_attempts", 1),
        )
    except (PlannerRepairError, TypeError, ValueError):
        return None
    return result


__all__ = [
    "PLANNER_REPAIR_LINEAGE_SCHEMA_VERSION",
    "PLANNER_REPAIR_REQUEST_SCHEMA_VERSION",
    "REPAIRABLE_PLANNER_ERRORS",
    "PlannerRepairError",
    "build_planner_repair_request",
    "build_repair_lineage",
    "is_repairable_planner_error",
    "safe_repair_request",
]
