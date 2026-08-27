"""Domain-neutral user projection for a canonical Composite Result."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.composite_contract import normalize_composite_section
from agent.provider_structured_output import project_structured_output_evidence
from agent.provider_runtime import (
    project_planner_attempt_receipt,
    project_provider_runtime_evidence,
)
from agent.data_kinds import SUPPORTED_DATA_KINDS
from agent.analysis_intent import AnalysisIntentError, normalize_analysis_intent
from agent.runtime_core.composition import project_component_inputs
from agent.runtime_core.plan_receipt import project_canonical_plan_receipt
from agent.runtime_core.selection_evidence import normalize_selection_evidence


COMPOSITE_VIEW_SCHEMA_VERSION = "spatial-agent.composite-view.v1"
_MAX_COMPONENTS = 8
_MAX_VIEWS = 24
_MAX_BYTES = 2_000_000
_PRIVATE_KEYS = {
    "api_key",
    "messages",
    "model_response",
    "private_payload",
    "prompt",
    "raw_response",
    "secret",
    "source_path",
    "token",
}


class CompositeViewError(ValueError):
    """A canonical Composite Result cannot be projected safely."""


def build_composite_view_projection(
    result: Mapping[str, Any], *, answer: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Build one bounded answer/View/evidence payload for every frontend."""

    if not isinstance(result, Mapping):
        raise CompositeViewError("composite result must be an object")
    section = result.get("composite") or result.get("_composite")
    composite = normalize_composite_section(section)
    state = composite["state"]
    components = composite["components"][:_MAX_COMPONENTS]
    request = composite.get("request")
    request = request if isinstance(request, Mapping) else {}
    fingerprint = _text(request.get("fingerprint"), 128)
    execution_binding = request.get("execution_binding")
    answer = (
        _answer_override(answer)
        or _answer_override(result.get("answer_structured"))
        or _build_answer(result, state, components)
    )
    sections = _build_sections(components)
    views = _build_views(result.get("views"), state)
    evidence = _build_evidence(
        composite.get("evidence"),
        state,
        answer_generation=result.get("answer_generation_evidence"),
    )
    planning = _build_planning(result.get("planner_evidence"))
    artifacts = _collect_artifacts(composite, components)
    projection = {
        "schema_version": COMPOSITE_VIEW_SCHEMA_VERSION,
        "run_id": _text(result.get("run_id"), 160),
        "status": _status(result.get("status"), state),
        "state": state,
        "request_fingerprint": fingerprint or None,
        "data_kinds": _aggregate_data_kinds(components),
        "execution_binding": _project_execution_binding(execution_binding),
        "answer": answer,
        "sections": sections,
        "views": views,
        "evidence": evidence,
        "planning": planning,
        "artifacts": artifacts,
    }
    _fit_budget(projection)
    return projection


def _build_answer(
    result: Mapping[str, Any], state: str, components: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    headline = {
        "completed": "组合分析已完成",
        "partial": "组合分析已完成部分结果",
        "blocked": "组合分析需要补充信息",
        "failed": "组合分析未能完成",
    }.get(state, "组合分析已收到")
    summary = _text(result.get("answer"), 640)
    if (
        not summary
        or (
            summary.startswith("已完成 ")
            and "个分析组件，并汇总为一份组合结果" in summary
        )
    ):
        completed_count = sum(
            1 for item in components if item.get("state") == "completed"
        )
        summary = {
            "completed": f"已完成 {completed_count} 个分析部分，结果已整理如下。",
            "partial": f"已返回 {completed_count} 个分析部分的结果，其余部分尚未完成。",
            "blocked": "当前没有可执行的完整结果。",
            "failed": "当前没有可用的完整结果。",
        }.get(state, "请查看分析状态和证据。")
    findings = [
        _text(item.get("answer"), 320)
        for item in components
        if _text(item.get("answer"), 320)
    ]
    limitations: list[str] = []
    if state != "completed":
        limitations.append("部分组件未完成，当前结论不应视为完整分析结论。")
    for item in components:
        failure = item.get("failure")
        if isinstance(failure, Mapping):
            message = _text(failure.get("message"), 240)
            if message and message not in limitations:
                limitations.append(message)
        degradation = item.get("degradation")
        if isinstance(degradation, Mapping):
            message = _text(degradation.get("message"), 240)
            if message and message not in limitations:
                limitations.append(message)
    next_steps = _next_steps(state, limitations)
    return {
        "headline": headline,
        "summary": summary,
        "key_findings": findings[:_MAX_COMPONENTS],
        "limitations": limitations[:_MAX_COMPONENTS],
        "next_steps": next_steps,
    }


def _answer_override(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    headline = _text(value.get("headline"), 160)
    summary = _text(value.get("summary"), 800)
    if not headline or not summary:
        return None
    return {
        "headline": headline,
        "summary": summary,
        "key_findings": _safe_strings(value.get("key_findings"), _MAX_COMPONENTS),
        "limitations": _safe_strings(value.get("limitations"), _MAX_COMPONENTS),
        "next_steps": _safe_strings(value.get("next_steps"), _MAX_COMPONENTS),
    }


def _next_steps(state: str, limitations: Sequence[str]) -> list[str]:
    """Return state-level guidance without interpreting a Domain result."""

    if state == "partial":
        return ["查看未完成部分的原因，补充必要信息后重新分析。"]
    if state == "blocked":
        return ["补充必要信息后重新提交分析。"]
    if state == "failed":
        return ["检查数据或服务状态后重试。"]
    if limitations:
        return ["结合使用边界查看结果，并在需要时补充条件后继续分析。"]
    return []


def _build_sections(components: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sections = [
        {
            "section_id": "overview",
            "kind": "summary",
            "title": "分析概览",
            "component_ids": [item.get("component_id") for item in components],
        }
    ]
    for index, item in enumerate(components[:_MAX_COMPONENTS], start=1):
        sections.append(
            {
                "section_id": _text(item.get("component_id"), 96),
                "kind": "component",
                "title": f"分析结果 {index}",
                "component_id": _text(item.get("component_id"), 96),
                "domain_id": _text(item.get("domain_id"), 64),
                "state": _text(item.get("state"), 32),
                "status": _text(item.get("status"), 32),
                "result_type": _text(item.get("result_type"), 96),
                "data_profile": _safe_object(item.get("data_profile")),
                "data_kinds": _data_profile_kinds(item.get("data_profile")),
                "depends_on": _safe_strings(item.get("depends_on"), _MAX_COMPONENTS),
                "inputs": project_component_inputs(item.get("inputs")),
                "answer": _text(item.get("answer"), 640),
                "view_refs": _safe_strings(item.get("view_refs"), 16),
                "execution": _project_execution(item.get("execution")),
                "input_evidence": _project_input_evidence(item.get("input_evidence")),
            }
        )
    return sections


def _aggregate_data_kinds(components: Sequence[Mapping[str, Any]]) -> list[str]:
    """Describe the concrete result shapes present in a Composite response."""

    found: set[str] = set()
    for item in components:
        if not isinstance(item, Mapping):
            continue
        found.update(_data_profile_kinds(item.get("data_profile")))
    concrete = [kind for kind in SUPPORTED_DATA_KINDS if kind != "unknown" and kind in found]
    return concrete[:8] or ["unknown"]


def _data_profile_kinds(value: Any) -> list[str]:
    profile = value if isinstance(value, Mapping) else {}
    raw = profile.get("kinds")
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, (list, tuple)):
        return []
    return [
        kind
        for kind in SUPPORTED_DATA_KINDS
        if kind in {str(item or "").strip() for item in values[:8]}
    ][:8]


def _build_views(value: Any, state: str) -> list[dict[str, Any]]:
    panels = value.get("panels") if isinstance(value, Mapping) else {}
    if not isinstance(panels, Mapping):
        panels = {}
    views: list[dict[str, Any]] = []
    for panel_id, raw in list(panels.items())[:_MAX_VIEWS]:
        if not isinstance(raw, Mapping):
            continue
        view_id = _text(raw.get("view_id") or panel_id, 96)
        views.append(
            {
                "view_id": view_id,
                "kind": _text(raw.get("kind") or raw.get("type") or "generic", 48),
                "title": _text(raw.get("title") or view_id, 160),
                "state": _text(raw.get("state") or state, 32),
                "component_id": _text(raw.get("component_id"), 96) or None,
                "domain_id": _text(raw.get("domain_id"), 64) or None,
                "payload": _bounded_value(raw, depth=0),
            }
        )
    return views


def _build_evidence(
    value: Any,
    state: str,
    *,
    answer_generation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    result = {
        "schema_version": _text(source.get("schema_version"), 96),
        "available": bool(source),
        "state": _text(source.get("state") or state, 32),
        "component_count": _bounded_int(source.get("component_count"), _MAX_COMPONENTS),
        "completed_component_ids": _safe_strings(source.get("completed_component_ids"), _MAX_COMPONENTS),
        "failed_component_ids": _safe_strings(source.get("failed_component_ids"), _MAX_COMPONENTS),
        "blocked_component_ids": _safe_strings(source.get("blocked_component_ids"), _MAX_COMPONENTS),
        "pending_component_ids": _safe_strings(source.get("pending_component_ids"), _MAX_COMPONENTS),
        "component_evidence": _bounded_value(source.get("component_evidence") or [], depth=0),
    }
    execution = source.get("execution_binding")
    if isinstance(execution, Mapping):
        result["execution_binding"] = _project_execution_binding(execution)
    if isinstance(answer_generation, Mapping):
        from agent.answer_generation import project_answer_generation_evidence

        result["answer_generation"] = project_answer_generation_evidence(
            answer_generation
        )
    return result


def _build_planning(value: Any) -> dict[str, Any]:
    """Expose only bounded planner/provider facts to every result consumer."""

    if not isinstance(value, Mapping):
        return {}
    result = {
        "schema_version": _text(value.get("schema_version"), 96),
        "planner_source": _text(value.get("planner_source"), 32),
        "schema_status": _text(value.get("schema_status"), 32),
    }
    if isinstance(value.get("execution_binding"), Mapping):
        result["execution_binding"] = _project_execution_binding(
            value["execution_binding"]
        )
    structured_output = project_structured_output_evidence(
        value.get("structured_output")
    )
    if structured_output is not None:
        result["structured_output"] = structured_output
    provider_runtime = project_provider_runtime_evidence(
        value.get("provider_runtime")
    )
    if provider_runtime is not None:
        result["provider_runtime"] = provider_runtime
    planner_attempt = project_planner_attempt_receipt(value.get("planner_attempt"))
    if planner_attempt is not None:
        result["planner_attempt"] = planner_attempt
    canonical_plan = project_canonical_plan_receipt(value.get("canonical_plan"))
    if canonical_plan["state"] != "unavailable" or value.get("canonical_plan"):
        result["canonical_plan"] = canonical_plan
    completeness = value.get("plan_completeness")
    if isinstance(completeness, Mapping):
        result["plan_completeness"] = {
            "schema_version": _text(
                completeness.get("schema_version")
                or "spatial-agent.plan-completeness.v1",
                96,
            ),
            "status": _text(completeness.get("status"), 24),
            "reason_code": _text(completeness.get("reason_code"), 96),
            "component_count": _bounded_int(
                completeness.get("component_count"), _MAX_COMPONENTS
            ),
            "materialized_count": _bounded_int(
                completeness.get("materialized_count"), _MAX_COMPONENTS
            ),
        }
    discovery = value.get("discovery")
    if isinstance(discovery, Mapping):
        result["discovery"] = _project_discovery(discovery)
    selection_evidence = normalize_selection_evidence(value.get("selection_evidence"))
    if selection_evidence:
        result["selection_evidence"] = selection_evidence
    analysis_intents = _project_analysis_intents(value.get("analysis_intents"))
    if analysis_intents:
        result["analysis_intents"] = analysis_intents
    continuation = value.get("continuation")
    if isinstance(continuation, Mapping):
        result["continuation"] = {
            "schema_version": _text(continuation.get("schema_version"), 96),
            "request_fingerprint": _text(continuation.get("request_fingerprint"), 128),
            "planner_selection_fingerprint": _text(
                continuation.get("planner_selection_fingerprint"), 128
            ),
            "component_id": _text(continuation.get("component_id"), 96),
            "domain_id": _text(continuation.get("domain_id"), 64),
            "capability_id": _text(continuation.get("capability_id"), 96),
            "field_ids": _safe_strings(continuation.get("field_ids"), _MAX_COMPONENTS),
        }
        if str(continuation.get("schema_version") or "") == "spatial-agent.composite-clarification-continuation.v1":
            result["continuation"]["component_ids"] = _safe_strings(
                continuation.get("component_ids"), _MAX_COMPONENTS
            )
            result["continuation"]["domain_ids"] = _safe_strings(
                continuation.get("domain_ids"), _MAX_COMPONENTS
            )
            result["continuation"]["components"] = [
                {
                    "component_id": _text(item.get("component_id"), 96),
                    "domain_id": _text(item.get("domain_id"), 64),
                    "capability_id": _text(item.get("capability_id"), 96),
                }
                for item in (continuation.get("components") or [])[:_MAX_COMPONENTS]
                if isinstance(item, Mapping)
            ]
            result["continuation"].pop("component_id", None)
            result["continuation"].pop("domain_id", None)
            result["continuation"].pop("capability_id", None)
            result["continuation"].pop("field_ids", None)
    return {key: item for key, item in result.items() if item not in (None, "")}


def _project_analysis_intents(value: Any) -> list[dict[str, Any]]:
    """Keep normalized, domain-neutral intent receipts for result consumers."""

    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for raw in list(value)[:_MAX_COMPONENTS]:
        if not isinstance(raw, Mapping):
            continue
        try:
            normalized = normalize_analysis_intent(raw.get("intent"))
        except AnalysisIntentError:
            continue
        item = {"intent": normalized}
        domain_id = _text(raw.get("domain_id"), 64)
        if domain_id:
            item["domain_id"] = domain_id
        result.append(item)
    return result


def _collect_artifacts(
    composite: Mapping[str, Any], components: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    evidence = composite.get("evidence")
    if isinstance(evidence, Mapping):
        for item in evidence.get("artifact_references") or []:
            if isinstance(item, Mapping):
                references.append(_artifact(item))
    for component in components:
        artifact = component.get("artifact")
        if isinstance(artifact, Mapping):
            references.append(_artifact(artifact))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in references:
        key = json.dumps(item, ensure_ascii=True, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:_MAX_COMPONENTS]


def _artifact(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(value.get("available")),
        "kind": _text(value.get("kind"), 48),
        "status": _text(value.get("status"), 32),
        "domain_id": _text(value.get("domain_id"), 64),
        "ref": _text(value.get("ref"), 160),
    }


def _project_discovery(value: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [
        item for item in (value.get("candidates") or []) if isinstance(item, Mapping)
    ]
    try:
        candidate_count = int(value.get("candidate_count"))
    except (TypeError, ValueError):
        candidate_count = len(candidates)
    try:
        data_requirement_count = int(value.get("data_requirement_count"))
    except (TypeError, ValueError):
        data_requirement_count = len(value.get("data_requirements") or [])
    return {
        "schema_version": _text(value.get("schema_version"), 96),
        "request_fingerprint": _text(value.get("request_fingerprint"), 128),
        "discovery_fingerprint": _text(value.get("discovery_fingerprint"), 128),
        "state": _text(value.get("state"), 32),
        "reason_code": _text(value.get("reason_code"), 96),
        "candidate_count": max(0, min(_MAX_VIEWS, candidate_count)),
        "data_requirement_count": max(0, min(64, data_requirement_count)),
        "next_actions": _safe_strings(value.get("next_actions"), 4),
    }


def _fit_budget(projection: dict[str, Any]) -> None:
    encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) <= _MAX_BYTES:
        return
    for view in projection.get("views") or []:
        if isinstance(view, dict):
            view["payload"] = {"truncated": True, "reason": "view_payload_budget"}
    projection["evidence"]["views_truncated"] = True


def _bounded_int(value: Any, maximum: int) -> int:
    try:
        return max(0, min(maximum, int(value)))
    except (TypeError, ValueError):
        return 0


def _bounded_value(value: Any, *, depth: int) -> Any:
    if depth >= 5:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _bounded_value(item, depth=depth + 1)
            for key, item in list(value.items())[:96]
            if str(key).lower() not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        items = [_bounded_value(item, depth=depth + 1) for item in list(value)[:256]]
        if len(value) > 256:
            items.append("[truncated]")
        return items
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:1200] if isinstance(value, str) else value
    return str(value)[:120]


def _safe_object(value: Any) -> dict[str, Any]:
    bounded = _bounded_value(value or {}, depth=0)
    return bounded if isinstance(bounded, dict) else {}


def _safe_strings(value: Any, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    return [_text(item, 96) for item in list(value)[:limit] if _text(item, 96)]


def _project_execution_binding(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        "schema_version": _text(value.get("schema_version"), 96),
        "binding_fingerprint": _text(value.get("binding_fingerprint"), 128),
        "request_fingerprint": _text(value.get("request_fingerprint"), 128),
        "component_ids": _safe_strings(value.get("component_ids"), _MAX_COMPONENTS),
    }
    return {key: item for key, item in result.items() if item not in (None, "", [])}


def _project_execution(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        "schema_version": _text(value.get("schema_version"), 96),
        "binding_fingerprint": _text(value.get("binding_fingerprint"), 128),
        "plan_fingerprint": _text(value.get("plan_fingerprint"), 128),
        "step_ids": _safe_strings(value.get("step_ids"), _MAX_COMPONENTS * 2),
    }
    return {key: item for key, item in result.items() if item not in (None, "", [])}


def _project_input_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        "schema_version": _text(value.get("schema_version"), 96),
        "state": _text(value.get("state"), 32),
        "input_names": _safe_strings(value.get("input_names"), 8),
    }
    return {key: item for key, item in result.items() if item not in (None, "", [])}


def _status(value: Any, state: str) -> str:
    text = _text(value, 32).upper()
    if text:
        return text
    return {"completed": "COMPLETED", "partial": "PARTIAL", "blocked": "BLOCKED", "failed": "FAILED"}.get(state, "FAILED")


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = [
    "COMPOSITE_VIEW_SCHEMA_VERSION",
    "CompositeViewError",
    "build_composite_view_projection",
]
