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
_TOP_LEVEL_FIELDS = {"outcome", "goal", "message", "components"}
_TOP_LEVEL_ALIASES = {
    "status": "outcome",
    "objective": "goal",
    "reason": "message",
    "plan": "components",
    "steps": "components",
}
_COMPONENT_ALIASES = {
    "id": "component_id",
    "componentId": "component_id",
    "domain": "domain_id",
    "domainId": "domain_id",
    "capability": "capability_id",
    "capabilityId": "capability_id",
    "task": "request",
    "query": "request",
    "description": "request",
    "dependencies": "depends_on",
    "dependsOn": "depends_on",
    "is_required": "required",
    "isRequired": "required",
}
_OUTCOME_ALIASES = {
    "planned": "success",
    "ok": "success",
    "completed": "success",
    "clarification": "needs_clarification",
    "clarify": "needs_clarification",
    "need_clarification": "needs_clarification",
    "needs-clarification": "needs_clarification",
    "reject": "rejected",
    "invalid": "rejected",
}
_COMPONENT_FIELDS = {
    "component_id",
    "domain_id",
    "capability_id",
    "request",
    "depends_on",
    "required",
    "workflow",
}
_CONTEXT_SCHEMAS = {
    "spatial-agent.composite-planner-context.v1",
    "spatial-agent.composite-request-context.v2",
}


class CompositePlannerError(ValueError):
    """Bounded planner failure safe for public application projections."""

    def __init__(self, message: str, *, code: str = "composite_planner_invalid"):
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def normalize_provider_response(payload: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize only documented provider drift before the canonical contract.

    The compatibility surface is intentionally small: one ``plan`` wrapper,
    a few top-level aliases, common camelCase component names, and safe
    defaults for outcome/components/required fields.  Unknown fields and
    conflicting aliases fail closed.  The returned summary contains field
    names and actions only; it never contains provider content.
    """
    if not isinstance(payload, Mapping):
        raise CompositePlannerError(
            "planner output must be an object", code="plan_object_required"
        )

    actions: list[str] = []
    source = dict(payload)
    if set(source) == {"plan"} and isinstance(source.get("plan"), Mapping):
        source = dict(source["plan"])
        actions.append("unwrap:plan")

    unknown = sorted(str(key) for key in set(source) - set(_TOP_LEVEL_FIELDS) - set(_TOP_LEVEL_ALIASES))
    if unknown:
        raise CompositePlannerError(
            "planner response contains unsupported fields",
            code="plan_response_field_invalid",
        )

    normalized: dict[str, Any] = {}
    for key, value in source.items():
        target = _TOP_LEVEL_ALIASES.get(key, key)
        if target in normalized:
            raise CompositePlannerError(
                "planner response contains conflicting aliases",
                code="plan_response_alias_conflict",
            )
        normalized[target] = value
        if target != key:
            actions.append(f"alias:{key}->{target}")

    raw_components_present = "components" in normalized
    raw_components = normalized.get("components")
    if raw_components_present and not isinstance(raw_components, list):
        raise CompositePlannerError(
            "planner components must be an array", code="plan_components_invalid"
        )
    if raw_components_present and len(raw_components) > 8:
        raise CompositePlannerError(
            "planner components exceed the maximum", code="plan_components_limit"
        )

    raw_outcome = normalized.get("outcome")
    if raw_outcome is None or not str(raw_outcome).strip():
        if not raw_components_present:
            raise CompositePlannerError(
                "planner components must be an array", code="plan_components_invalid"
            )
        normalized["outcome"] = "success" if raw_components else "needs_clarification"
        actions.append("default:outcome_from_components")
    else:
        outcome = str(raw_outcome).strip().lower().replace(" ", "_")
        outcome = _OUTCOME_ALIASES.get(outcome, outcome)
        normalized["outcome"] = outcome
        if outcome != str(raw_outcome).strip().lower():
            actions.append("alias:outcome_value")

    if normalized["outcome"] != "success" and not raw_components_present:
        normalized["components"] = []
        actions.append("default:components_for_non_success")
    if normalized["outcome"] == "success" and not str(normalized.get("goal") or "").strip():
        normalized["goal"] = "组合分析"
        actions.append("default:goal")

    components = normalized.get("components")
    if not isinstance(components, list):
        raise CompositePlannerError(
            "planner components must be an array", code="plan_components_invalid"
        )
    normalized_components = []
    for raw in components[:8]:
        if not isinstance(raw, Mapping):
            raise CompositePlannerError(
                "component must be an object", code="plan_component_object_required"
            )
        unknown_component = sorted(
            str(key)
            for key in set(raw) - set(_COMPONENT_FIELDS) - set(_COMPONENT_ALIASES)
        )
        if unknown_component:
            raise CompositePlannerError(
                "component contains unsupported fields",
                code="plan_component_field_invalid",
            )
        component: dict[str, Any] = {}
        for key, value in raw.items():
            target = _COMPONENT_ALIASES.get(key, key)
            if target in component:
                raise CompositePlannerError(
                    "component contains conflicting aliases",
                    code="plan_component_alias_conflict",
                )
            component[target] = value
            if target != key:
                actions.append(f"component_alias:{key}->{target}")
        if "depends_on" not in component:
            component["depends_on"] = []
            actions.append("default:component_depends_on")
        if "required" not in component:
            component["required"] = True
            actions.append("default:component_required")
        normalized_components.append(component)
    normalized["components"] = normalized_components

    return normalized, {
        "status": "normalized" if actions else "identity",
        "actions": actions[:16],
    }


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


def _normalize_planner_payload(
    payload: Any,
    *,
    request: str,
    context: Mapping[str, Any] | None,
    planner_source: str,
) -> dict[str, Any]:
    normalized, compatibility = normalize_provider_response(payload)
    result = normalize_composite_plan(
        normalized,
        request=request,
        context=context,
        planner_source=planner_source,
    )
    result["compatibility"] = compatibility
    return result


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
        return _normalize_planner_payload(
            payload,
            request=request,
            context=context,
            planner_source=self.source,
        )


class ReplayCompositePlanner:
    """Deterministic planner for sanitized provider replays and contract tests."""

    source = "replay"

    def __init__(self, response: Any):
        if not isinstance(response, Mapping) and not callable(response):
            raise ValueError("response must be a mapping or callable")
        self._response = response

    def plan(
        self,
        request: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            payload = (
                self._response(request, context or {})
                if callable(self._response)
                else self._response
            )
        except CompositePlannerError:
            raise
        except Exception as exc:
            raise CompositePlannerError(
                "replay planner failed", code="replay_planner_failed"
            ) from exc
        return _normalize_planner_payload(
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
                    "Return exactly one JSON object matching the Composite planning schema. "
                    "The top-level object must contain only outcome, goal, message, "
                    "and components; never include analysis, reasoning, explanation, "
                    "metadata, or any other field. Each component may contain only "
                    "component_id, domain_id, capability_id, request, depends_on, "
                    "required, and optional workflow. Choose only capability_id and "
                    "domain_id values present in the trusted context. Do not invent "
                    "tools, data, facts, paths, code, or measurements. Use "
                    "needs_clarification when the request or context is insufficient. "
                    "Copy each domain_id and capability_id exactly from one "
                    "capability_index entry; selection_key is only a reference hint "
                    "and must not be returned as a component field. Do not infer an "
                    "ID from a label or tool name. "
                    "For success, components must be non-empty; for "
                    "needs_clarification or rejected, components must be an empty "
                    "array. Never return components with a non-success outcome."
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
        return _normalize_planner_payload(
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
    if len(raw_components) > 8:
        raise CompositePlannerError(
            "planner components exceed the maximum", code="plan_components_limit"
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
    schema_version = str(value.get("schema_version") or "").strip()
    if schema_version and schema_version not in _CONTEXT_SCHEMAS:
        raise CompositePlannerError(
            "planner context schema is unsupported",
            code="planner_context_schema_invalid",
        )
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
    "ReplayCompositePlanner",
    "RuleCompositePlanner",
    "composite_plan_schema",
    "normalize_composite_plan",
    "normalize_provider_response",
]
