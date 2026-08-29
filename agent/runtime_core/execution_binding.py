"""Validated execution input for composed Domain runs.

The Composite planner is allowed to choose components, but execution must
consume the exact TaskPlan that crossed the capability, schema and DAG gates.
This module owns that seam.  The internal binding keeps the bounded plan
arguments needed by an executor; transport, artifact and evidence consumers
receive only the structural projection returned by :func:`project_execution_binding`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.application.composite_contract import normalize_composite_request
from agent.models import TaskPlan
from agent.plan_schema import PlanningError, parse_task_plan
from agent.runtime_core.planning import validate_plan
from agent.runtime_core.projection import plan_dag, plan_to_dict
from agent.runtime_core.composition import (
    CompositionError,
    normalize_component_inputs,
    project_component_inputs,
)


EXECUTION_BINDING_SCHEMA_VERSION = "spatial-agent.execution-binding.v1"
_MAX_COMPONENTS = 8
_MAX_STEPS = 12
_MAX_TOOLS = 24
_MAX_RESULT_TYPES = 24
_MAX_BINDING_BYTES = 256_000


class ExecutionBindingError(ValueError):
    """A planned execution input cannot cross the coordinator boundary."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "execution_binding_invalid",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = str(code)[:96]
        self.details = dict(details) if isinstance(details, Mapping) else {}
        super().__init__(message)


def build_execution_binding(
    request: Mapping[str, Any],
    components: Sequence[Mapping[str, Any]],
    *,
    task_plan_bridge: Mapping[str, Any],
    planner_name: str,
    backend: str,
) -> dict[str, Any]:
    """Build and validate a binding from already accepted component plans."""

    normalized = normalize_composite_request(request, allow_legacy=True)
    if not isinstance(components, (list, tuple)) or not components:
        raise ExecutionBindingError(
            "execution binding requires planned components",
            code="execution_binding_components_missing",
        )
    if not isinstance(task_plan_bridge, Mapping) or task_plan_bridge.get("state") != "accepted":
        raise ExecutionBindingError(
            "execution binding requires an accepted TaskPlan bridge",
            code="execution_binding_plan_not_accepted",
        )

    source_by_id = {
        str(item.get("component_id") or ""): item
        for item in components
        if isinstance(item, Mapping) and str(item.get("component_id") or "")
    }
    bridge_by_id = {
        str(item.get("component_id") or ""): item
        for item in (task_plan_bridge.get("components") or [])
        if isinstance(item, Mapping) and str(item.get("component_id") or "")
    }
    if set(source_by_id) != set(bridge_by_id):
        raise ExecutionBindingError(
            "planned components and TaskPlan bridge do not match",
            code="execution_binding_component_mismatch",
        )

    request_components = {
        item["component_id"]: item for item in normalized["components"]
    }
    bound_components: list[dict[str, Any]] = []
    for component_id in [item["component_id"] for item in normalized["components"]]:
        source = source_by_id.get(component_id)
        bridge = bridge_by_id.get(component_id)
        spec = request_components.get(component_id)
        plan = bridge.get("_validated_task_plan") if isinstance(bridge, Mapping) else None
        if not isinstance(source, Mapping) or not isinstance(bridge, Mapping) or not isinstance(spec, Mapping):
            raise ExecutionBindingError(
                "execution binding component is incomplete",
                code="execution_binding_component_invalid",
            )
        if not isinstance(plan, TaskPlan):
            raise ExecutionBindingError(
                "execution binding is missing the validated TaskPlan",
                code="execution_binding_plan_missing",
            )
        policy = bridge.get("policy")
        if not isinstance(policy, Mapping):
            raise ExecutionBindingError(
                "execution binding policy is missing",
                code="execution_binding_policy_missing",
            )
        workflow = bridge.get("_execution_workflow")
        workflow = _bounded_json_value(workflow) if isinstance(workflow, Mapping) else {}
        plan_payload = plan_to_dict(plan)
        capability_id = str(source.get("capability_id") or "")[:96]
        plan_fingerprint = _fingerprint(
            {
                "component_id": component_id,
                "domain_id": spec["domain_id"],
                "workflow": workflow,
                "plan": plan_payload,
                **({"capability_id": capability_id} if capability_id else {}),
            }
        )
        bound_components.append(
            {
                "component_id": component_id,
                "domain_id": str(spec["domain_id"])[:32],
                "capability_id": capability_id or None,
                "request": str(spec["request"])[:2000],
                "planner": str(spec.get("planner") or planner_name)[:32],
                "backend": str(spec.get("backend") or backend)[:32],
                "session_id": str(spec.get("session_id") or "")[:160] or None,
                "required": bool(spec.get("required", True)),
                "depends_on": [str(item)[:48] for item in (spec.get("depends_on") or [])[:_MAX_COMPONENTS]],
                "inputs": project_component_inputs(spec.get("inputs")),
                "workflow": workflow,
                "plan": plan_payload,
                "dag": plan_dag(plan),
                "policy": {
                    "allowed_tools": _strings(policy.get("allowed_tools"), _MAX_TOOLS),
                    "result_types": _strings(policy.get("result_types"), _MAX_RESULT_TYPES),
                    "max_steps": _bounded_int(policy.get("max_steps"), 1, _MAX_STEPS),
                },
                "plan_fingerprint": plan_fingerprint,
            }
        )

    binding: dict[str, Any] = {
        "schema_version": EXECUTION_BINDING_SCHEMA_VERSION,
        "state": "validated",
        "request_fingerprint": str(normalized["fingerprint"])[:128],
        "planner": str(planner_name or "rule")[:32],
        "backend": str(backend or "memory")[:32],
        "component_ids": [item["component_id"] for item in bound_components],
        "components": bound_components,
    }
    binding["binding_fingerprint"] = _binding_fingerprint(binding)
    return validate_execution_binding(binding, request=normalized)


def validate_execution_binding(
    value: Any,
    *,
    request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate binding identity, plans, tools, DAG and result contracts."""

    if not isinstance(value, Mapping):
        raise ExecutionBindingError(
            "execution binding is required",
            code="execution_binding_required",
        )
    if str(value.get("schema_version") or "") != EXECUTION_BINDING_SCHEMA_VERSION:
        raise ExecutionBindingError(
            "unknown execution binding schema version",
            code="execution_binding_schema_unknown",
        )
    if str(value.get("state") or "") != "validated":
        raise ExecutionBindingError(
            "execution binding is not validated",
            code="execution_binding_state_invalid",
        )
    normalized_request = None
    if request is not None:
        normalized_request = normalize_composite_request(request, allow_legacy=True)
        if str(value.get("request_fingerprint") or "") != str(normalized_request["fingerprint"]):
            raise ExecutionBindingError(
                "execution binding request fingerprint does not match",
                code="execution_binding_request_mismatch",
            )
    raw_components = value.get("components")
    if not isinstance(raw_components, list) or not raw_components or len(raw_components) > _MAX_COMPONENTS:
        raise ExecutionBindingError(
            "execution binding components are invalid",
            code="execution_binding_components_invalid",
        )
    component_ids = [str(item.get("component_id") or "") for item in raw_components if isinstance(item, Mapping)]
    if len(component_ids) != len(raw_components) or len(set(component_ids)) != len(component_ids):
        raise ExecutionBindingError(
            "execution binding component ids are invalid",
            code="execution_binding_component_mismatch",
        )
    declared_ids = [str(item) for item in (value.get("component_ids") or [])]
    if declared_ids != component_ids:
        raise ExecutionBindingError(
            "execution binding component set does not match",
            code="execution_binding_component_mismatch",
        )

    canonical_components: list[dict[str, Any]] = []
    for raw in raw_components:
        if not isinstance(raw, Mapping):
            raise ExecutionBindingError(
                "execution binding component is invalid",
                code="execution_binding_component_invalid",
            )
        component = _validate_component(raw)
        if normalized_request is not None:
            expected = next(
                (
                    item
                    for item in normalized_request.get("components") or []
                    if isinstance(item, Mapping)
                    and str(item.get("component_id") or "")
                    == str(component.get("component_id") or "")
                ),
                None,
            )
            if not isinstance(expected, Mapping):
                raise ExecutionBindingError(
                    "execution binding component is not present in the request",
                    code="execution_binding_component_mismatch",
                )
            if list(component.get("depends_on") or []) != list(
                expected.get("depends_on") or []
            ) or project_component_inputs(component.get("inputs")) != project_component_inputs(
                expected.get("inputs")
            ):
                raise ExecutionBindingError(
                    "execution binding component dependencies or inputs do not match the request",
                    code="execution_binding_component_mismatch",
                )
        canonical_components.append(component)

    canonical = {
        "schema_version": EXECUTION_BINDING_SCHEMA_VERSION,
        "state": "validated",
        "request_fingerprint": str(value.get("request_fingerprint") or "")[:128],
        "planner": str(value.get("planner") or "rule")[:32],
        "backend": str(value.get("backend") or "memory")[:32],
        "component_ids": component_ids,
        "components": canonical_components,
    }
    expected = _binding_fingerprint(canonical)
    actual = str(value.get("binding_fingerprint") or "")
    if actual != expected:
        raise ExecutionBindingError(
            "execution binding fingerprint does not match its contents",
            code="execution_binding_fingerprint_mismatch",
        )
    canonical["binding_fingerprint"] = actual
    encoded = _json_bytes(canonical)
    if len(encoded) > _MAX_BINDING_BYTES:
        raise ExecutionBindingError(
            "execution binding exceeds max_bytes",
            code="execution_binding_too_large",
        )
    return canonical


def task_plan_from_binding(component: Mapping[str, Any]) -> TaskPlan:
    """Parse one validated binding component into the Runtime plan object."""

    if not isinstance(component, Mapping):
        raise ExecutionBindingError(
            "execution binding component is invalid",
            code="execution_binding_component_invalid",
        )
    policy = component.get("policy") if isinstance(component.get("policy"), Mapping) else {}
    try:
        return parse_task_plan(component.get("plan"), policy.get("allowed_tools") or [])
    except (PlanningError, TypeError, ValueError) as exc:
        raise ExecutionBindingError(
            "execution binding TaskPlan cannot be parsed",
            code="execution_binding_plan_invalid",
        ) from exc


def project_execution_binding(value: Any) -> dict[str, Any]:
    """Return a transport/artifact-safe structural binding projection."""

    if _looks_like_projection(value):
        return _project_existing_projection(value)
    try:
        binding = validate_execution_binding(value)
    except ExecutionBindingError as exc:
        return {
            "schema_version": EXECUTION_BINDING_SCHEMA_VERSION,
            "state": "unavailable",
            "reason_code": exc.code,
            "binding_fingerprint": None,
            "request_fingerprint": None,
            "component_ids": [],
            "components": [],
        }
    return {
        "schema_version": EXECUTION_BINDING_SCHEMA_VERSION,
        "state": "validated",
        "binding_fingerprint": binding["binding_fingerprint"],
        "request_fingerprint": binding["request_fingerprint"],
        "planner": binding["planner"],
        "backend": binding["backend"],
        "component_ids": list(binding["component_ids"]),
        "components": [_project_component(item) for item in binding["components"]],
    }


def _looks_like_projection(value: Any) -> bool:
    if not isinstance(value, Mapping) or str(value.get("state") or "") != "validated":
        return False
    components = value.get("components")
    return isinstance(components, list) and bool(components) and all(
        isinstance(item, Mapping) and "plan" not in item and "steps" in item
        for item in components
    )


def _project_existing_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    components = []
    for raw in (value.get("components") or [])[:_MAX_COMPONENTS]:
        if not isinstance(raw, Mapping):
            continue
        components.append(
            {
                "component_id": str(raw.get("component_id") or "")[:48],
                "domain_id": str(raw.get("domain_id") or "")[:32],
                "required": bool(raw.get("required", True)),
                "depends_on": [str(item)[:48] for item in (raw.get("depends_on") or [])[:_MAX_COMPONENTS]],
                "plan_fingerprint": str(raw.get("plan_fingerprint") or "")[:128],
                "result_type": str(raw.get("result_type") or "")[:96],
                "step_count": _bounded_int(raw.get("step_count"), 0, _MAX_STEPS),
                "steps": [
                    {
                        "id": str(item.get("id") or "")[:48],
                        "tool": str(item.get("tool") or "")[:96],
                        "depends_on": [str(dep)[:48] for dep in (item.get("depends_on") or [])[:_MAX_STEPS]],
                        "arg_keys": [str(key)[:96] for key in (item.get("arg_keys") or [])[:32]],
                    }
                    for item in (raw.get("steps") or [])[:_MAX_STEPS]
                    if isinstance(item, Mapping)
                ],
                "policy": {
                    "allowed_tools": _strings((raw.get("policy") or {}).get("allowed_tools"), _MAX_TOOLS),
                    "result_types": _strings((raw.get("policy") or {}).get("result_types"), _MAX_RESULT_TYPES),
                    "max_steps": _bounded_int((raw.get("policy") or {}).get("max_steps"), 1, _MAX_STEPS),
                },
            }
        )
    return {
        "schema_version": EXECUTION_BINDING_SCHEMA_VERSION,
        "state": "validated",
        "binding_fingerprint": str(value.get("binding_fingerprint") or "")[:128] or None,
        "request_fingerprint": str(value.get("request_fingerprint") or "")[:128] or None,
        "planner": str(value.get("planner") or "rule")[:32],
        "backend": str(value.get("backend") or "memory")[:32],
        "component_ids": [str(item)[:48] for item in (value.get("component_ids") or [])[:_MAX_COMPONENTS]],
        "components": components,
    }


def component_binding(value: Mapping[str, Any], component_id: str) -> Mapping[str, Any]:
    """Find one component after the caller has validated the binding."""

    for item in value.get("components") or []:
        if isinstance(item, Mapping) and str(item.get("component_id") or "") == str(component_id):
            return item
    raise ExecutionBindingError(
        "execution binding component is unavailable",
        code="execution_binding_component_mismatch",
    )


def validate_component_result(component: Mapping[str, Any], child: Mapping[str, Any]) -> None:
    """Reject a completed child whose declared Result type drifted."""

    nested = child.get("result") if isinstance(child.get("result"), Mapping) else child
    actual = str((nested or {}).get("type") or child.get("result_type") or "")
    expected = str((component.get("plan") or {}).get("output", {}).get("type") or "")
    if str(child.get("status") or "").upper() == "COMPLETED" and actual != expected:
        raise ExecutionBindingError(
            "component result type does not match the validated plan",
            code="execution_binding_result_type_mismatch",
        )


def _validate_component(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = ("component_id", "domain_id", "plan", "dag", "policy", "plan_fingerprint")
    if any(not raw.get(key) for key in required):
        raise ExecutionBindingError(
            "execution binding component is incomplete",
            code="execution_binding_component_invalid",
        )
    policy = raw.get("policy")
    if not isinstance(policy, Mapping):
        raise ExecutionBindingError("execution binding policy is invalid", code="execution_binding_policy_invalid")
    allowed_tools = _strings(policy.get("allowed_tools"), _MAX_TOOLS)
    result_types = _strings(policy.get("result_types"), _MAX_RESULT_TYPES)
    max_steps = _bounded_int(policy.get("max_steps"), 1, _MAX_STEPS)
    plan_payload = raw.get("plan")
    if not isinstance(plan_payload, Mapping):
        raise ExecutionBindingError("execution binding plan is invalid", code="execution_binding_plan_invalid")
    try:
        plan = parse_task_plan(plan_payload, allowed_tools)
        validate_plan(plan, allowed_tools, max_steps)
    except (PlanningError, ValueError, TypeError) as exc:
        text = str(exc).lower()
        code = "execution_binding_tool_not_allowlisted" if "unknown tool" in text else "execution_binding_plan_invalid"
        raise ExecutionBindingError("execution binding plan failed validation", code=code) from exc
    result_type = str(plan.output.get("type") or "")
    if result_type not in result_types:
        raise ExecutionBindingError(
            "execution binding result type is not allowlisted",
            code="execution_binding_result_type_not_allowlisted",
        )
    try:
        inputs = normalize_component_inputs(raw.get("inputs"))
    except CompositionError as exc:
        raise ExecutionBindingError(
            "execution binding component inputs are invalid",
            code=exc.code,
        ) from exc
    workflow = _bounded_json_value(raw.get("workflow") or {})
    canonical = {
        "component_id": str(raw.get("component_id"))[:48],
        "domain_id": str(raw.get("domain_id"))[:32],
        "request": str(raw.get("request") or "")[:2000],
        "planner": str(raw.get("planner") or "rule")[:32],
        "backend": str(raw.get("backend") or "memory")[:32],
        "session_id": str(raw.get("session_id") or "")[:160] or None,
        "required": bool(raw.get("required", True)),
        "depends_on": [str(item)[:48] for item in (raw.get("depends_on") or [])[:_MAX_COMPONENTS]],
        "inputs": inputs,
        "workflow": workflow,
        "plan": plan_to_dict(plan),
        "dag": plan_dag(plan),
        "policy": {
            "allowed_tools": allowed_tools,
            "result_types": result_types,
            "max_steps": max_steps,
        },
    }
    capability_id = str(raw.get("capability_id") or "")[:96]
    if capability_id:
        canonical["capability_id"] = capability_id
    expected_plan_fingerprint = _fingerprint(
        {
            "component_id": canonical["component_id"],
            "domain_id": canonical["domain_id"],
            "workflow": workflow,
            "plan": canonical["plan"],
            **({"capability_id": capability_id} if capability_id else {}),
        }
    )
    if str(raw.get("plan_fingerprint")) != expected_plan_fingerprint:
        raise ExecutionBindingError(
            "execution binding plan fingerprint does not match",
            code="execution_binding_plan_fingerprint_mismatch",
        )
    canonical["plan_fingerprint"] = expected_plan_fingerprint
    return canonical


def _project_component(value: Mapping[str, Any]) -> dict[str, Any]:
    plan = value.get("plan") if isinstance(value.get("plan"), Mapping) else {}
    steps = [item for item in (plan.get("steps") or []) if isinstance(item, Mapping)]
    return {
        "component_id": str(value.get("component_id") or "")[:48],
        "domain_id": str(value.get("domain_id") or "")[:32],
        "capability_id": str(value.get("capability_id") or "")[:96] or None,
        "required": bool(value.get("required", True)),
        "depends_on": [str(item)[:48] for item in (value.get("depends_on") or [])[:_MAX_COMPONENTS]],
        "inputs": project_component_inputs(value.get("inputs")),
        "plan_fingerprint": str(value.get("plan_fingerprint") or "")[:128],
        "result_type": str((plan.get("output") or {}).get("type") or "")[:96],
        "step_count": len(steps),
        "steps": [
            {
                "id": str(item.get("id") or "")[:48],
                "tool": str(item.get("tool") or "")[:96],
                "depends_on": [str(dep)[:48] for dep in (item.get("depends_on") or [])[:_MAX_STEPS]],
                "arg_keys": sorted(str(key)[:96] for key in (item.get("args") or {}))[:32],
            }
            for item in steps[:_MAX_STEPS]
        ],
        "policy": {
            "allowed_tools": _strings((value.get("policy") or {}).get("allowed_tools"), _MAX_TOOLS),
            "result_types": _strings((value.get("policy") or {}).get("result_types"), _MAX_RESULT_TYPES),
            "max_steps": _bounded_int((value.get("policy") or {}).get("max_steps"), 1, _MAX_STEPS),
        },
    }


def _binding_fingerprint(value: Mapping[str, Any]) -> str:
    body = {
        key: value.get(key)
        for key in ("schema_version", "state", "request_fingerprint", "planner", "backend", "component_ids", "components")
    }
    return _fingerprint(body)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json_bytes(value)).hexdigest()


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExecutionBindingError("execution binding is not JSON serializable", code="execution_binding_not_serializable") from exc


def _bounded_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        raise ExecutionBindingError("execution binding workflow is too deep", code="execution_binding_workflow_invalid")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value if not isinstance(value, str) else value[:2000]
    if isinstance(value, Mapping):
        return {str(key)[:96]: _bounded_json_value(item, depth=depth + 1) for key, item in list(value.items())[:64]}
    if isinstance(value, (list, tuple)):
        return [_bounded_json_value(item, depth=depth + 1) for item in list(value)[:64]]
    raise ExecutionBindingError("execution binding contains a non-JSON value", code="execution_binding_not_serializable")


def _strings(value: Any, limit: int) -> list[str]:
    result: list[str] = []
    values = value if isinstance(value, (list, tuple, set)) else []
    for item in values:
        text = str(item or "").strip()[:96]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return minimum


__all__ = [
    "EXECUTION_BINDING_SCHEMA_VERSION",
    "ExecutionBindingError",
    "build_execution_binding",
    "component_binding",
    "project_execution_binding",
    "task_plan_from_binding",
    "validate_component_result",
    "validate_execution_binding",
]
