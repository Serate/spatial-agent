"""Bounded Planner-facing projection helpers for cross-Domain Composite requests.

Split out of ``composite_planning`` so the projection functions live behind a
small, stable seam.  This module only projects catalog/readiness/planner data;
it does not execute components or carry Domain-specific policy.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.application.composite_contract import (
    inherit_composite_runtime_selection,
    normalize_composite_request,
)
from agent.application.composite_request_context import (
    COMPOSITE_REQUEST_CONTEXT_MAX_BYTES,
    CompositeRequestContextBuilder,
    CompositeRequestContextError,
)
from agent.application.composite_planner import CompositePlannerError
from agent.analysis_intent import AnalysisIntentError, normalize_analysis_intent
from agent.failure_contract import build_failure_evidence
from agent.planner_repair import (
    build_planner_repair_request,
    build_repair_lineage,
    is_repairable_planner_error,
)
from agent.integration.provider_structured_output import project_structured_output_evidence
from agent.request_requirements import project_request_requirements
from agent.data_readiness import project_data_readiness
from agent.integration.provider_runtime import (
    build_planner_attempt_receipt,
    project_planner_attempt_receipt,
    project_provider_runtime_evidence,
)
from agent.runtime_core.composite_taskplan import (
    CompositeTaskPlanBridge,
    CompositeTaskPlanBridgeError,
    project_task_plan_bridge,
)
from agent.runtime_core.execution_binding import (
    ExecutionBindingError,
    build_execution_binding,
    project_execution_binding,
)
from agent.runtime_core.plan_completeness import (
    annotate_catalog_capabilities,
    assess_catalog_consistency,
    validate_plan_completeness,
    PlanCompletenessError,
)
from agent.runtime_core.plan_receipt import build_canonical_plan_receipt
from agent.runtime_core.selection_evidence import project_selection_evidence
from agent.runtime_core.clarification_continuation import (
    ClarificationContinuationError,
    consume_fact_continuation,
)
from agent.runtime_core.planner_envelope import (
    PlannerEnvelopeError,
    build_execution_planner_envelope,
    project_planner_envelope_evidence,
)


COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION = "spatial-agent.composite-planner-context.v1"
COMPOSITE_PLANNER_EVIDENCE_SCHEMA_VERSION = "spatial-agent.composite-planner-evidence.v1"
COMPOSITE_PLANNER_SELECTION_SCHEMA_VERSION = "spatial-agent.composite-planner-selection.v1"
_SAFE_CAPABILITY_FIELDS = (
    "id",
    "label",
    "description",
    "datasets",
    "tools",
    "result_types",
    "analysis_operations",
    "available",
    "availability_mode",
    "availability_reason",
    "missing_datasets",
    "derived_datasets",
    "data_layer",
    "capability_status",
    "workflow_ids",
    "plan_mode",
    "output_profiles",
)

def _safe_compatibility(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": "identity", "actions": []}
    status = str(value.get("status") or "identity").strip().lower()
    if status not in {"identity", "normalized"}:
        status = "identity"
    actions = []
    for action in value.get("actions") or []:
        text = str(action or "").strip()[:96]
        if text and text not in actions:
            actions.append(text)
        if len(actions) >= 16:
            break
    return {"status": status, "actions": actions}


def _project_discovery_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Expose only receipt identity and bounded readiness counts to results."""

    candidates = [
        item for item in (value.get("candidates") or []) if isinstance(item, Mapping)
    ]
    states: dict[str, int] = {}
    for item in candidates:
        state = str(item.get("state") or "unknown")[:32]
        states[state] = states.get(state, 0) + 1
    requirements = [
        item
        for item in (value.get("data_requirements") or [])
        if isinstance(item, Mapping)
    ]
    receipt_evidence = value.get("evidence")
    domain_count = len(value.get("domains") or [])
    if isinstance(receipt_evidence, Mapping):
        try:
            domain_count = int(receipt_evidence.get("domain_count") or domain_count)
        except (TypeError, ValueError):
            pass
    return {
        "schema_version": str(value.get("schema_version") or "")[:96],
        "request_fingerprint": str(value.get("request_fingerprint") or "")[:128],
        "discovery_fingerprint": str(value.get("discovery_fingerprint") or "")[:128],
        "state": str(value.get("state") or "unknown")[:32],
        "reason_code": str(value.get("reason_code") or "unknown")[:96],
        "domain_count": max(0, min(8, domain_count)),
        "candidate_count": max(0, min(16, len(candidates))),
        "data_requirement_count": max(0, min(64, len(requirements))),
        "candidate_states": states,
        "next_actions": [str(item)[:160] for item in (value.get("next_actions") or [])[:4]],
    }


def _validate_continuation_selection(
    continuation: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any],
    components: Sequence[Any],
    task_plan_bridge: Mapping[str, Any],
) -> None:
    """Ensure a resumed request cannot switch component identity silently."""

    if continuation is None:
        return
    if str(continuation.get("schema_version") or "") == "spatial-agent.composite-clarification-continuation.v1":
        expected_components = {
            str(item.get("component_id")): item
            for item in (continuation.get("components") or [])
            if isinstance(item, Mapping) and str(item.get("component_id") or "")
        }
        selected_components = {
            str(item.get("component_id")): item
            for item in components
            if isinstance(item, Mapping) and str(item.get("component_id") or "")
        }
        if set(expected_components) != set(selected_components) or not expected_components:
            raise CompositePlannerError(
                "continuation component set does not match",
                code="continuation_component_mismatch",
            )
        bridge_by_id = {
            str(item.get("component_id")): item
            for item in (task_plan_bridge.get("components") or [])
            if isinstance(item, Mapping) and str(item.get("component_id") or "")
        }
        if set(bridge_by_id) != set(expected_components):
            raise CompositePlannerError(
                "continuation TaskPlan component set is unavailable",
                code="continuation_component_mismatch",
            )
        for component_id, expected_component in expected_components.items():
            actual_component = selected_components[component_id]
            if (
                str(actual_component.get("domain_id") or "")
                != str(expected_component.get("domain_id") or "")
                or str(actual_component.get("capability_id") or "")
                != str(expected_component.get("capability_id") or "")
            ):
                raise CompositePlannerError(
                    "continuation capability identity does not match",
                    code="continuation_capability_mismatch",
                )
        bridge_handoff = task_plan_bridge.get("fact_handoff")
        actual = (
            str(bridge_handoff.get("planner_selection_fingerprint") or "")
            if isinstance(bridge_handoff, Mapping)
            else ""
        )
        expected = str(continuation.get("planner_selection_fingerprint") or "")
        if not expected or actual != expected:
            raise CompositePlannerError(
                "continuation planner selection does not match",
                code="continuation_selection_mismatch",
            )
        if str(context.get("request_fingerprint") or "") != str(
            continuation.get("request_fingerprint") or ""
        ):
            raise CompositePlannerError(
                "continuation request fingerprint does not match",
                code="continuation_request_mismatch",
            )
        return
    component_id = str(continuation.get("component_id") or "")
    domain_id = str(continuation.get("domain_id") or "")
    capability_id = str(continuation.get("capability_id") or "")
    selected = [
        item
        for item in components
        if isinstance(item, Mapping)
        and str(item.get("component_id") or "") == component_id
    ]
    if len(selected) != 1:
        raise CompositePlannerError(
            "continuation component is not selected exactly once",
            code="continuation_component_mismatch",
        )
    component = selected[0]
    if str(component.get("domain_id") or "") != domain_id or str(
        component.get("capability_id") or ""
    ) != capability_id:
        raise CompositePlannerError(
            "continuation capability identity does not match",
            code="continuation_capability_mismatch",
        )
    bridge_components = [
        item
        for item in (task_plan_bridge.get("components") or [])
        if isinstance(item, Mapping)
        and str(item.get("component_id") or "") == component_id
    ]
    if len(bridge_components) != 1:
        raise CompositePlannerError(
            "continuation TaskPlan identity is unavailable",
            code="continuation_component_mismatch",
        )
    handoff = bridge_components[0].get("fact_handoff")
    actual = (
        str(handoff.get("planner_selection_fingerprint") or "")
        if isinstance(handoff, Mapping)
        else ""
    )
    expected = str(continuation.get("planner_selection_fingerprint") or "")
    if not expected or actual != expected:
        raise CompositePlannerError(
            "continuation planner selection does not match",
            code="continuation_selection_mismatch",
        )
    if str(context.get("request_fingerprint") or "") != str(
        continuation.get("request_fingerprint") or ""
    ):
        raise CompositePlannerError(
            "continuation request fingerprint does not match",
            code="continuation_request_mismatch",
        )


def _continuation_descriptor(handoff: Mapping[str, Any]) -> dict[str, Any]:
    continuation = dict(handoff.get("continuation") or {})
    for key in (
        "request_fingerprint",
        "planner_selection_fingerprint",
        "component_id",
        "domain_id",
        "capability_id",
        "component_ids",
        "domain_ids",
    ):
        if key in handoff:
            continuation[key] = handoff[key]
    return continuation


def _continuation_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "schema_version": str(value.get("schema_version") or "")[:96],
        "request_fingerprint": str(value.get("request_fingerprint") or "")[:128],
        "planner_selection_fingerprint": str(
            value.get("planner_selection_fingerprint") or ""
        )[:128],
        "component_id": str(value.get("component_id") or "")[:96],
        "domain_id": str(value.get("domain_id") or "")[:64],
        "capability_id": str(value.get("capability_id") or "")[:96],
        "field_ids": [
            str(item)[:80]
            for item in (value.get("field_ids") or [])[:16]
            if str(item).strip()
        ],
    }
    if result["schema_version"] == "spatial-agent.composite-clarification-continuation.v1":
        result["component_ids"] = [
            str(item)[:96]
            for item in (value.get("component_ids") or [])[:8]
            if str(item).strip()
        ]
        result["domain_ids"] = [
            str(item)[:64]
            for item in (value.get("domain_ids") or [])[:8]
            if str(item).strip()
        ]
        result["components"] = [
            {
                "component_id": str(item.get("component_id") or "")[:96],
                "domain_id": str(item.get("domain_id") or "")[:64],
                "capability_id": str(item.get("capability_id") or "")[:96],
            }
            for item in (value.get("components") or [])[:8]
            if isinstance(item, Mapping)
        ]
        result.pop("component_id", None)
        result.pop("domain_id", None)
        result.pop("capability_id", None)
        result.pop("field_ids", None)
    return result


def _project_analysis_intents(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Publish only normalized Domain intent receipts."""

    result: list[dict[str, Any]] = []
    for raw in (context.get("domain_contexts") or [])[:8]:
        if not isinstance(raw, Mapping) or raw.get("analysis_intent") is None:
            continue
        try:
            intent = normalize_analysis_intent(raw.get("analysis_intent"))
        except AnalysisIntentError:
            continue
        result.append(
            {
                "domain_id": str(raw.get("domain_id") or "")[:64],
                "intent": intent,
            }
        )
    return result


def _planner_evidence(
    candidate: Mapping[str, Any],
    *,
    planner_source: str,
    schema_status: str,
    component_count: int,
    request_fingerprint: Any,
    requested_planner: Any = None,
    selection_state: str = "unavailable",
    selection_reason: Any = None,
    selected_capability_ids: Any = None,
    candidate_count: int = 0,
    task_plan_bridge: Any = None,
    provider_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    compatibility = _safe_compatibility(candidate.get("compatibility"))
    fingerprint = str(request_fingerprint or "").strip()[:128] or None
    result = {
        "schema_version": COMPOSITE_PLANNER_EVIDENCE_SCHEMA_VERSION,
        "planner_source": str(planner_source or "unknown")[:32],
        "schema_status": str(schema_status or "unknown")[:32],
        "component_count": max(0, min(8, int(component_count))),
        "request_fingerprint": fingerprint,
        "compatibility": compatibility,
        "selection": _planner_selection_evidence(
            requested_planner=requested_planner,
            selected_source=planner_source,
            state=selection_state,
            reason_code=selection_reason,
            selected_capability_ids=selected_capability_ids,
            selected_capability_keys=_capability_keys(candidate.get("components")),
            candidate_count=candidate_count,
        ),
    }
    if isinstance(task_plan_bridge, Mapping):
        result["task_plan_bridge"] = project_task_plan_bridge(task_plan_bridge)
    structured_output = project_structured_output_evidence(provider_metrics)
    if structured_output is not None:
        result["structured_output"] = structured_output
    provider_runtime = project_provider_runtime_evidence(provider_metrics)
    if provider_runtime is not None:
        result["provider_runtime"] = provider_runtime
    provider_stage = (
        provider_metrics.get("projection_stage")
        if isinstance(provider_metrics, Mapping)
        else None
    )
    planner_attempt = build_planner_attempt_receipt(
        provider_metrics,
        stage=provider_stage
        or ("selection" if str(planner_source or "") == "llm" else "discovery"),
        outcome=_planner_attempt_outcome(
            schema_status=schema_status,
            selection_state=selection_state,
            provider_metrics=provider_metrics,
        ),
        reason_code=selection_reason,
    )
    if planner_attempt is not None:
        result["planner_attempt"] = planner_attempt
    return result


def _planner_attempt_outcome(
    *,
    schema_status: Any,
    selection_state: Any,
    provider_metrics: Mapping[str, Any] | None,
) -> str | None:
    """Keep provider completion separate from the planner's semantic outcome."""

    if str(schema_status or "") == "valid":
        return "success"
    state = str(selection_state or "").strip().lower()
    if state == "clarification":
        return "needs_clarification"
    if state in {"rejected", "failed"}:
        metrics = provider_metrics if isinstance(provider_metrics, Mapping) else {}
        if metrics.get("error_type") or str(metrics.get("status") or "").lower() in {
            "error",
            "failed",
            "timed_out",
        }:
            return "provider_failure"
        return "rejected"
    return None


def _provider_projection_stage(
    evidence: Mapping[str, Any], envelope: Mapping[str, Any]
) -> str:
    """Describe the stage actually used by the planner adapter."""

    lineage = evidence.get("repair_lineage")
    if isinstance(lineage, Mapping) and bool(lineage.get("attempted")):
        return "repair"
    if str(evidence.get("planner_source") or "") == "llm":
        return "selection"
    # Rule and Replay are local adapters and do not cross the provider
    # boundary; their shared context was produced from the discovery stage.
    return str(envelope.get("projection_stage") or "discovery")[:24]


def _safe_planner_metrics(planner: Any) -> Mapping[str, Any] | None:
    metrics = getattr(planner, "metrics", None)
    if not callable(metrics):
        return None
    try:
        value = metrics()
    except Exception:
        return None
    return value if isinstance(value, Mapping) else None


def _planner_selection_evidence(
    *,
    requested_planner: Any,
    selected_source: Any,
    state: Any,
    reason_code: Any,
    selected_capability_ids: Any,
    selected_capability_keys: Any,
    candidate_count: Any,
) -> dict[str, Any]:
    """Build the bounded planner/source decision shared by every outcome."""

    allowed_states = {"selected", "clarification", "rejected", "failed", "unavailable"}
    normalized_state = str(state or "unavailable").strip().lower()
    if normalized_state not in allowed_states:
        normalized_state = "unavailable"
    capability_ids: list[str] = []
    values = selected_capability_ids if isinstance(selected_capability_ids, (list, tuple, set)) else []
    for value in values:
        text = str(value or "").strip()[:96]
        if text and text not in capability_ids:
            capability_ids.append(text)
        if len(capability_ids) >= 8:
            break
    capability_keys: list[str] = []
    key_values = (
        selected_capability_keys
        if isinstance(selected_capability_keys, (list, tuple, set))
        else []
    )
    for value in key_values:
        text = str(value or "").strip()[:140]
        if text and text not in capability_keys:
            capability_keys.append(text)
        if len(capability_keys) >= 8:
            break
    try:
        bounded_count = max(0, min(64, int(candidate_count)))
    except (TypeError, ValueError):
        bounded_count = 0
    return {
        "schema_version": COMPOSITE_PLANNER_SELECTION_SCHEMA_VERSION,
        "state": normalized_state,
        "requested_planner": str(requested_planner or "unknown").strip()[:32] or "unknown",
        "selected_source": str(selected_source or "unknown").strip()[:32] or "unknown",
        "reason_code": str(reason_code or "planner_selection_unavailable").strip()[:96],
        "selected_capability_ids": capability_ids,
        "selected_capability_keys": capability_keys,
        "candidate_count": bounded_count,
    }


def _capability_keys(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        domain_id = str(item.get("domain_id") or "").strip()
        capability_id = str(item.get("capability_id") or "").strip()
        if not domain_id or not capability_id:
            continue
        key = f"{domain_id}::{capability_id}"[:140]
        if key not in result:
            result.append(key)
        if len(result) >= 8:
            break
    return result


def _selection_state_for_status(status: str) -> str:
    normalized = str(status or "").upper()
    if normalized == "NEEDS_CLARIFICATION":
        return "clarification"
    if normalized == "REJECTED":
        return "rejected"
    return "unavailable"


_PLANNING_CLARIFICATION_CODES = frozenset(
    {
        "planner_context_too_large",
        "plan_components_required",
        "capability_unavailable",
        "taskplan_component_clarification",
        "taskplan_composite_clarification",
        "component_facts_missing",
    }
)


def _planning_failure_projection(code: Any, *, status: Any) -> dict[str, Any]:
    """Project a planning gate without exposing exception text or payloads."""

    reason_code = str(code or "planning_application_failed").strip()[:96]
    if reason_code in _PLANNING_CLARIFICATION_CODES or str(status or "").upper() == "NEEDS_CLARIFICATION":
        state = "clarification"
        next_actions = ["补充信息后重新提交"]
    elif reason_code == "taskplan_component_preview_invalid":
        state = "preview_invalid"
        next_actions = ["检查领域返回的计划格式后重试"]
    elif reason_code == "taskplan_component_preview_failed":
        state = "preview_failed"
        next_actions = ["检查数据或领域服务状态后重试"]
    elif reason_code.startswith("execution_binding_"):
        state = "binding_failed"
        next_actions = ["重新生成计划后重试"]
    else:
        state = "rejected"
        next_actions = ["调整问题后重新提交"]
    return {
        "schema_version": "spatial-agent.planning-failure.v1",
        "state": state,
        "code": reason_code,
        "phase": "planning",
        "retryable": False,
        "execution_run_created": False,
        "next_actions": next_actions,
    }


def _selection_reason_for_candidate(candidate: Mapping[str, Any], status: str) -> str:
    validation = candidate.get("validation") if isinstance(candidate, Mapping) else None
    if isinstance(validation, Mapping) and validation.get("reason_code"):
        return str(validation["reason_code"])[:96]
    return "planner_outcome_" + str(status or "unavailable").lower()[:64]


def _context_candidate_count(context: Mapping[str, Any]) -> int:
    values = context.get("capability_index") if isinstance(context, Mapping) else None
    return len(values) if isinstance(values, list) else 0


def _call_catalog(service: Any, *, planner: str, backend: str) -> Mapping[str, Any]:
    resolver = getattr(service, "capabilities", None)
    if not callable(resolver):
        raise ValueError("Domain service does not expose capabilities()")
    value = resolver(planner=planner, backend=backend)
    if not isinstance(value, Mapping):
        raise ValueError("Domain capability catalog must be an object")
    return value


def _call_workflow(service: Any, *, planner: str, backend: str) -> Mapping[str, Any]:
    resolver = getattr(service, "workflow_contract", None)
    if not callable(resolver):
        return {"catalog": {}, "known_tools": [], "known_result_types": []}
    value = resolver(planner=planner, backend=backend)
    return value if isinstance(value, Mapping) else {}


def _call_execution_contract(
    service: Any, *, planner: str, backend: str
) -> Mapping[str, Any]:
    """Read the optional structural Runtime contract without executing tools."""

    resolver = getattr(service, "execution_contract", None)
    if not callable(resolver):
        return {}
    value = resolver(planner=planner, backend=backend)
    return value if isinstance(value, Mapping) else {}


def _call_runtime_capabilities(
    service: Any, *, planner: str, backend: str
) -> Mapping[str, Any]:
    """Read bounded current data readiness when a Domain exposes it."""

    resolver = getattr(service, "runtime_capabilities", None)
    if not callable(resolver):
        return {}
    try:
        value = resolver(max_files=2, planner=planner, backend=backend)
    except TypeError:
        # Keep compatibility with older services that only accept max_files.
        try:
            value = resolver(max_files=2)
        except Exception:
            return {}
    except Exception:
        return {}
    return value if isinstance(value, Mapping) else {}


def _project_capability(value: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for field in _SAFE_CAPABILITY_FIELDS:
        if field not in value:
            continue
        if field in {
            "datasets",
            "tools",
            "result_types",
            "analysis_operations",
            "missing_datasets",
            "derived_datasets",
            "workflow_ids",
        }:
            projected[field] = _bounded_strings(value.get(field))
        elif field == "available":
            projected[field] = bool(value.get(field))
        else:
            projected[field] = _bounded_text(value.get(field))
    capability_id = str(projected.get("id") or "").strip()
    if not capability_id:
        raise ValueError("capability id is required")
    projected["request_requirements"] = _project_requirements(
        value.get("request_requirements")
    )
    return projected


def _project_workflow(key: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    workflow_id = str(value.get("id") or key or "").strip()
    if not workflow_id:
        raise ValueError("workflow id is required")
    return {
        "id": workflow_id[:96],
        "label": _bounded_text(value.get("label")),
        "description": _bounded_text(value.get("description")),
        "allowed_tools": _bounded_strings(value.get("allowed_tools")),
        "result_types": _bounded_strings(value.get("result_types")),
        "input_profiles": _project_profile_list(value.get("input_profiles")),
        "output_profiles": _project_profile_list(value.get("output_profiles")),
        "steps": [
            {
                "id": _bounded_text(step.get("id")),
                "tool": _bounded_text(step.get("tool")),
                "depends_on": _bounded_strings(step.get("depends_on")),
            }
            for step in (value.get("step_blueprint") or [])[:16]
            if isinstance(step, Mapping)
        ],
    }


def _project_execution_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the bounded closure facts needed by catalog readiness."""

    if not isinstance(value, Mapping) or not value:
        return {}
    tool_definitions = value.get("tool_definitions")
    tool_names = _bounded_strings(value.get("tool_names"), limit=64)
    if isinstance(tool_definitions, Mapping):
        tool_names = _bounded_strings(
            list(tool_names) + list(tool_definitions.keys()), limit=64
        )
    result = {
        "schema_version": _bounded_text(value.get("schema_version"), 96),
        "status": _bounded_text(value.get("status"), 24) or "unknown",
        "domain_id": _bounded_text(value.get("domain_id"), 64),
        "tool_names": tool_names,
        "result_type_ids": _bounded_strings(value.get("result_type_ids"), limit=64),
    }
    if isinstance(value.get("tool_definitions"), Mapping):
        result["tool_schema_count"] = min(64, len(value["tool_definitions"]))
    result["result_profiles"] = _project_result_profiles(value.get("result_profiles"))
    if value.get("result_registry_schema_version"):
        result["result_registry_schema_version"] = _bounded_text(
            value.get("result_registry_schema_version"), 96
        )
    return result


def _project_result_profiles(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for result_type, raw in list(value.items())[:64]:
        if not isinstance(raw, Mapping):
            continue
        kinds = _bounded_strings(raw.get("kinds"), limit=8)
        primary = _bounded_text(raw.get("primary"), 32)
        if not kinds:
            kinds = [primary or "unknown"]
        if primary not in kinds:
            primary = kinds[0]
        result[_bounded_text(result_type, 96)] = {
            "schema_version": _bounded_text(raw.get("schema_version"), 96)
            or "spatial-agent.data-profile.v1",
            "primary": primary,
            "kinds": kinds,
        }
    return {key: value for key, value in result.items() if key}


def _profiles_for_results(value: Any, profiles: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for result_type in _bounded_strings(value, limit=24):
        profile = profiles.get(result_type)
        if not isinstance(profile, Mapping):
            continue
        result.append({"result_type": result_type, **dict(profile)})
    return result[:24]


def _project_operation_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project operation/profile closure without exposing planner internals."""

    status = str(value.get("status") or "unknown")
    if status not in {"ready", "invalid", "unknown", "not_applicable", "not_declared"}:
        status = "unknown"
    result = {
        "schema_version": str(
            value.get("schema_version") or "spatial-agent.operation-binding.v1"
        )[:96],
        "status": status,
        "reason_code": str(value.get("reason_code") or "operation_binding_unknown")[:96],
        "operations": _bounded_strings(value.get("operations"), limit=8),
        "workflow_ids": _bounded_strings(value.get("workflow_ids"), limit=8),
        "result_types": _bounded_strings(value.get("result_types"), limit=16),
    }
    profiles = []
    for raw in (value.get("output_profiles") or [])[:16]:
        if not isinstance(raw, Mapping):
            continue
        profiles.append(
            {
                "result_type": _bounded_text(raw.get("result_type"), 96),
                "primary": _bounded_text(raw.get("primary"), 32),
                "kinds": _bounded_strings(raw.get("kinds"), limit=8),
            }
        )
    if profiles:
        result["output_profiles"] = profiles
    for field in ("missing_result_profiles", "invalid_operations"):
        values = _bounded_strings(value.get(field), limit=8)
        if values:
            result[field] = values
    return result


def _project_profile_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for raw in list(value)[:24]:
        if not isinstance(raw, Mapping):
            continue
        name = _bounded_text(raw.get("name") or raw.get("input"), 64)
        kinds = _bounded_strings(raw.get("kinds") or raw.get("data_kinds"), limit=8)
        if not kinds:
            continue
        item = {"kinds": kinds}
        if name:
            item["name"] = name
        result.append(item)
    return result


def _project_requirements(value: Any) -> dict[str, Any]:
    return project_request_requirements(value, max_fields=16, source=None)


def _project_readiness(value: Any) -> dict[str, Any]:
    return project_data_readiness(value)


def _selected_domain_ids(
    requested: Sequence[str] | None,
    host_catalog: Mapping[str, Any],
    *,
    max_domains: int,
) -> list[str]:
    source = requested
    if source is None:
        source = host_catalog.get("domain_ids") or [
            item.get("id")
            for item in (host_catalog.get("domains") or [])
            if isinstance(item, Mapping)
        ]
    if isinstance(source, str) or not isinstance(source, Sequence):
        raise ValueError("domain_ids must be a bounded list")
    result: list[str] = []
    for value in source:
        domain_id = str(value or "").strip().lower()
        if not domain_id or domain_id in result:
            continue
        result.append(domain_id)
    if not result:
        raise ValueError("at least one domain is required")
    if len(result) > max_domains:
        raise ValueError("domain_ids exceeds max_domains")
    return sorted(result)


def _aggregate_readiness(values: Any) -> str:
    statuses = {str(value or "unknown") for value in values}
    if statuses and statuses <= {"ready"}:
        return "ready"
    if "partial" in statuses or "ready" in statuses:
        return "partial"
    if "unavailable" in statuses:
        return "unavailable"
    return "unknown"


def _bounded_strings(value: Any, limit: int = 32) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()[:160]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _bounded_text(value: Any, limit: int = 320) -> str:
    return str(value or "").strip()[:limit]


def _positive_limit(value: Any, name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(name + " must be positive") from exc
    if normalized < 1:
        raise ValueError(name + " must be positive")
    return normalized


def _call_optional_binding(method: Any, value: Any, *, execution_binding: Any, **kwargs: Any) -> Any:
    """Call old injected run ports without weakening the production seam."""

    if execution_binding is not None:
        try:
            parameters = inspect.signature(method).parameters
            accepts = "execution_binding" in parameters or any(
                item.kind == inspect.Parameter.VAR_KEYWORD
                for item in parameters.values()
            )
        except (TypeError, ValueError):
            accepts = True
        if accepts:
            kwargs["execution_binding"] = execution_binding
    return method(value, **kwargs)


__all__ = [
    "COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION",
    "CompositeCapabilityProjector",
]
