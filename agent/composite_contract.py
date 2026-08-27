"""Domain-neutral request/result/evidence seam for cross-Domain composition.

This module deliberately knows nothing about GIS, Economic, tools, or data
paths.  A future coordinator may execute each normalized component through
the existing DomainRuntimeHost and AgentService instances; this seam only
defines how that coordinator describes work and publishes one bounded result.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from agent.artifact_reference import build_artifact_reference
from agent.contract_versions import (
    COMPOSITE_EVIDENCE_SCHEMA_VERSION,
    COMPOSITE_REQUEST_SCHEMA_VERSION,
    COMPOSITE_RESULT_SCHEMA_VERSION,
    RESULT_ENVELOPE_SCHEMA_VERSION,
    VIEWS_SCHEMA_VERSION,
    VIEW_SCHEMA_VERSION,
    WORKSPACE_SCHEMA_VERSION,
)
from agent.data_kinds import (
    SUPPORTED_DATA_KINDS,
    build_data_profile,
    normalize_data_profile,
)
from agent.analysis_intent import SUPPORTED_ANALYSIS_OPERATIONS
from agent.result_registry import ResultContractRegistry, ResultTypeSpec, ViewSpec
from agent.runtime_core.composition import (
    CompositionError,
    normalize_component_inputs,
    project_component_inputs,
    validate_component_composition,
)


COMPOSITE_RESULT_TYPE = "composite_result"
MAX_COMPONENTS = 8
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")
_DOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_STATUS_VALUES = {"completed", "partial", "blocked", "failed"}


class CompositeContractError(ValueError):
    """A Composite request or result cannot cross the public boundary."""

    def __init__(self, message: str, *, code: str = "composite_contract_invalid"):
        self.code = str(code)[:96]
        super().__init__(message)


def normalize_composite_request(
    value: Any,
    *,
    allow_legacy: bool = False,
) -> dict[str, Any]:
    """Normalize a bounded component DAG without selecting any Domain."""

    if not isinstance(value, Mapping):
        raise CompositeContractError(
            "composite request must be an object",
            code="composite_request_object_required",
        )
    version = value.get("schema_version")
    if version in (None, ""):
        if not allow_legacy:
            raise CompositeContractError(
                "composite request schema version is required",
                code="composite_request_schema_missing",
            )
        version = COMPOSITE_REQUEST_SCHEMA_VERSION
    if str(version) != COMPOSITE_REQUEST_SCHEMA_VERSION:
        raise CompositeContractError(
            "unknown composite request schema version",
            code="composite_request_schema_unknown",
        )
    request = _required_text(value.get("request"), 2000, "request")
    raw_components = value.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise CompositeContractError(
            "composite request requires components",
            code="composite_components_required",
        )
    if len(raw_components) > MAX_COMPONENTS:
        raise CompositeContractError(
            "composite request exceeds component limit",
            code="composite_components_limit",
        )

    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_components):
        if not isinstance(raw, Mapping):
            raise CompositeContractError(
                f"component {index} must be an object",
                code="composite_component_object_required",
            )
        component_id = _identifier(raw.get("component_id"), "component_id")
        if component_id in seen:
            raise CompositeContractError(
                "duplicate composite component id",
                code="composite_component_duplicate",
            )
        seen.add(component_id)
        domain_id = _identifier(raw.get("domain_id"), "domain_id", pattern=_DOMAIN_PATTERN)
        component_request = _required_text(raw.get("request"), 2000, "component request")
        planner = _optional_text(raw.get("planner"), 32, fallback="rule")
        backend = _optional_text(raw.get("backend"), 32, fallback="memory")
        session_id = _optional_text(raw.get("session_id"), 160, fallback="")
        raw_dependencies = raw.get("depends_on", [])
        if not isinstance(raw_dependencies, list) or len(raw_dependencies) > MAX_COMPONENTS:
            raise CompositeContractError(
                "component dependencies must be a bounded list",
                code="composite_dependencies_invalid",
            )
        depends_on: list[str] = []
        for dependency in raw_dependencies:
            dependency_id = _identifier(dependency, "depends_on")
            if dependency_id == component_id or dependency_id in depends_on:
                raise CompositeContractError(
                    "component dependency is duplicated or self-referential",
                    code="composite_dependency_invalid",
                )
            depends_on.append(dependency_id)
        item: dict[str, Any] = {
            "component_id": component_id,
            "domain_id": domain_id,
            "request": component_request,
            "planner": planner,
            "backend": backend,
            "required": _required_flag(raw, "required"),
            "depends_on": depends_on,
        }
        if raw.get("analysis_operations") is not None:
            item["analysis_operations"] = _normalize_analysis_operations(
                raw.get("analysis_operations")
            )
        if raw.get("inputs") is not None:
            try:
                item["inputs"] = normalize_component_inputs(raw.get("inputs"))
            except CompositionError as exc:
                raise CompositeContractError(str(exc), code=exc.code) from exc
        if session_id:
            item["session_id"] = session_id
        if raw.get("workflow") is not None:
            if not isinstance(raw.get("workflow"), Mapping):
                raise CompositeContractError(
                    "component workflow must be an object",
                    code="composite_workflow_invalid",
                )
            item["workflow"] = _bounded_value(raw.get("workflow"), depth=0)
            _assert_json_size(item["workflow"], 24000, "component workflow")
        components.append(item)

    known = {item["component_id"] for item in components}
    for item in components:
        missing = [dependency for dependency in item["depends_on"] if dependency not in known]
        if missing:
            raise CompositeContractError(
                "component dependency does not exist",
                code="composite_dependency_missing",
            )
    _assert_acyclic(components)
    try:
        validate_component_composition(components)
    except CompositionError as exc:
        raise CompositeContractError(str(exc), code=exc.code) from exc
    canonical = {
        "schema_version": COMPOSITE_REQUEST_SCHEMA_VERSION,
        "request": request,
        "components": components,
    }
    encoded = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    canonical["fingerprint"] = "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return canonical


def inherit_composite_runtime_selection(
    value: Any,
    *,
    planner: Any,
    backend: Any,
) -> Any:
    """Apply one product runtime selection to every composite component.

    Planner output is not allowed to introduce a different runtime selection.
    The copy is intentionally shallow outside ``components`` and does not
    mutate the caller's request. Structural validation remains owned by
    :func:`normalize_composite_request`.
    """

    if not isinstance(value, Mapping):
        return value
    components = value.get("components")
    if not isinstance(components, list):
        return dict(value)
    selected_planner = str(planner or "rule").strip()[:32]
    selected_backend = str(backend or "memory").strip()[:32]
    copied = dict(value)
    copied["components"] = [
        (
            {
                **dict(component),
                "planner": selected_planner,
                "backend": selected_backend,
            }
            if isinstance(component, Mapping)
            else component
        )
        for component in components
    ]
    return copied


def build_composite_result_contract(
    request: Mapping[str, Any],
    children: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    run_id: str | None = None,
    answer: str | None = None,
    execution_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate child run envelopes into one standard public Result."""

    composite_request = normalize_composite_request(request, allow_legacy=True)
    child_lookup = _child_lookup(children)
    components: list[dict[str, Any]] = []
    child_views: dict[str, dict[str, Any]] = {}
    for spec in composite_request["components"]:
        component_id = spec["component_id"]
        child = child_lookup.get(component_id)
        projected = _project_component(spec, child)
        components.append(projected)
        _collect_child_views(component_id, spec["domain_id"], child, child_views)

    state = _aggregate_state(components)
    profile = _aggregate_profile(components)
    evidence = _build_composite_evidence(components, state)
    composite_section = {
        "schema_version": COMPOSITE_RESULT_SCHEMA_VERSION,
        "request": {
            "schema_version": composite_request["schema_version"],
            "fingerprint": composite_request["fingerprint"],
            "component_ids": [item["component_id"] for item in composite_request["components"]],
        },
        "state": state,
        "component_count": len(components),
        "components": components,
        "evidence": evidence,
    }
    if isinstance(execution_binding, Mapping):
        composite_section["request"]["execution_binding"] = {
            "schema_version": str(execution_binding.get("schema_version") or "")[:96],
            "binding_fingerprint": str(execution_binding.get("binding_fingerprint") or "")[:128],
            "component_ids": [
                str(item)[:48]
                for item in (execution_binding.get("component_ids") or [])[:MAX_COMPONENTS]
            ],
        }
        evidence["execution_binding"] = {
            "schema_version": str(execution_binding.get("schema_version") or "")[:96],
            "binding_fingerprint": str(execution_binding.get("binding_fingerprint") or "")[:128],
        }
    composite_id = _optional_text(run_id, 160, fallback="")
    if not composite_id:
        composite_id = "composite-" + composite_request["fingerprint"].split(":", 1)[-1][:24]
    payload = {
        "run_id": composite_id,
        "request": composite_request["request"],
        "status": _public_status(state),
        "result_type": COMPOSITE_RESULT_TYPE,
        "answer": str(answer or _default_answer(state, components))[:1200],
        "plan": _synthetic_plan(composite_request),
        "steps": _synthetic_steps(components),
        "_composite": composite_section,
    }
    registry = _composite_registry(
        lambda **_kwargs: _build_composite_views(
            components,
            child_views,
            state=state,
        )
    )
    # Import lazily to keep the public result builder independent from the
    # module import order used by the legacy root result_contract module.
    from result_contract import build_result_contract

    result = build_result_contract(payload, registry=registry)
    # The common result builder derives the profile from the registry.  The
    # Composite profile is a union of actual children, so overwrite it only
    # after the generic envelope is built and validate it again below.
    result["data_profile"] = profile
    result["composite"] = composite_section
    result["views"] = _build_composite_views(components, child_views, state=state)
    from agent.evidence_registry import build_evidence_registry
    from agent.evidence_projection import project_evidence_recovery

    result["evidence_registry"] = build_evidence_registry({"result": result, "status": payload["status"]}, custom_entries=registry.evidence_specs_for(COMPOSITE_RESULT_TYPE))
    result["evidence_recovery"] = project_evidence_recovery({"result": result})
    from agent.nested_schema import normalize_result_contract

    return normalize_result_contract(result)


def normalize_composite_section(value: Any, *, allow_legacy: bool = True) -> dict[str, Any]:
    """Validate a persisted Composite section without interpreting domains."""

    if not isinstance(value, Mapping):
        raise CompositeContractError(
            "composite section must be an object",
            code="composite_section_object_required",
        )
    version = value.get("schema_version")
    if version in (None, "") and allow_legacy:
        version = COMPOSITE_RESULT_SCHEMA_VERSION
    if str(version) != COMPOSITE_RESULT_SCHEMA_VERSION:
        raise CompositeContractError(
            "unknown composite result schema version",
            code="composite_result_schema_unknown",
        )
    components = value.get("components")
    if not isinstance(components, list) or len(components) > MAX_COMPONENTS:
        raise CompositeContractError(
            "composite result components are invalid",
            code="composite_result_components_invalid",
        )
    normalized_components = []
    seen: set[str] = set()
    for raw in components:
        if not isinstance(raw, Mapping):
            raise CompositeContractError(
                "composite result component is invalid",
                code="composite_result_component_invalid",
            )
        component_id = _identifier(raw.get("component_id"), "component_id")
        if component_id in seen:
            raise CompositeContractError(
                "composite result component is duplicated",
                code="composite_result_component_duplicate",
            )
        seen.add(component_id)
        item = {
            "component_id": component_id,
            "domain_id": _identifier(raw.get("domain_id"), "domain_id", pattern=_DOMAIN_PATTERN),
            "required": bool(raw.get("required", True)),
            "depends_on": _string_list(raw.get("depends_on")),
            "status": _optional_text(raw.get("status"), 32, fallback="UNAVAILABLE"),
            "state": _state(raw.get("state")),
            "result_type": _optional_text(raw.get("result_type"), 96, fallback="unknown"),
            "data_profile": _safe_profile(raw.get("data_profile")),
            "answer": _optional_text(raw.get("answer"), 1200, fallback=""),
            "view_refs": [str(item)[:96] for item in (raw.get("view_refs") or [])[:16] if isinstance(item, str)],
        }
        if raw.get("inputs") is not None:
            try:
                item["inputs"] = normalize_component_inputs(raw.get("inputs"))
            except CompositionError as exc:
                raise CompositeContractError(str(exc), code=exc.code) from exc
        if isinstance(raw.get("execution"), Mapping):
            item["execution"] = {
                "schema_version": str(raw["execution"].get("schema_version") or "")[:96],
                "binding_fingerprint": str(raw["execution"].get("binding_fingerprint") or "")[:128],
                "plan_fingerprint": str(raw["execution"].get("plan_fingerprint") or "")[:128],
                "step_ids": [str(value)[:48] for value in (raw["execution"].get("step_ids") or [])[:16]],
            }
        for key in ("failure", "degradation", "artifact", "evidence", "input_evidence"):
            if isinstance(raw.get(key), Mapping):
                item[key] = _bounded_value(raw[key], depth=0)
        normalized_components.append(item)
    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping):
        raise CompositeContractError(
            "composite evidence is required",
            code="composite_evidence_missing",
        )
    normalized_evidence = _normalize_evidence(evidence, normalized_components)
    try:
        validate_component_composition(normalized_components)
    except CompositionError as exc:
        raise CompositeContractError(str(exc), code=exc.code) from exc
    state = _state(value.get("state"))
    return {
        "schema_version": COMPOSITE_RESULT_SCHEMA_VERSION,
        "request": _bounded_value(value.get("request") or {}, depth=0),
        "state": state,
        "component_count": len(normalized_components),
        "components": normalized_components,
        "evidence": normalized_evidence,
    }


def _project_component(spec: Mapping[str, Any], child: Any) -> dict[str, Any]:
    payload = child if isinstance(child, Mapping) else {}
    nested = payload.get("result") if isinstance(payload.get("result"), Mapping) else payload
    nested = nested if isinstance(nested, Mapping) else {}
    raw_status = payload.get("status") or nested.get("status") or "UNAVAILABLE"
    status = str(raw_status)[:32]
    state = _component_state(status, child_available=bool(child))
    reported_domain = str(payload.get("domain_id") or nested.get("domain_id") or "").strip()
    if reported_domain and reported_domain != spec["domain_id"]:
        state = "blocked"
    profile = _safe_profile(nested.get("data_profile") or payload.get("data_profile"))
    result_type = str(nested.get("type") or payload.get("result_type") or "unknown")[:96]
    component: dict[str, Any] = {
        "component_id": spec["component_id"],
        "domain_id": spec["domain_id"],
        "required": bool(spec.get("required", True)),
        "depends_on": _string_list(spec.get("depends_on")),
        "status": status,
        "state": state,
        "result_type": result_type,
        "data_profile": profile,
        "answer": str(
            payload.get("answer")
            or nested.get("summary")
            or nested.get("answer")
            or ""
        )[:1200],
        "view_refs": [],
    }
    inputs = project_component_inputs(spec.get("inputs"))
    if inputs:
        component["inputs"] = inputs
    if reported_domain and reported_domain != spec["domain_id"]:
        component["failure"] = {
            "code": "component_domain_mismatch",
            "message": "子结果的 Domain 身份与请求组件不一致。",
        }
    if not child:
        component["failure"] = {
            "code": "component_result_unavailable",
            "message": "组件没有返回可用结果。",
        }
    error = payload.get("error") or nested.get("error")
    if error:
        component["failure"] = {
            "code": str(payload.get("error_code") or nested.get("code") or "component_failed")[:96],
            "category": str(payload.get("error_category") or "")[:64],
            "message": str(error)[:320],
        }
    degradation = nested.get("degradation") or payload.get("degradation")
    if isinstance(degradation, Mapping):
        component["degradation"] = _project_degradation(degradation)
    artifact_ref = payload.get("artifact_ref")
    if not artifact_ref:
        artifacts = nested.get("artifacts")
        if isinstance(artifacts, Mapping) and isinstance(artifacts.get("run"), Mapping):
            artifact_ref = artifacts["run"].get("ref")
    artifact = build_artifact_reference(
        artifact_ref,
        kind="run",
        domain_id=spec["domain_id"],
        status="available" if artifact_ref else "unavailable",
    )
    if artifact.get("available"):
        component["artifact"] = artifact
    evidence_registry = nested.get("evidence_registry") or payload.get("evidence_registry")
    component["evidence"] = _evidence_summary(evidence_registry, nested)
    execution = payload.get("_execution_evidence") or nested.get("execution")
    if isinstance(execution, Mapping):
        component["execution"] = {
            "schema_version": str(execution.get("schema_version") or "")[:96],
            "binding_fingerprint": str(execution.get("binding_fingerprint") or "")[:128],
            "plan_fingerprint": str(execution.get("plan_fingerprint") or "")[:128],
            "step_ids": [str(value)[:48] for value in (execution.get("step_ids") or [])[:16]],
        }
    input_evidence = payload.get("_component_input_evidence") or nested.get(
        "input_evidence"
    )
    if isinstance(input_evidence, Mapping):
        component["input_evidence"] = {
            "schema_version": str(input_evidence.get("schema_version") or "")[:96],
            "state": str(input_evidence.get("state") or "unknown")[:32],
            "input_names": [
                str(value)[:160]
                for value in (input_evidence.get("input_names") or [])[:8]
                if isinstance(value, str)
            ],
        }
    return component


def _build_composite_evidence(components: Sequence[Mapping[str, Any]], state: str) -> dict[str, Any]:
    complete = [item["component_id"] for item in components if item.get("state") == "completed"]
    failed = [item["component_id"] for item in components if item.get("state") == "failed"]
    blocked = [item["component_id"] for item in components if item.get("state") == "blocked"]
    pending = [item["component_id"] for item in components if item.get("state") == "pending"]
    artifacts = [item["artifact"] for item in components if isinstance(item.get("artifact"), Mapping) and item["artifact"].get("available")]
    return {
        "schema_version": COMPOSITE_EVIDENCE_SCHEMA_VERSION,
        "state": state,
        "component_count": len(components),
        "completed_component_ids": complete[:MAX_COMPONENTS],
        "failed_component_ids": failed[:MAX_COMPONENTS],
        "blocked_component_ids": blocked[:MAX_COMPONENTS],
        "pending_component_ids": pending[:MAX_COMPONENTS],
        "artifact_references": artifacts[:MAX_COMPONENTS],
        "component_evidence": [
            {
                "component_id": item["component_id"],
                "domain_id": item["domain_id"],
                "state": item["state"],
                "available": bool((item.get("evidence") or {}).get("available")),
                "entry_count": (item.get("evidence") or {}).get("entry_count", 0),
                "input_state": (item.get("input_evidence") or {}).get("state"),
            }
            for item in components
        ],
    }


def _build_composite_views(
    components: Sequence[Mapping[str, Any]],
    child_views: Mapping[str, Mapping[str, Any]],
    *,
    state: str,
) -> dict[str, Any]:
    panels: dict[str, dict[str, Any]] = {
        "composite": {
            "schema_version": VIEW_SCHEMA_VERSION,
            "kind": "composite",
            "view_id": "composite",
            "title": "组合分析",
            "state": state,
            "components": [
                {
                    "component_id": item["component_id"],
                    "domain_id": item["domain_id"],
                    "state": item["state"],
                    "result_type": item["result_type"],
                    "data_profile": item["data_profile"],
                    "answer": item.get("answer", ""),
                    "view_refs": item.get("view_refs", []),
                }
                for item in components
            ],
            "note": "各组件结果通过统一 Result、View 和 Evidence 契约汇总。",
        }
    }
    for panel_id, panel in list(child_views.items())[:16]:
        panels[panel_id] = dict(panel)
    return {"schema_version": VIEWS_SCHEMA_VERSION, "panels": panels}


def _collect_child_views(
    component_id: str,
    domain_id: str,
    child: Any,
    target: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(child, Mapping):
        return
    nested = child.get("result") if isinstance(child.get("result"), Mapping) else child
    if not isinstance(nested, Mapping):
        return
    views = nested.get("views")
    panels = views.get("panels") if isinstance(views, Mapping) else None
    if not isinstance(panels, Mapping):
        return
    for panel_id, raw_panel in list(panels.items())[:8]:
        if not isinstance(raw_panel, Mapping):
            continue
        safe_id = str(panel_id or "panel")[:64]
        output_id = f"{component_id}__{safe_id}"[:96]
        panel = _bounded_value(raw_panel, depth=0)
        if not isinstance(panel, dict):
            continue
        panel["view_id"] = output_id
        panel["component_id"] = component_id
        panel["domain_id"] = domain_id
        target[output_id] = panel


def _synthetic_plan(request: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "goal": request["request"],
        "output": {"type": COMPOSITE_RESULT_TYPE, "summary": True},
        "steps": [
            {
                "id": item["component_id"],
                "tool": "domain_run",
                "args": {"domain_id": item["domain_id"]},
                "depends_on": list(item.get("depends_on") or []),
            }
            for item in request["components"]
        ],
    }
    for step, item in zip(result["steps"], request["components"]):
        inputs = project_component_inputs(item.get("inputs"))
        if inputs:
            step["inputs"] = inputs
    return result


def _synthetic_steps(components: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item["component_id"],
            "tool": "domain_run",
            "status": item.get("status"),
            "result": {
                "status": item.get("status"),
                "data_profile": item.get("data_profile"),
            },
            "error": (item.get("failure") or {}).get("message") if isinstance(item.get("failure"), Mapping) else None,
        }
        for item in components
    ]


def _composite_registry(view_builder: Any) -> ResultContractRegistry:
    def builder(_result_type: str, **kwargs: Any) -> Mapping[str, Any]:
        del kwargs
        return view_builder()

    return ResultContractRegistry(
        {
            COMPOSITE_RESULT_TYPE: ResultTypeSpec(
                title="组合分析结果",
                panels=("composite", "generic", "evidence"),
                view_specs=(ViewSpec("composite", "generic", "组合分析"),),
                data_kinds=("composite",),
            )
        },
        fallback_title="组合分析结果",
        view_builder=builder,
        evidence_specs={
            COMPOSITE_RESULT_TYPE: (
                {
                    "id": "composite_evidence",
                    "schema_version": COMPOSITE_EVIDENCE_SCHEMA_VERSION,
                    "reference": "result.composite.evidence",
                },
            )
        },
    )


def _child_lookup(children: Any) -> dict[str, Mapping[str, Any]]:
    if isinstance(children, Mapping):
        return {str(key): value for key, value in children.items() if isinstance(value, Mapping)}
    result: dict[str, Mapping[str, Any]] = {}
    if isinstance(children, Sequence) and not isinstance(children, (str, bytes, bytearray)):
        for item in children:
            if isinstance(item, Mapping) and item.get("component_id"):
                result[str(item["component_id"])] = item
    return result


def _aggregate_profile(components: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    kinds = ["composite"]
    for kind in SUPPORTED_DATA_KINDS:
        if kind == "composite":
            continue
        if any(kind in (item.get("data_profile") or {}).get("kinds", []) for item in components):
            kinds.append(kind)
    return build_data_profile(kinds)


def _aggregate_state(components: Sequence[Mapping[str, Any]]) -> str:
    required = [item for item in components if item.get("required", True)]
    optional = [item for item in components if not item.get("required", True)]
    if not required:
        required = list(components)
    required_states = {item.get("state") for item in required}
    if required_states <= {"completed"}:
        return "completed" if all(item.get("state") == "completed" for item in optional) else "partial"
    if "failed" in required_states:
        return "failed"
    if "blocked" in required_states:
        return "blocked"
    if "pending" in required_states:
        return "pending"
    return "failed"


def _component_state(status: str, *, child_available: bool) -> str:
    if not child_available:
        return "blocked"
    normalized = str(status or "").upper()
    if normalized == "COMPLETED":
        return "completed"
    if normalized in {"QUEUED", "PLANNING", "EXECUTING"}:
        return "pending"
    if normalized in {"NEEDS_CLARIFICATION", "WAITING_FOR_DECISION"}:
        return "blocked"
    if normalized in {"FAILED", "CANCELLED", "REJECTED"}:
        return "failed"
    return "blocked"


def _public_status(state: str) -> str:
    return {
        "pending": "PLANNING",
        "completed": "COMPLETED",
        "partial": "COMPLETED",
        "blocked": "NEEDS_CLARIFICATION",
        "failed": "FAILED",
    }.get(state, "FAILED")


def _default_answer(state: str, components: Sequence[Mapping[str, Any]]) -> str:
    total = len(components)
    if state == "completed":
        return f"已完成 {total} 个分析部分，结果已整理如下。"
    if state == "partial":
        return f"已完成部分分析，共收到 {total} 个分析部分的结果；未完成部分已在使用边界中说明。"
    if state == "pending":
        return "分析正在处理中，完成后将返回结果。"
    if state == "blocked":
        return "分析暂未完成，需要补充信息或等待数据可用。"
    return "分析未完成，详细原因已保留在结果信息中。"


def _safe_profile(value: Any) -> dict[str, Any]:
    try:
        return normalize_data_profile(value, allow_legacy=True)
    except Exception:
        return build_data_profile(("unknown",))


def _evidence_summary(value: Any, nested: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"available": False, "state": "unavailable", "entry_count": 0}
    entries = value.get("entries")
    return {
        "available": bool(value.get("available")),
        "state": "available" if value.get("available") else "unavailable",
        "schema_version": str(value.get("schema_version") or "")[:96],
        "entry_count": len(entries) if isinstance(entries, list) else 0,
        "recovery_available": bool(nested.get("evidence_recovery")),
    }


def _project_degradation(value: Mapping[str, Any]) -> dict[str, Any]:
    items = value.get("items")
    projected: dict[str, Any] = {
        "state": str(value.get("state") or value.get("status") or "unknown")[:32],
        "reason_codes": [str(item)[:96] for item in (value.get("reason_codes") or [])[:8] if isinstance(item, str)],
    }
    if isinstance(items, list):
        projected["item_count"] = len(items)
        projected["items"] = [
            _bounded_value(item, depth=0)
            for item in items[:4]
            if isinstance(item, Mapping)
        ]
    return projected


def _normalize_evidence(value: Mapping[str, Any], components: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    schema = value.get("schema_version")
    if schema in (None, ""):
        schema = COMPOSITE_EVIDENCE_SCHEMA_VERSION
    if str(schema) != COMPOSITE_EVIDENCE_SCHEMA_VERSION:
        raise CompositeContractError(
            "unknown composite evidence schema version",
            code="composite_evidence_schema_unknown",
        )
    return {
        "schema_version": COMPOSITE_EVIDENCE_SCHEMA_VERSION,
        "state": _state(value.get("state")),
        "component_count": len(components),
        "completed_component_ids": _string_list(value.get("completed_component_ids")),
        "failed_component_ids": _string_list(value.get("failed_component_ids")),
        "blocked_component_ids": _string_list(value.get("blocked_component_ids")),
        "pending_component_ids": _string_list(value.get("pending_component_ids")),
        "artifact_references": [
            _bounded_value(item, depth=0)
            for item in (value.get("artifact_references") or [])[:MAX_COMPONENTS]
            if isinstance(item, Mapping)
        ],
        "component_evidence": [
            _bounded_value(item, depth=0)
            for item in (value.get("component_evidence") or [])[:MAX_COMPONENTS]
            if isinstance(item, Mapping)
        ],
    }


def _state(value: Any) -> str:
    state = str(value or "blocked").strip().lower()
    return state if state in _STATUS_VALUES or state == "pending" else "blocked"


def _string_list(value: Any) -> list[str]:
    return list(dict.fromkeys(str(item)[:48] for item in (value or [])[:MAX_COMPONENTS] if isinstance(item, str)))


def _assert_acyclic(components: Sequence[Mapping[str, Any]]) -> None:
    graph = {item["component_id"]: list(item.get("depends_on") or []) for item in components}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CompositeContractError(
                "composite component dependencies contain a cycle",
                code="composite_dependency_cycle",
            )
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _identifier(value: Any, field: str, *, pattern: re.Pattern[str] = _ID_PATTERN) -> str:
    candidate = str(value or "").strip().lower()
    if not pattern.fullmatch(candidate):
        raise CompositeContractError(
            f"{field} is invalid",
            code="composite_identifier_invalid",
        )
    return candidate


def _required_text(value: Any, limit: int, field: str) -> str:
    result = str(value or "").strip()
    if not result or len(result) > limit:
        raise CompositeContractError(
            f"{field} is required and bounded",
            code="composite_text_invalid",
        )
    return result


def _optional_text(value: Any, limit: int, *, fallback: str) -> str:
    return str(value or fallback).strip()[:limit]


def _required_flag(value: Mapping[str, Any], key: str) -> bool:
    if key not in value:
        return True
    raw = value.get(key)
    if not isinstance(raw, bool):
        raise CompositeContractError(
            f"{key} must be boolean",
            code="composite_boolean_invalid",
        )
    return raw


def _normalize_analysis_operations(value: Any) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 8:
        raise CompositeContractError(
            "analysis_operations must be a bounded non-empty list",
            code="composite_analysis_operations_invalid",
        )
    result: list[str] = []
    for item in value:
        operation = str(item or "").strip()
        if operation not in SUPPORTED_ANALYSIS_OPERATIONS:
            raise CompositeContractError(
                "analysis operation is unsupported",
                code="composite_analysis_operation_unsupported",
            )
        if operation not in result:
            result.append(operation)
    return result


def _assert_json_size(value: Any, limit: int, label: str) -> None:
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise CompositeContractError(label + " is not JSON-safe", code="composite_json_invalid") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise CompositeContractError(label + " exceeds size limit", code="composite_json_limit")


def _bounded_value(value: Any, *, depth: int) -> Any:
    if depth >= 4:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:640]
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _bounded_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
            if isinstance(key, (str, int))
        }
    if isinstance(value, (list, tuple)):
        return [_bounded_value(item, depth=depth + 1) for item in list(value)[:32]]
    return str(value)[:240]


__all__ = [
    "COMPOSITE_EVIDENCE_SCHEMA_VERSION",
    "COMPOSITE_REQUEST_SCHEMA_VERSION",
    "COMPOSITE_RESULT_SCHEMA_VERSION",
    "COMPOSITE_RESULT_TYPE",
    "CompositeContractError",
    "build_composite_result_contract",
    "normalize_composite_request",
    "normalize_composite_section",
]
