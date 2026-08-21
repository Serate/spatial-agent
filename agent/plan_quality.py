"""Bounded workflow-aware TaskPlan quality diagnostics.

This module is a read-only seam between workflow template context and Planner
repair.  It never edits or silently normalizes a plan.  When a result type
identifies exactly one templated workflow, it compares the candidate's ordered
step signatures with that workflow's blueprint and returns safe issue codes
that a Planner can use for one bounded repair attempt.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import TaskPlan


PLAN_QUALITY_SCHEMA_VERSION = "spatial-agent.plan-quality.v1"
PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION = "spatial-agent.plan-quality-evidence.v1"
_MAX_ITEMS = 16
_MAX_TEXT = 96


def diagnose_plan(
    plan: TaskPlan | Mapping[str, Any] | None,
    workflow_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare a plan with a uniquely identifiable workflow blueprint.

    If the context has no unique blueprint for the plan's result type, the
    diagnostic is unavailable rather than inventing a workflow restriction.
    This keeps open-ended capabilities extensible while making existing
    declared templates actionable during repair.
    """

    output = _mapping(plan.output if isinstance(plan, TaskPlan) else _mapping(plan).get("output"))
    result_type = _text(output.get("type"))
    templates = _templates(workflow_context)
    candidates = [
        item
        for item in templates
        if result_type in _result_types(item) and isinstance(item.get("step_blueprint"), list)
    ]
    if len(candidates) != 1 or not result_type:
        return {
            "schema_version": PLAN_QUALITY_SCHEMA_VERSION,
            "available": False,
            "passed": True,
            "reason_code": "workflow_blueprint_unavailable",
            "result_type": result_type or None,
            "candidate_template_ids": [_text(item.get("id")) for item in candidates[:_MAX_ITEMS]],
            "issues": [],
        }

    template = candidates[0]
    actual_steps = _steps(plan)
    expected_steps = template.get("step_blueprint")[:_MAX_ITEMS]
    issues: list[dict[str, Any]] = []
    if len(actual_steps) != len(expected_steps):
        issues.append(
            {
                "code": "template_step_count",
                "expected": len(expected_steps),
                "actual": len(actual_steps),
            }
        )
    for index, expected in enumerate(expected_steps[:_MAX_ITEMS]):
        actual = actual_steps[index] if index < len(actual_steps) else None
        if not isinstance(actual, Mapping):
            continue
        expected_id = _text(expected.get("id"))
        actual_id = _text(actual.get("id"))
        if expected_id != actual_id:
            issues.append(_issue("template_step_id", index, expected_id, actual_id))
        expected_tool = _text(expected.get("tool"))
        actual_tool = _text(actual.get("tool"))
        if expected_tool != actual_tool:
            issues.append(_issue("template_step_tool", index, expected_tool, actual_tool))
        expected_args = _arg_keys(expected.get("arg_keys"), expected.get("args"))
        actual_args = _arg_keys(None, actual.get("args"))
        if expected_args and expected_args != actual_args:
            issues.append(_issue("template_step_args", index, expected_args, actual_args))
        expected_deps = _string_list(expected.get("depends_on"))
        actual_deps = _string_list(actual.get("depends_on"))
        if expected_deps != actual_deps:
            issues.append(_issue("template_step_dependency", index, expected_deps, actual_deps))

    return {
        "schema_version": PLAN_QUALITY_SCHEMA_VERSION,
        "available": True,
        "passed": not issues,
        "reason_code": "ok" if not issues else "workflow_blueprint_mismatch",
        "template_id": _text(template.get("id")) or None,
        "result_type": result_type,
        "expected_step_count": len(expected_steps),
        "actual_step_count": len(actual_steps),
        "expected_steps": [_step_signature(item) for item in expected_steps],
        "actual_steps": [_step_signature(item) for item in actual_steps[:_MAX_ITEMS]],
        "issues": issues[:_MAX_ITEMS],
    }


def repair_context(diagnostic: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a small, explicit Planner instruction from a diagnostic."""

    value = diagnostic if isinstance(diagnostic, Mapping) else {}
    if not value.get("available"):
        return {
            "schema_version": PLAN_QUALITY_SCHEMA_VERSION,
            "available": False,
            "instruction": "没有唯一 workflow blueprint；只修复明确的校验错误，不猜测模板。",
        }
    issues = value.get("issues") if isinstance(value.get("issues"), list) else []
    return {
        "schema_version": PLAN_QUALITY_SCHEMA_VERSION,
        "available": True,
        "template_id": _text(value.get("template_id"))[:_MAX_TEXT],
        "result_type": _text(value.get("result_type"))[:_MAX_TEXT],
        "expected_step_count": _bounded_int(value.get("expected_step_count"), 0, _MAX_ITEMS),
        "expected_steps": list(value.get("expected_steps") or [])[:_MAX_ITEMS],
        "issues": list(issues)[:_MAX_ITEMS],
        "instruction": (
            "按该 workflow blueprint 输出完整 TaskPlan：保持步骤数量、顺序、id、tool、参数键和依赖；"
            "不要重复已有步骤，不要静默删除未确认的用户约束。"
        ),
    }


def project_plan_quality_evidence(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project plan quality into one bounded cross-entry evidence shape.

    ``diagnose_plan`` is an internal diagnostic and may be absent on legacy
    artifacts or open-ended plans.  This projection deliberately distinguishes
    an unavailable unique blueprint from a failed blueprint match; callers can
    therefore compare replay, HTTP, artifact and Console evidence without
    inventing a template for an extensible capability.
    """

    source = value if isinstance(value, Mapping) else {}
    available = bool(source.get("available"))
    passed = bool(source.get("passed")) if available else True
    reason = _text(source.get("reason_code")) or (
        "ok" if available and passed else "workflow_blueprint_unavailable"
    )
    state = "passed" if available and passed else "mismatch" if available else "unavailable"
    result: dict[str, Any] = {
        "schema_version": PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION,
        "available": available,
        "state": state,
        "passed": passed,
        "reason_code": reason,
        "template_id": _text(source.get("template_id")) or None,
        "result_type": _text(source.get("result_type")) or None,
        "candidate_template_ids": _string_list(source.get("candidate_template_ids"))[:_MAX_ITEMS],
        "expected_step_count": _bounded_int(source.get("expected_step_count"), 0, _MAX_ITEMS),
        "actual_step_count": _bounded_int(source.get("actual_step_count"), 0, _MAX_ITEMS),
        "issues": [],
    }
    issues = source.get("issues")
    if isinstance(issues, list):
        result["issues"] = [
            _bound_quality_item(item)
            for item in issues[:_MAX_ITEMS]
            if isinstance(item, Mapping)
        ]
    return result


def _bound_quality_item(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("code", "index", "expected", "actual"):
        if key not in value:
            continue
        item = value[key]
        if isinstance(item, list):
            result[key] = [str(entry)[:_MAX_TEXT] for entry in item[:_MAX_ITEMS]]
        elif isinstance(item, Mapping):
            result[key] = {
                str(name)[:_MAX_TEXT]: str(entry)[:_MAX_TEXT]
                for name, entry in list(item.items())[:_MAX_ITEMS]
            }
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item if not isinstance(item, str) else item[:_MAX_TEXT]
    return result


def _templates(context: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    source = context if isinstance(context, Mapping) else {}
    if isinstance(source.get("workflow_templates"), Mapping):
        source = source["workflow_templates"]
    values = source.get("templates") if isinstance(source, Mapping) else None
    return [item for item in (values if isinstance(values, list) else []) if isinstance(item, Mapping)]


def _steps(plan: TaskPlan | Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if isinstance(plan, TaskPlan):
        return [
            {
                "id": item.id,
                "tool": item.tool,
                "args": dict(item.args),
                "depends_on": list(item.depends_on),
            }
            for item in plan.steps
        ]
    raw = _mapping(plan).get("steps")
    return [item for item in (raw if isinstance(raw, list) else []) if isinstance(item, Mapping)]


def _step_signature(value: Mapping[str, Any]) -> dict[str, Any]:
    args = _arg_keys(value.get("arg_keys"), value.get("args"))
    return {
        "id": _text(value.get("id"))[:_MAX_TEXT],
        "tool": _text(value.get("tool"))[:_MAX_TEXT],
        "arg_keys": args[:_MAX_ITEMS],
        "depends_on": _string_list(value.get("depends_on"))[:_MAX_ITEMS],
    }


def _issue(code: str, index: int, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "code": code,
        "index": index,
        "expected": expected,
        "actual": actual,
    }


def _result_types(template: Mapping[str, Any]) -> list[str]:
    values = template.get("result_types")
    if not isinstance(values, list):
        values = [template.get("output_type")]
    return [_text(item) for item in values if _text(item)]


def _arg_keys(explicit: Any, args: Any) -> list[str]:
    if isinstance(explicit, list):
        return sorted({_text(item) for item in explicit if _text(item)})
    if isinstance(args, Mapping):
        return sorted(str(key)[:_MAX_TEXT] for key in args)
    return []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item)[:_MAX_TEXT] for item in value if _text(item)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


__all__ = [
    "PLAN_QUALITY_SCHEMA_VERSION",
    "PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION",
    "diagnose_plan",
    "project_plan_quality_evidence",
    "repair_context",
]
