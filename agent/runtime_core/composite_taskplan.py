"""Domain-neutral bridge from Composite candidates to canonical TaskPlans.

The Composite planner chooses bounded capabilities and component requests.  A
component still needs to cross the same TaskPlan/DAG gates as a regular
Runtime request before it can create a run.  This module keeps that bridge
behind one small interface and returns only a safe structural projection;
planner arguments are never copied into evidence.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.models import TaskPlan
from agent.plan_schema import PlanningError, parse_task_plan
from agent.runtime_core.planning import validate_plan
from agent.runtime_core.projection import plan_dag


TASK_PLAN_BRIDGE_SCHEMA_VERSION = "spatial-agent.composite-taskplan-bridge.v1"
_MAX_COMPONENTS = 8
_MAX_STEPS = 12
_MAX_PLAN_BYTES = 64_000
_TASK_PLAN_FIELDS = {"goal", "steps", "output", "assumptions"}
_STEP_FIELDS = {"id", "tool", "args", "depends_on"}


class CompositeTaskPlanBridgeError(ValueError):
    """A Composite candidate cannot safely become an executable TaskPlan."""

    def __init__(self, message: str, *, code: str):
        self.code = str(code)[:96]
        super().__init__(message)


class CompositeTaskPlanBridge:
    """Materialize and validate component plans without choosing a Domain.

    Explicit replay plans live under ``component.workflow.task_plan``.  A
    production Domain service may alternatively expose ``preview()``; that
    planning-only seam supplies a TaskPlan for candidates that do not carry
    an explicit replay plan.  Neither path dispatches a tool.
    """

    def __init__(self, *, host: Any, max_steps: int = _MAX_STEPS) -> None:
        if host is None:
            raise ValueError("host is required")
        self._host = host
        self._max_steps = max(1, min(_MAX_STEPS, int(max_steps)))

    def bridge(
        self,
        components: Sequence[Mapping[str, Any]],
        *,
        context: Mapping[str, Any],
        planner: str,
        backend: str,
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Return bounded TaskPlan/DAG projections for all components."""

        if not isinstance(components, (list, tuple)):
            raise CompositeTaskPlanBridgeError(
                "planned components are invalid", code="taskplan_components_invalid"
            )
        projected: list[dict[str, Any]] = []
        materialized = 0
        deferred = 0
        for component in list(components)[:_MAX_COMPONENTS]:
            if not isinstance(component, Mapping):
                raise CompositeTaskPlanBridgeError(
                    "planned component is invalid", code="taskplan_component_invalid"
                )
            result = self._bridge_component(
                component,
                context=context,
                planner=planner,
                backend=backend,
                session_id=session_id,
            )
            projected.append(result)
            if result["state"] == "accepted":
                materialized += 1
            else:
                deferred += 1

        state = "accepted" if deferred == 0 else "deferred"
        return {
            "schema_version": TASK_PLAN_BRIDGE_SCHEMA_VERSION,
            "state": state,
            "reason_code": (
                "taskplans_materialized"
                if state == "accepted"
                else "taskplan_materialization_deferred"
            ),
            "component_count": len(projected),
            "materialized_count": materialized,
            "deferred_count": deferred,
            "components": projected,
        }

    def _bridge_component(
        self,
        component: Mapping[str, Any],
        *,
        context: Mapping[str, Any],
        planner: str,
        backend: str,
        session_id: str,
    ) -> dict[str, Any]:
        component_id = _bounded_text(component.get("component_id"), 48)
        domain_id = _bounded_text(component.get("domain_id"), 32)
        workflow = component.get("workflow")
        if workflow is not None and not isinstance(workflow, Mapping):
            raise CompositeTaskPlanBridgeError(
                "component workflow is invalid", code="taskplan_workflow_invalid"
            )

        plan_payload = _explicit_task_plan(workflow)
        source = "explicit_workflow"
        if plan_payload is None:
            plan_payload = self._preview_plan(
                component,
                workflow=workflow,
                planner=planner,
                backend=backend,
                session_id=session_id,
            )
            source = "domain_preview"
        if plan_payload is None:
            return {
                "component_id": component_id,
                "domain_id": domain_id,
                "state": "deferred",
                "reason_code": "taskplan_materialization_deferred",
            }

        capability = _capability(context, domain_id, component.get("capability_id"))
        if capability is None:
            raise CompositeTaskPlanBridgeError(
                "component capability is not registered",
                code="taskplan_capability_not_registered",
            )
        allowed_tools, result_types = _policy(
            context,
            domain_id=domain_id,
            capability=capability,
            workflow=workflow,
        )
        task_plan = _parse_and_validate(
            plan_payload,
            allowed_tools=allowed_tools,
            result_types=result_types,
            max_steps=self._max_steps,
        )
        return {
            "component_id": component_id,
            "domain_id": domain_id,
            "state": "accepted",
            "source": source,
            "plan": _project_plan(task_plan),
            "dag": plan_dag(task_plan),
            "policy": {
                "allowed_tools": allowed_tools[:24],
                "result_types": result_types[:24],
                "max_steps": self._max_steps,
            },
        }

    def _preview_plan(
        self,
        component: Mapping[str, Any],
        *,
        workflow: Mapping[str, Any] | None,
        planner: str,
        backend: str,
        session_id: str,
    ) -> Mapping[str, Any] | None:
        service_resolver = getattr(self._host, "service", None)
        selector = getattr(self._host, "select", None)
        if not callable(service_resolver) or not callable(selector):
            return None
        try:
            selection = selector(component.get("domain_id"), source="automatic")
            service = service_resolver(selection)
        except Exception:
            return None
        preview = getattr(service, "preview", None)
        if not callable(preview):
            return None
        kwargs: dict[str, Any] = {
            "session_id": _bounded_text(session_id, 120) or "default",
            "planner": _bounded_text(component.get("planner") or planner, 32),
            "backend": _bounded_text(component.get("backend") or backend, 32),
        }
        if isinstance(workflow, Mapping) and workflow.get("template_id"):
            kwargs["workflow"] = dict(workflow)
        try:
            response = preview(
                _bounded_text(component.get("request"), 2000),
                **kwargs,
            )
        except Exception as exc:
            raise CompositeTaskPlanBridgeError(
                "component planning preview failed",
                code="taskplan_component_preview_failed",
            ) from exc
        if not isinstance(response, Mapping):
            raise CompositeTaskPlanBridgeError(
                "component planning preview is invalid",
                code="taskplan_component_preview_invalid",
            )
        status = str(response.get("status") or "").upper()
        if status in {"NEEDS_CLARIFICATION", "REJECTED"}:
            raise CompositeTaskPlanBridgeError(
                "component planning requires clarification",
                code="taskplan_component_clarification",
            )
        if status != "PLANNED":
            raise CompositeTaskPlanBridgeError(
                "component planning preview did not produce a plan",
                code="taskplan_component_preview_failed",
            )
        plan = response.get("plan")
        return plan if isinstance(plan, Mapping) else None


def project_task_plan_bridge(value: Any) -> dict[str, Any]:
    """Keep only safe structural bridge evidence for persistence/transport."""

    if not isinstance(value, Mapping):
        return _unavailable_bridge("taskplan_bridge_missing")
    state = str(value.get("state") or "unavailable")
    if state not in {"accepted", "deferred", "unavailable"}:
        state = "unavailable"
    components: list[dict[str, Any]] = []
    for raw in (value.get("components") or [])[:_MAX_COMPONENTS]:
        if not isinstance(raw, Mapping):
            continue
        item = {
            "component_id": _bounded_text(raw.get("component_id"), 48),
            "domain_id": _bounded_text(raw.get("domain_id"), 32),
            "state": str(raw.get("state") or "deferred")[:24],
            "reason_code": _bounded_text(raw.get("reason_code"), 96) or None,
        }
        if raw.get("source"):
            item["source"] = _bounded_text(raw.get("source"), 32)
        if isinstance(raw.get("plan"), Mapping):
            item["plan"] = _project_plan_projection(raw["plan"])
        if isinstance(raw.get("dag"), Mapping):
            item["dag"] = _project_dag(raw["dag"])
        if isinstance(raw.get("policy"), Mapping):
            item["policy"] = {
                "allowed_tools": _bounded_strings(raw["policy"].get("allowed_tools")),
                "result_types": _bounded_strings(raw["policy"].get("result_types")),
                "max_steps": _bounded_int(raw["policy"].get("max_steps"), 0, 128),
            }
        components.append(item)
    return {
        "schema_version": TASK_PLAN_BRIDGE_SCHEMA_VERSION,
        "state": state,
        "reason_code": _bounded_text(value.get("reason_code"), 96)
        or "taskplan_bridge_unavailable",
        "component_count": _bounded_int(value.get("component_count"), 0, _MAX_COMPONENTS),
        "materialized_count": _bounded_int(value.get("materialized_count"), 0, _MAX_COMPONENTS),
        "deferred_count": _bounded_int(value.get("deferred_count"), 0, _MAX_COMPONENTS),
        "components": components,
    }


def _explicit_task_plan(workflow: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(workflow, Mapping):
        return None
    if "task_plan" in workflow:
        value = workflow.get("task_plan")
        if not isinstance(value, Mapping):
            raise CompositeTaskPlanBridgeError(
                "workflow task_plan must be an object",
                code="taskplan_payload_invalid",
            )
        return value
    if "plan" in workflow:
        value = workflow.get("plan")
        if not isinstance(value, Mapping):
            raise CompositeTaskPlanBridgeError(
                "workflow plan must be an object", code="taskplan_payload_invalid"
            )
        return value
    if isinstance(workflow.get("steps"), list):
        return workflow
    return None


def _parse_and_validate(
    payload: Mapping[str, Any],
    *,
    allowed_tools: list[str],
    result_types: list[str],
    max_steps: int,
) -> TaskPlan:
    unknown = set(payload) - _TASK_PLAN_FIELDS
    if unknown:
        raise CompositeTaskPlanBridgeError(
            "task plan contains unsupported fields", code="taskplan_field_invalid"
        )
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise CompositeTaskPlanBridgeError(
            "task plan steps must be an array", code="taskplan_schema_invalid"
        )
    for step in steps:
        if not isinstance(step, Mapping) or set(step) - _STEP_FIELDS:
            raise CompositeTaskPlanBridgeError(
                "task plan step contains unsupported fields",
                code="taskplan_step_field_invalid",
            )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > _MAX_PLAN_BYTES:
        raise CompositeTaskPlanBridgeError(
            "task plan exceeds max_bytes", code="taskplan_too_large"
        )
    try:
        plan = parse_task_plan(payload, allowed_tools)
        validate_plan(plan, allowed_tools, max_steps)
    except (PlanningError, ValueError, TypeError) as exc:
        code = "taskplan_tool_not_allowlisted" if "unknown tool" in str(exc).lower() else "taskplan_schema_invalid"
        raise CompositeTaskPlanBridgeError(
            "task plan failed the execution gate", code=code
        ) from exc
    output_type = str(plan.output.get("type") or "").strip()
    if not output_type or output_type not in set(result_types):
        raise CompositeTaskPlanBridgeError(
            "task plan result type is not allowlisted",
            code="taskplan_result_type_not_allowlisted",
        )
    return plan


def _policy(
    context: Mapping[str, Any],
    *,
    domain_id: str,
    capability: Mapping[str, Any],
    workflow: Mapping[str, Any] | None,
) -> tuple[list[str], list[str]]:
    capability_tools = _bounded_strings(capability.get("tools"))
    capability_results = _bounded_strings(capability.get("result_types"))
    workflow_value = workflow if isinstance(workflow, Mapping) else {}
    registered = _registered_workflow(
        context, domain_id=domain_id, template_id=workflow_value.get("template_id")
    )
    if workflow_value.get("template_id") and registered is None:
        raise CompositeTaskPlanBridgeError(
            "workflow is not registered", code="taskplan_workflow_not_registered"
        )
    declared_tools = _bounded_strings(
        workflow_value.get("allowed_tools")
        or (registered or {}).get("allowed_tools")
        or capability_tools
    )
    declared_results = _bounded_strings(
        workflow_value.get("result_types")
        or (registered or {}).get("result_types")
        or capability_results
    )
    if not declared_tools or not declared_results:
        raise CompositeTaskPlanBridgeError(
            "task plan policy is incomplete", code="taskplan_policy_unavailable"
        )
    if set(declared_tools) - set(capability_tools):
        raise CompositeTaskPlanBridgeError(
            "workflow tool exceeds capability allowlist",
            code="taskplan_tool_not_allowlisted",
        )
    if set(declared_results) - set(capability_results):
        raise CompositeTaskPlanBridgeError(
            "workflow result exceeds capability allowlist",
            code="taskplan_result_type_not_allowlisted",
        )
    return declared_tools, declared_results


def _capability(
    context: Mapping[str, Any], domain_id: str, capability_id: Any
) -> Mapping[str, Any] | None:
    target = str(capability_id or "")
    for item in context.get("capability_index") or []:
        if isinstance(item, Mapping) and str(item.get("domain_id")) == domain_id and str(item.get("capability_id") or item.get("id")) == target:
            return item
    return None


def _registered_workflow(
    context: Mapping[str, Any], *, domain_id: str, template_id: Any
) -> Mapping[str, Any] | None:
    target = str(template_id or "")
    if not target:
        return None
    for item in context.get("workflow_index") or []:
        if isinstance(item, Mapping) and str(item.get("domain_id")) == domain_id and str(item.get("workflow_id") or item.get("id")) == target:
            return item
    return None


def _project_plan(plan: TaskPlan) -> dict[str, Any]:
    return {
        "goal": plan.goal[:320],
        "steps": [
            {
                "id": step.id[:48],
                "tool": step.tool[:96],
                "depends_on": list(step.depends_on)[:_MAX_STEPS],
                "arg_keys": sorted(str(key)[:96] for key in step.args)[:32],
            }
            for step in plan.steps[:_MAX_STEPS]
        ],
        "output": {"type": str(plan.output.get("type") or "")[:96]},
        "assumptions": [str(item)[:320] for item in plan.assumptions[:16]],
    }


def _project_plan_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "goal": _bounded_text(value.get("goal"), 320),
        "steps": [
            {
                "id": _bounded_text(item.get("id"), 48),
                "tool": _bounded_text(item.get("tool"), 96),
                "depends_on": _bounded_strings(item.get("depends_on")),
                "arg_keys": _bounded_strings(item.get("arg_keys"), limit=32),
            }
            for item in (value.get("steps") or [])[:_MAX_STEPS]
            if isinstance(item, Mapping)
        ],
        "output": {"type": _bounded_text((value.get("output") or {}).get("type"), 96)},
        "assumptions": _bounded_strings(value.get("assumptions"), limit=16),
    }


def _project_dag(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": _bounded_text(item.get("id"), 48),
                "tool": _bounded_text(item.get("tool"), 96),
                "depends_on": _bounded_strings(item.get("depends_on")),
                "arg_keys": _bounded_strings(item.get("arg_keys"), limit=32),
            }
            for item in (value.get("nodes") or [])[:_MAX_STEPS]
            if isinstance(item, Mapping)
        ],
        "edges": [
            {
                "from": _bounded_text(item.get("from"), 48),
                "to": _bounded_text(item.get("to"), 48),
            }
            for item in (value.get("edges") or [])[:_MAX_STEPS * 2]
            if isinstance(item, Mapping)
        ],
        "node_count": _bounded_int(value.get("node_count"), 0, _MAX_STEPS),
        "edge_count": _bounded_int(value.get("edge_count"), 0, _MAX_STEPS * 2),
    }


def _unavailable_bridge(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": TASK_PLAN_BRIDGE_SCHEMA_VERSION,
        "state": "unavailable",
        "reason_code": reason_code[:96],
        "component_count": 0,
        "materialized_count": 0,
        "deferred_count": 0,
        "components": [],
    }


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _bounded_strings(value: Any, *, limit: int = 24) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else []
    result: list[str] = []
    for item in values:
        text = _bounded_text(item, 96)
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
    "CompositeTaskPlanBridge",
    "CompositeTaskPlanBridgeError",
    "TASK_PLAN_BRIDGE_SCHEMA_VERSION",
    "project_task_plan_bridge",
]
