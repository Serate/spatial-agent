"""Versioned evidence for the policy that accepted or rejected a TaskPlan.

The Runtime owns the decision lifecycle and generic TaskPlan validation.  A
Domain Pack may describe an additional policy (for example a bounded workflow
allowlist), but it must not leak its implementation into this module.  This
small module is the public projection seam: result, artifact, async recovery,
the Contract Harness and the Console can all consume the same bounded shape.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import TaskPlan


PLAN_POLICY_SCHEMA_VERSION = "spatial-agent.plan-policy.v1"
PLAN_POLICY_STATES = {"accepted", "rejected", "clarification", "unavailable"}
PLAN_POLICY_SOURCES = {
    "explicit_workflow",
    "domain_auto_match",
    "domain_catalog",
    "none",
}
_MAX_ITEMS = 24
_MAX_TEXT = 96


def build_plan_policy_evidence(
    plan: TaskPlan | None,
    *,
    domain_policy: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
    domain_id: str = "unknown",
    state: str = "accepted",
    reason_code: str | None = None,
    repair_lineage: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a bounded, credential-free plan policy projection.

    ``domain_policy`` is descriptive metadata supplied by a Domain Pack.  It
    never replaces Runtime validation, and an absent policy is a valid state
    for an extensible Domain.  ``state`` describes the Runtime outcome, not a
    Domain-specific implementation detail.
    """

    policy = _mapping(domain_policy)
    normalized_state = _text(state) if state in PLAN_POLICY_STATES else "unavailable"
    explicit_template = _text(_mapping(workflow).get("template_id"))
    policy_template = _text(policy.get("workflow_template_id"))
    template_id = explicit_template or policy_template or None
    template_version = _text(
        _mapping(workflow).get("template_version")
        or policy.get("workflow_template_version")
    )
    source = _text(policy.get("source")) or (
        "explicit_workflow" if explicit_template else "none"
    )
    if source not in PLAN_POLICY_SOURCES:
        source = "none"
    available = bool(policy.get("available", bool(policy))) and bool(
        policy.get("policy_id") or policy.get("allowed_tools") or template_id
    )
    if not available:
        source = "none" if source == "explicit_workflow" and not policy else source

    tools = _string_list(policy.get("allowed_tools"))
    result_types = _string_list(policy.get("result_types"))
    candidate_policy_ids = _string_list(policy.get("candidate_policy_ids"))
    actual_tools = []
    step_count = 0
    if isinstance(plan, TaskPlan):
        step_count = len(plan.steps)
        actual_tools = _unique([step.tool for step in plan.steps])
    elif isinstance(plan, Mapping):
        raw_steps = plan.get("steps")
        if isinstance(raw_steps, list):
            step_count = len(raw_steps[:_MAX_ITEMS])
            actual_tools = _unique(
                [
                    _text(item.get("tool"))
                    for item in raw_steps[:_MAX_ITEMS]
                    if isinstance(item, Mapping) and _text(item.get("tool"))
                ]
            )

    accepted = normalized_state == "accepted"
    if reason_code is None:
        reason_code = "accepted" if accepted else {
            "rejected": "plan_policy_rejected",
            "clarification": "clarification_required",
            "unavailable": "domain_policy_unavailable",
        }.get(normalized_state, "plan_policy_unavailable")
    result: dict[str, Any] = {
        "schema_version": PLAN_POLICY_SCHEMA_VERSION,
        "available": available,
        "state": normalized_state,
        "accepted": accepted,
        "reason_code": _text(reason_code),
        "domain_id": _text(domain_id) or "unknown",
        "policy_id": _text(policy.get("policy_id")) or None,
        "source": source,
        "selected_by": _text(policy.get("selected_by")) or (
            "user" if explicit_template else "domain" if available else "none"
        ),
        "workflow_template_id": template_id,
        "workflow_template_version": template_version or None,
        "allowed_tools": tools,
        "max_steps": _bounded_int(policy.get("max_steps"), 0, 128),
        "result_types": result_types,
        "candidate_policy_ids": candidate_policy_ids,
        "step_count": max(0, min(step_count, 128)),
        "actual_tools": actual_tools,
        "repair_lineage": project_repair_lineage(repair_lineage),
    }
    if policy.get("required_constraints") is not None:
        result["required_constraints"] = _string_list(policy.get("required_constraints"))
    return result


def normalize_plan_policy_evidence(value: Any) -> dict[str, Any]:
    """Safely normalize persisted plan-policy evidence for old/new entries."""

    if not isinstance(value, Mapping):
        return build_plan_policy_evidence(
            None,
            domain_id="unknown",
            state="unavailable",
            reason_code="plan_policy_missing",
        )
    if value.get("schema_version") != PLAN_POLICY_SCHEMA_VERSION:
        return build_plan_policy_evidence(
            None,
            domain_id=_text(value.get("domain_id")) or "unknown",
            state="unavailable",
            reason_code="plan_policy_unknown_schema",
        )
    state = _text(value.get("state"))
    if state not in PLAN_POLICY_STATES:
        state = "unavailable"
    source = _text(value.get("source"))
    if source not in PLAN_POLICY_SOURCES:
        source = "none"
    result = {
        "schema_version": PLAN_POLICY_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "state": state,
        "accepted": bool(value.get("accepted")) and state == "accepted",
        "reason_code": _text(value.get("reason_code")) or "plan_policy_unavailable",
        "domain_id": _text(value.get("domain_id")) or "unknown",
        "policy_id": _text(value.get("policy_id")) or None,
        "source": source,
        "selected_by": _text(value.get("selected_by")) or "none",
        "workflow_template_id": _text(value.get("workflow_template_id")) or None,
        "workflow_template_version": _text(value.get("workflow_template_version")) or None,
        "allowed_tools": _string_list(value.get("allowed_tools")),
        "max_steps": _bounded_int(value.get("max_steps"), 0, 128),
        "result_types": _string_list(value.get("result_types")),
        "candidate_policy_ids": _string_list(value.get("candidate_policy_ids")),
        "step_count": _bounded_int(value.get("step_count"), 0, 128),
        "actual_tools": _string_list(value.get("actual_tools")),
        "repair_lineage": project_repair_lineage(value.get("repair_lineage")),
    }
    if "required_constraints" in value:
        result["required_constraints"] = _string_list(value.get("required_constraints"))
    return result


def project_repair_lineage(value: Any) -> list[dict[str, Any]]:
    """Project replan events without volatile timing or raw error text."""

    events = value if isinstance(value, (list, tuple)) else []
    projected: list[dict[str, Any]] = []
    for event in events[:_MAX_ITEMS]:
        if not isinstance(event, Mapping):
            continue
        item: dict[str, Any] = {}
        for key in ("phase", "failed_step_id", "failed_tool", "failure_category"):
            text = _text(event.get(key))
            if text:
                item[key] = text
        ids = event.get("replanned_step_ids")
        if isinstance(ids, list):
            item["replanned_step_ids"] = _string_list(ids)
        for key in ("plan_quality_before", "plan_quality_after"):
            quality = event.get(key)
            if isinstance(quality, Mapping):
                item[key] = {
                    "schema_version": _text(quality.get("schema_version")),
                    "state": _text(quality.get("state")),
                    "reason_code": _text(quality.get("reason_code")),
                    "template_id": _text(quality.get("template_id")) or None,
                }
        if item:
            projected.append(item)
    return projected


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


def _string_list(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else []
    result: list[str] = []
    for item in values:
        text = _text(item)
        if text and text not in result:
            result.append(text)
    return result[:_MAX_ITEMS]


def _unique(values: list[str]) -> list[str]:
    return _string_list(values)


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(minimum, min(value, maximum))


__all__ = [
    "PLAN_POLICY_SCHEMA_VERSION",
    "PLAN_POLICY_SOURCES",
    "PLAN_POLICY_STATES",
    "build_plan_policy_evidence",
    "normalize_plan_policy_evidence",
    "project_repair_lineage",
]
