"""Safe receipts for plans that have crossed the execution gate.

This module does not authorize a run.  It records whether the already-built
TaskPlan bridge and execution binding form a complete, validated closure so
transport and UI layers can explain the boundary without exposing plan args.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent.runtime_core.execution_binding import (
    ExecutionBindingError,
    validate_execution_binding,
)


CANONICAL_PLAN_RECEIPT_SCHEMA_VERSION = "spatial-agent.canonical-plan-receipt.v1"
_MAX_COMPONENTS = 8


def build_canonical_plan_receipt(
    task_plan_bridge: Mapping[str, Any] | None,
    execution_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a receipt that is executable only after all shared gates pass."""

    bridge = task_plan_bridge if isinstance(task_plan_bridge, Mapping) else {}
    binding = execution_binding if isinstance(execution_binding, Mapping) else {}
    if bridge.get("state") != "accepted":
        return _unavailable(
            str(bridge.get("reason_code") or "taskplan_bridge_not_accepted")
        )
    try:
        validated = validate_execution_binding(binding)
    except ExecutionBindingError as exc:
        return _unavailable(exc.code)
    bridge_components = _component_ids(bridge.get("components"))
    binding_components = _component_ids(validated.get("components"))
    if bridge_components != binding_components:
        return _unavailable("canonical_plan_component_mismatch")
    component_count = len(binding_components)
    return {
        "schema_version": CANONICAL_PLAN_RECEIPT_SCHEMA_VERSION,
        "state": "executable",
        "reason_code": "canonical_plan_validated",
        "executable": True,
        "component_count": component_count,
        "materialized_count": _bounded_count(bridge.get("materialized_count"), component_count),
        "component_ids": binding_components,
        "request_fingerprint": _text(validated.get("request_fingerprint"), 128),
        "binding_fingerprint": _text(validated.get("binding_fingerprint"), 128),
    }


def project_canonical_plan_receipt(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a bounded, idempotent transport projection."""

    raw = value if isinstance(value, Mapping) else {}
    state = str(raw.get("state") or "unavailable").strip().lower()
    if state not in {"executable", "deferred", "unavailable"}:
        state = "unavailable"
    component_ids = _component_ids(raw.get("component_ids"))
    executable = state == "executable" and raw.get("executable") is True
    return {
        "schema_version": CANONICAL_PLAN_RECEIPT_SCHEMA_VERSION,
        "state": state,
        "reason_code": _text(raw.get("reason_code"), 96) or "canonical_plan_unavailable",
        "executable": executable,
        "component_count": _bounded_count(raw.get("component_count"), _MAX_COMPONENTS),
        "materialized_count": _bounded_count(raw.get("materialized_count"), _MAX_COMPONENTS),
        "component_ids": component_ids,
        "request_fingerprint": _text(raw.get("request_fingerprint"), 128) or None,
        "binding_fingerprint": _text(raw.get("binding_fingerprint"), 128) or None,
    }


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": CANONICAL_PLAN_RECEIPT_SCHEMA_VERSION,
        "state": "unavailable",
        "reason_code": _text(reason_code, 96) or "canonical_plan_unavailable",
        "executable": False,
        "component_count": 0,
        "materialized_count": 0,
        "component_ids": [],
        "request_fingerprint": None,
        "binding_fingerprint": None,
    }


def _component_ids(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value[:_MAX_COMPONENTS]:
            raw = item.get("component_id") if isinstance(item, Mapping) else item
            component_id = _text(raw, 48)
            if component_id and component_id not in result:
                result.append(component_id)
    return result


def _bounded_count(value: Any, maximum: int) -> int:
    try:
        return max(0, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = [
    "CANONICAL_PLAN_RECEIPT_SCHEMA_VERSION",
    "build_canonical_plan_receipt",
    "project_canonical_plan_receipt",
]
