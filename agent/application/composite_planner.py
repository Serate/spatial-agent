"""Domain-neutral Rule/LLM planner contract for Composite requests.

Both planner adapters produce the same bounded candidate shape.  This module
does not execute a component.  It only validates planner output and converts
it to the existing ``spatial-agent.composite-request.v1`` contract before a
later application seam submits it to the Composite lifecycle.
"""

from __future__ import annotations

import json
import inspect
from collections.abc import Callable, Mapping
from typing import Any

from agent.application.composite_contract import (
    CompositeContractError,
    normalize_composite_request,
)
from agent.planner_repair import safe_repair_request
from agent.data_kinds import SUPPORTED_DATA_KINDS
from agent.analysis_intent import SUPPORTED_ANALYSIS_OPERATIONS
from agent.runtime_core.composition import (
    CompositionError,
    normalize_component_inputs,
    validate_component_composition,
)
from agent.runtime_core.planner_envelope import (
    PLANNER_ENVELOPE_MAX_BYTES,
    PlannerEnvelopeError,
    build_planner_envelope,
)


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
    "analysis_operations",
    "workflow",
    "inputs",
}
_CONTEXT_SCHEMAS = {
    "spatial-agent.composite-planner-context.v1",
    "spatial-agent.composite-request-context.v2",
}
_MAX_CONTEXT_BYTES = PLANNER_ENVELOPE_MAX_BYTES


class CompositePlannerError(ValueError):
    """Bounded planner failure safe for public application projections."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "composite_planner_invalid",
        details: Mapping[str, Any] | None = None,
    ):
        self.code = str(code)[:96]
        self.details = dict(details) if isinstance(details, Mapping) else {}
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
                        "component_id": {"type": "string", "minLength": 1, "maxLength": 48},
                        "domain_id": {"type": "string", "minLength": 1, "maxLength": 32},
                        "capability_id": {"type": "string", "minLength": 1, "maxLength": 96},
                        "request": {"type": "string", "minLength": 1, "maxLength": 2000},
                        "depends_on": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {"type": "string", "maxLength": 48},
                        },
                        "required": {"type": "boolean"},
                        "analysis_operations": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "string",
                                "enum": list(SUPPORTED_ANALYSIS_OPERATIONS),
                            },
                        },
                        "inputs": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "required": ["name", "source", "accepted_kinds", "required"],
                                "additionalProperties": False,
                                "properties": {
                                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                                    "source": {
                                        "type": "object",
                                        "required": ["component_id", "path"],
                                        "additionalProperties": False,
                                        "properties": {
                                            "component_id": {"type": "string", "minLength": 1, "maxLength": 48},
                                            "path": {
                                                "type": "string",
                                                "pattern": "^result(?:\\.[A-Za-z][A-Za-z0-9_-]{0,63}){0,7}$",
                                                "maxLength": 160,
                                            },
                                        },
                                    },
                                    "accepted_kinds": {
                                        "type": "array",
                                        "minItems": 1,
                                        "maxItems": 8,
                                        "items": {
                                            "type": "string",
                                            "enum": list(SUPPORTED_DATA_KINDS),
                                        },
                                    },
                                    "required": {"type": "boolean"},
                                },
                            },
                        },
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
        self._last_envelope_metrics: dict[str, Any] = {}
        # ``complete_json`` is the only required client seam.  Keep a small
        # adapter-level fallback so clients that intentionally do not expose
        # metrics still produce an honest planner-attempt receipt.  Provider
        # metrics remain authoritative whenever they are available.
        self._last_call_metrics: dict[str, Any] = {
            "status": "not_started",
            "attempts": 0,
            "retries": 0,
        }

    def metrics(self) -> Mapping[str, Any]:
        provider_metrics = getattr(self._client, "metrics", None)
        if callable(provider_metrics):
            value = provider_metrics()
        else:
            value = {}
        result = dict(value) if isinstance(value, Mapping) else {}
        for key, fallback in self._last_call_metrics.items():
            if result.get(key) in (None, ""):
                result[key] = fallback
        result.update(self._last_envelope_metrics)
        return result

    def plan(
        self,
        request: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        bounded_context = _bounded_context(context)
        repair_request = safe_repair_request(bounded_context.get("planner_repair"))
        projection_stage = "repair" if repair_request is not None else "selection"
        encoded_context = json.dumps(
            bounded_context, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self._last_envelope_metrics = {
            "projection_stage": projection_stage,
            "envelope_bytes": len(encoded_context.encode("utf-8")),
            "envelope_max_bytes": _MAX_CONTEXT_BYTES,
        }
        self._last_call_metrics = {
            "status": "in_progress",
            "attempts": 1,
            "retries": 0,
        }
        repair_instruction = ""
        if repair_request is not None:
            repair_instruction = (
                " This is one bounded schema repair attempt. Correct only the "
                "declared output shape for the supplied repair reason; do not "
                "change facts, domains, capabilities, tools, datasets, or "
                "permissions, and do not describe the repair."
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object matching the Composite planning schema. "
                    "The top-level object must contain only outcome, goal, message, "
                    "and components; never include analysis, reasoning, explanation, "
                    "metadata, or any other field. Each component may contain only "
                    "component_id, domain_id, capability_id, request, depends_on, "
                    "required, and optional analysis_operations. A component may additionally include bounded inputs "
                    "with name, source.component_id, source.path, accepted_kinds, and required. "
                    "Workflow selection is resolved by the selected "
                    "Domain; do not return a workflow object. Choose only capability_id and "
                    "domain_id values present in the trusted planner envelope. Do not invent "
                    "tools, data, facts, paths, code, or measurements. Use "
                    "needs_clarification when the request or context is insufficient. "
                    "Copy each domain_id and capability_id exactly from one "
                    "capability_index entry; selection_key is only a reference hint "
                    "and must not be returned as a component field. Do not infer an "
                    "ID from a label or tool name. "
                    "Select only candidates whose available field is true and, when "
                    "present, whose execution_ready field is true. Candidates with "
                    "plan_mode=unbound, execution_ready=false, workflow_not_registered, "
                    "or missing facts are advisory only and must not be selected for "
                    "a success plan; if no suitable ready candidate exists, return "
                    "needs_clarification. "
                    "When the request contains multiple independent analytical goals, "
                    "map each goal to the smallest suitable registered capability and "
                    "keep distinct goals as distinct components; compose multiple "
                    "components when the request requires multiple outputs. Do not "
                    "collapse a multi-goal request into one component merely to shorten "
                    "the plan. Preserve dependencies only when a later component uses "
                    "an earlier result. "
                    "Use the bounded analysis_intent and each capability's "
                    "analysis_operations as semantic guidance; do not invent an "
                    "operation, data kind, dataset, workflow, or result type. "
                    "For success, components must be non-empty; for "
                    "needs_clarification or rejected, components must be an empty "
                    "array. Never return components with a non-success outcome."
                    + repair_instruction
                ),
            },
            {
                "role": "user",
                "content": request[:2000]
                + "\n\n[Trusted planner envelope]\n"
                + json.dumps(bounded_context, ensure_ascii=False, sort_keys=True),
            },
        ]
        schema = composite_plan_schema()
        try:
            # Keep the long-standing two-argument client seam.  Structured
            # wire mode is negotiated by the provider client itself; adding a
            # keyword here would break replay/fake clients that intentionally
            # implement only the public minimal protocol.
            payload = _complete_composite_json(
                self._client,
                messages,
                schema,
                deterministic=True,
            )
        except Exception as exc:
            # Some compatible gateways return an empty/truncated JSON body
            # even though the HTTP request itself succeeded.  The ordinary
            # Planner already has a bounded compact recovery seam; Composite
            # planning must use the same one so a transient provider shape
            # failure does not become a false capability failure.  This is
            # exactly one additional provider call and still crosses the same
            # normalization, capability, TaskPlan and execution gates.
            compact = getattr(self._client, "complete_compact_json", None)
            if (
                getattr(exc, "code", None) == "invalid_model_response"
                and callable(compact)
            ):
                try:
                    payload = compact(messages, schema)
                except Exception as compact_exc:
                    exc = compact_exc
                else:
                    self._last_call_metrics = {
                        "status": "success",
                        "attempts": 2,
                        "retries": 0,
                        "compact_recovery_attempts": 1,
                    }
                    return _normalize_planner_payload(
                        payload,
                        request=request,
                        context=context,
                        planner_source=self.source,
                    )
            call_metrics: dict[str, Any] = {
                "status": "error",
                "attempts": 2
                if getattr(exc, "code", None) == "invalid_model_response"
                and callable(compact)
                else 1,
                "retries": 0,
            }
            retryable = getattr(exc, "retryable", None)
            if isinstance(retryable, bool):
                # Only copy the bounded recovery flag.  Never copy exception
                # text, URLs, response bodies or arbitrary provider fields.
                call_metrics["retryable"] = retryable
            self._last_call_metrics = call_metrics
            provider_failure = {}
            for key in ("category", "code"):
                value = getattr(exc, key, None)
                if value is not None and str(value).strip():
                    provider_failure[key] = str(value).strip()[:96]
            retryable = getattr(exc, "retryable", None)
            if isinstance(retryable, bool):
                provider_failure["retryable"] = retryable
            raise CompositePlannerError(
                "composite planner provider failed",
                code="planner_provider_failed",
                details={"provider_failure": provider_failure}
                if provider_failure
                else None,
            ) from exc
        self._last_call_metrics = {
            "status": "success",
            "attempts": 1,
            "retries": 0,
        }
        return _normalize_planner_payload(
            payload,
            request=request,
            context=context,
            planner_source=self.source,
        )


def _complete_composite_json(
    client: Any,
    messages: Any,
    schema: Mapping[str, Any],
    *,
    deterministic: bool,
) -> Mapping[str, Any]:
    """Call a structured provider without widening the minimal client seam."""

    method = getattr(client, "complete_json", None)
    if not callable(method):
        raise CompositePlannerError(
            "planner client does not support structured JSON",
            code="planner_provider_unavailable",
        )
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        item.kind == inspect.Parameter.VAR_KEYWORD
        for item in parameters.values()
    )
    kwargs: dict[str, Any] = {}
    if accepts_kwargs or "schema_name" in parameters:
        kwargs["schema_name"] = "composite_plan"
    if accepts_kwargs or "deterministic" in parameters:
        kwargs["deterministic"] = bool(deterministic)
    payload = method(messages, schema, **kwargs)
    if not isinstance(payload, Mapping):
        raise CompositePlannerError(
            "planner output must be an object",
            code="plan_object_required",
        )
    return payload


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

    planner_components = []
    capability_ids: list[str] = []
    for raw in raw_components[:8]:
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
        if planner_source == "llm" and "workflow" in raw:
            raise CompositePlannerError(
                "LLM planner cannot provide a workflow",
                code="plan_component_workflow_forbidden",
            )
        component_id = _required_component_text(raw, "component_id")
        domain_id = _required_component_text(raw, "domain_id")
        capability_id = _required_component_text(raw, "capability_id")
        component_request = _required_component_text(raw, "request", 2000)
        dependencies = raw.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(value, str) for value in dependencies
        ):
            raise CompositePlannerError(
                "component depends_on must be an array",
                code="plan_dependencies_invalid",
            )
        item = {
            "component_id": component_id,
            "domain_id": domain_id,
            "request": component_request,
            "depends_on": [value[:48] for value in dependencies],
            "required": _required_bool(raw, "required"),
        }
        if raw.get("analysis_operations") is not None:
            item["analysis_operations"] = _normalize_analysis_operations(
                raw.get("analysis_operations")
            )
        if raw.get("workflow") is not None:
            if not isinstance(raw["workflow"], Mapping):
                raise CompositePlannerError(
                    "component workflow must be an object",
                    code="plan_workflow_invalid",
                )
            item["workflow"] = dict(raw["workflow"])
        if raw.get("inputs") is not None:
            try:
                item["inputs"] = _normalize_planner_inputs(raw.get("inputs"))
            except CompositionError as exc:
                raise CompositePlannerError(str(exc), code=exc.code) from exc
        planner_components.append(item)
        capability_ids.append(capability_id)

    try:
        canonical_request = normalize_composite_request(
            {
                "schema_version": "spatial-agent.composite-request.v1",
                "request": str(request or goal)[:2000],
                "components": planner_components,
            }
        )
    except CompositeContractError as exc:
        raise CompositePlannerError(
            "planner components do not form a canonical request",
            code=exc.code,
        ) from exc
    # The public request contract owns identifier canonicalization (including
    # lower-casing component/domain IDs and normalizing dependencies). Rebuild
    # the planner projection from that trusted result so the capability
    # projection and the later execution binding cannot drift apart.
    projected_components = []
    for index, canonical in enumerate(canonical_request["components"]):
        source = planner_components[index]
        projected_components.append(
            {
                **canonical,
                "capability_id": capability_ids[index],
                "index": index,
                **(
                    {"analysis_operations": source["analysis_operations"]}
                    if "analysis_operations" in source
                    else {}
                ),
                # ``normalize_composite_request`` intentionally bounds deeply
                # nested public workflow payloads.  Keep the original
                # planner-side workflow only for deterministic Rule/Replay
                # adapters; the execution bridge still owns its full schema,
                # tool allowlist, and TaskPlan validation.  LLM output is not
                # allowed to provide a workflow at all.
                **(
                    {"workflow": source["workflow"]}
                    if planner_source != "llm" and "workflow" in source
                    else {}
                ),
            }
        )

    _validate_context_capabilities(projected_components, context)
    try:
        validate_component_composition(projected_components, context=context)
    except CompositionError as exc:
        raise CompositePlannerError(str(exc), code=exc.code) from exc
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
        if item.get("plan_mode") == "unbound":
            raise CompositePlannerError(
                "planner selected a capability without a registered workflow",
                code="capability_not_materializable",
            )
        if "execution_ready" in item and not bool(item.get("execution_ready")):
            reason = str(
                item.get("execution_reason_code")
                or item.get("execution_readiness")
                or item.get("state")
                or "capability_unavailable"
            ).strip()[:96]
            raise CompositePlannerError(
                "planner selected a capability that is not execution-ready",
                code=reason or "capability_unavailable",
            )
        requested_operations = set(component.get("analysis_operations") or ())
        supported_operations = set(item.get("analysis_operations") or ())
        if requested_operations:
            if not supported_operations:
                raise CompositePlannerError(
                    "planner selected a capability without declared analysis operations",
                    code="capability_operation_undeclared",
                )
            if not requested_operations.issubset(supported_operations):
                raise CompositePlannerError(
                    "planner selected a capability that does not support the requested analysis operation",
                    code="capability_operation_mismatch",
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
    try:
        # Request construction keeps the discovery projection as an internal
        # receipt.  The provider gets the projection for the decision it is
        # about to make; a repair request is deliberately narrower again.
        stage = "repair" if safe_repair_request(value.get("planner_repair")) else "selection"
        return build_planner_envelope(
            value,
            max_bytes=_MAX_CONTEXT_BYTES,
            projection_stage=stage,
        )
    except PlannerEnvelopeError as exc:
        raise CompositePlannerError(
            "planner context exceeds max_bytes"
            if exc.code == "planner_envelope_too_large"
            else "planner context is invalid",
            code=(
                "planner_context_too_large"
                if exc.code == "planner_envelope_too_large"
                else exc.code
            ),
        ) from exc


def _required_component_text(value: Mapping[str, Any], key: str, limit: int = 96) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise CompositePlannerError(
            "component " + key + " must be a string",
            code="plan_component_field_invalid",
        )
    text = raw.strip()
    if not text:
        raise CompositePlannerError(
            "component " + key + " is required", code="plan_component_field_missing"
        )
    if len(text) > limit:
        raise CompositePlannerError(
            "component " + key + " exceeds its limit",
            code="plan_component_field_invalid",
        )
    return text


def _required_bool(value: Mapping[str, Any], key: str) -> bool:
    raw = value.get(key, True)
    if not isinstance(raw, bool):
        raise CompositePlannerError(
            "component " + key + " must be boolean",
            code="plan_component_field_invalid",
        )
    return raw


def _normalize_analysis_operations(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CompositePlannerError(
            "component analysis_operations must be a non-empty array",
            code="plan_analysis_operations_invalid",
        )
    if len(value) > 8 or any(not isinstance(item, str) for item in value):
        raise CompositePlannerError(
            "component analysis_operations is invalid",
            code="plan_analysis_operations_invalid",
        )
    result: list[str] = []
    for item in value:
        operation = item.strip()
        if operation not in SUPPORTED_ANALYSIS_OPERATIONS:
            raise CompositePlannerError(
                "component analysis operation is unsupported",
                code="plan_analysis_operation_unsupported",
            )
        if operation not in result:
            result.append(operation)
    return result


def _normalize_planner_inputs(value: Any) -> list[dict[str, Any]]:
    """Normalize input references while aligning IDs with the request contract."""

    normalized = normalize_component_inputs(value)
    for item in normalized:
        source = item.get("source")
        if isinstance(source, Mapping):
            source["component_id"] = str(source.get("component_id") or "").strip().lower()
    return normalized


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
