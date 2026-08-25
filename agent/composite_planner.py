"""Domain-neutral Rule/LLM planner contract for Composite requests.

Both planner adapters produce the same bounded candidate shape.  This module
does not execute a component.  It only validates planner output and converts
it to the existing ``spatial-agent.composite-request.v1`` contract before a
later application seam submits it to the Composite lifecycle.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from agent.composite_contract import normalize_composite_request


COMPOSITE_PLANNING_RESPONSE_SCHEMA_VERSION = "spatial-agent.composite-planning-response.v1"
_OUTCOMES = {"success", "needs_clarification", "rejected"}
_COMPONENT_FIELDS = {
    "component_id",
    "domain_id",
    "capability_id",
    "request",
    "depends_on",
    "required",
    "workflow",
}


class CompositePlannerError(ValueError):
    """Bounded planner failure safe for public application projections."""

    def __init__(self, message: str, *, code: str = "composite_planner_invalid"):
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def composite_plan_schema() -> dict[str, Any]:
    """Return the strict, provider-neutral schema requested from an LLM."""
    return {
        "type": "object",
        "required": ["outcome", "goal", "message", "components"],
        "additionalProperties": False,
        "properties": {
            "outcome": {
                "type": "string",
                "enum": sorted(_OUTCOMES),
            },
            "goal": {"type": "string", "maxLength": 320},
            "message": {"type": "string", "maxLength": 640},
            "components": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "required": [
                        "component_id",
                        "domain_id",
                        "capability_id",
                        "request",
                        "depends_on",
                        "required",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "component_id": {"type": "string", "maxLength": 48},
                        "domain_id": {"type": "string", "maxLength": 32},
                        "capability_id": {"type": "string", "maxLength": 96},
                        "request": {"type": "string", "maxLength": 2000},
                        "depends_on": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {"type": "string", "maxLength": 48},
                        },
                        "required": {"type": "boolean"},
                        "workflow": {"type": "object"},
                    },
                },
            },
        },
    }


class RuleCompositePlanner:
    """Adapter around deterministic candidate generation."""

    source = "rule"

    def __init__(self, candidate_builder: Callable[[str, Mapping[str, Any]], Mapping[str, Any]]):
        if not callable(candidate_builder):
            raise ValueError("candidate_builder must be callable")
        self._candidate_builder = candidate_builder

    def plan(
        self,
        request: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            payload = self._candidate_builder(request, context or {})
        except CompositePlannerError:
            raise
        except Exception as exc:
            raise CompositePlannerError(
                "rule planner failed", code="rule_planner_failed"
            ) from exc
        return normalize_composite_plan(
            payload,
            request=request,
            context=context,
            planner_source=self.source,
        )


class LLMCompositePlanner:
    """LLM adapter that asks only for a bounded Composite plan candidate."""

    source = "llm"

    def __init__(self, client: Any):
        if client is None or not callable(getattr(client, "complete_json", None)):
            raise ValueError("client must expose complete_json()")
        self._client = client

    def plan(
        self,
        request: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        bounded_context = _bounded_context(context)
        messages = [
            {
                "role": "system",
                "content": (
                    "Return only JSON matching the Composite planning schema. "
                    "Choose only capability_id and domain_id values present in "
                    "the trusted context. Do not invent tools, data, facts, "
                    "paths, code, or measurements. Use needs_clarification "
                    "when the request or context is insufficient."
                ),
            },
            {
                "role": "user",
                "content": request[:2000]
                + "\n\n[Trusted capability context]\n"
                + json.dumps(bounded_context, ensure_ascii=False, sort_keys=True),
            },
        ]
        try:
            payload = self._client.complete_json(messages, composite_plan_schema())
        except Exception as exc:
            raise CompositePlannerError(
                "composite planner provider failed", code="planner_provider_failed"
            ) from exc
        return normalize_composite_plan(
            payload,
            request=request,
            context=context,
            planner_source=self.source,
        )


def normalize_composite_plan(
    payload: Any,
    *,
    request: str,
    context: Mapping[str, Any] | None,
    planner_source: str,
) -> dict[str, Any]:
    """Validate a candidate and build the canonical Composite request."""
    if not isinstance(payload, Mapping):
        raise CompositePlannerError(
            "planner output must be an object", code="plan_object_required"
        )
    outcome = str(payload.get("outcome") or "").strip().lower()
    if outcome not in _OUTCOMES:
        raise CompositePlannerError(
            "planner outcome is invalid", code="plan_outcome_invalid"
        )
    goal = _text(payload.get("goal"), "goal", 320, required=outcome == "success")
    message = _text(payload.get("message"), "message", 640, required=False)
    raw_components = payload.get("components")
    if not isinstance(raw_components, list):
        raise CompositePlannerError(
            "planner components must be an array", code="plan_components_invalid"
        )
    if outcome != "success":
        if raw_components:
            raise CompositePlannerError(
                "non-success plan must not contain components",
                code="plan_components_unexpected",
            )
        return {
            "schema_version": COMPOSITE_PLANNING_RESPONSE_SCHEMA_VERSION,
            "status": "NEEDS_CLARIFICATION" if outcome == "needs_clarification" else "REJECTED",
            "planner_source": _text(planner_source, "planner_source", 32, required=True),
            "goal": goal,
            "message": message or "需要补充任务信息。",
            "components": [],
            "request": None,
            "validation": {"status": "not_run", "reason_code": outcome},
        }
    if not raw_components:
        raise CompositePlannerError(
            "success plan requires components", code="plan_components_required"
        )

    canonical_components = []
    projected_components = []
    for index, raw in enumerate(raw_components[:8]):
        if not isinstance(raw, Mapping):
            raise CompositePlannerError(
                "component must be an object", code="plan_component_object_required"
            )
        unknown = sorted(set(raw) - _COMPONENT_FIELDS)
        if unknown:
            raise CompositePlannerError(
                "component contains unsupported fields",
                code="plan_component_field_invalid",
            )
        component_id = _required_component_text(raw, "component_id")
        domain_id = _required_component_text(raw, "domain_id")
        capability_id = _required_component_text(raw, "capability_id")
        component_request = _required_component_text(raw, "request", 2000)
        dependencies = raw.get("depends_on", [])
        if not isinstance(dependencies, list):
            raise CompositePlannerError(
                "component depends_on must be an array",
                code="plan_dependencies_invalid",
            )
        item = {
            "component_id": component_id,
            "domain_id": domain_id,
            "request": component_request,
            "depends_on": [str(value)[:48] for value in dependencies],
            "required": bool(raw.get("required", True)),
        }
        if raw.get("workflow") is not None:
            if not isinstance(raw["workflow"], Mapping):
                raise CompositePlannerError(
                    "component workflow must be an object",
                    code="plan_workflow_invalid",
                )
            item["workflow"] = dict(raw["workflow"])
        canonical_components.append(item)
        projected_components.append(
            {
                **item,
                "capability_id": capability_id,
                "index": index,
            }
        )

    _validate_context_capabilities(projected_components, context)
    canonical_request = normalize_composite_request(
        {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": str(request or goal)[:2000],
            "components": canonical_components,
        }
    )
    return {
        "schema_version": COMPOSITE_PLANNING_RESPONSE_SCHEMA_VERSION,
        "status": "PLANNED",
        "planner_source": _text(planner_source, "planner_source", 32, required=True),
        "goal": goal,
        "message": message,
        "components": projected_components,
        "request": canonical_request,
        "validation": {
            "status": "valid",
            "reason_code": "canonical_composite_request",
        },
    }


def _validate_context_capabilities(
    components: list[Mapping[str, Any]], context: Mapping[str, Any] | None
) -> None:
    if not isinstance(context, Mapping) or "capability_index" not in context:
        return
    index = {
        (str(item.get("domain_id")), str(item.get("capability_id"))): item
        for item in (context.get("capability_index") or [])
        if isinstance(item, Mapping)
    }
    for component in components:
        key = (str(component["domain_id"]), str(component["capability_id"]))
        item = index.get(key)
        if item is None:
            raise CompositePlannerError(
                "planner selected an unknown capability",
                code="capability_not_registered",
            )
        if item.get("available") is False:
            raise CompositePlannerError(
                "planner selected an unavailable capability",
                code="capability_unavailable",
            )


def _bounded_context(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > 64_000:
        raise CompositePlannerError(
            "planner context exceeds max_bytes", code="planner_context_too_large"
        )
    return dict(value)


def _required_component_text(value: Mapping[str, Any], key: str, limit: int = 96) -> str:
    text = str(value.get(key) or "").strip()
    if not text:
        raise CompositePlannerError(
            "component " + key + " is required", code="plan_component_field_missing"
        )
    return text[:limit]


def _text(value: Any, key: str, limit: int, *, required: bool) -> str:
    text = str(value or "").strip()[:limit]
    if required and not text:
        raise CompositePlannerError(key + " is required", code="plan_field_missing")
    return text


__all__ = [
    "COMPOSITE_PLANNING_RESPONSE_SCHEMA_VERSION",
    "CompositePlannerError",
    "LLMCompositePlanner",
    "RuleCompositePlanner",
    "composite_plan_schema",
    "normalize_composite_plan",
]
