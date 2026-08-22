"""Build the bounded result envelope shared by API clients and the Console."""

from pathlib import Path
import math
from typing import Any, Dict, List, Mapping

from agent.result_registry import ResultContractRegistry, default_result_registry
from agent.execution_contract import build_execution_record, execution_record_summary
from agent.deployment_evidence import build_deployment_evidence
from agent.action_lifecycle import project_action_lifecycle
from agent.plan_quality import project_plan_quality_evidence
from agent.execution_timeline import build_execution_timeline
from agent.evidence_registry import build_evidence_registry
from agent.evidence_recovery import project_evidence_recovery
from agent.recovery_action import normalize_action_receipt
from agent.contract_versions import (
    MODEL_EVIDENCE_SCHEMA_VERSION,
    RESULT_ENVELOPE_SCHEMA_VERSION,
)
from agent.selection_interaction import build_selection_interaction
from agent.nested_schema import (
    NestedSchemaError,
    normalize_result_contract,
    normalize_views,
    unavailable_nested_view,
)
from agent.runtime_context import normalize_runtime_context, runtime_context_fingerprint
from agent.request_identity import build_request_identity

COMMON_WORKSPACE_PANELS = [
    "answer",
    "evidence",
    "metrics",
    "steps",
    "provenance",
    "trace",
]

GEOMETRY_STATUS = {
    "real_geometry",
    "boundary_geometry",
    "no_geometry",
    "truncated_geometry",
    "unknown",
}

REPLANNING_SCHEMA_VERSION = "spatial-agent.replanning.v1"


def build_result_contract(
    payload: Dict[str, Any],
    *,
    registry: ResultContractRegistry | None = None,
) -> Dict[str, Any]:
    registry = registry or default_result_registry()
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
    output = plan.get("output") if isinstance(plan.get("output"), dict) else {}
    result_type = str(payload.get("result_type") or output.get("type") or "unknown")
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    references: List[Dict[str, Any]] = []
    evidence_steps = []
    geometry_sources = set()
    geometry_crs = set()

    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        result_ref = result.get("result_ref")
        if result_ref:
            references.append({"kind": "tool_result", "step_id": step.get("id"), "ref": result_ref})
        source = result.get("geometry_source")
        crs = result.get("geometry_crs") or result.get("crs")
        if source:
            geometry_sources.add(str(source))
        if crs:
            geometry_crs.add(str(crs))
        evidence_steps.append({
            "id": step.get("id"),
            "tool": step.get("tool"),
            "status": step.get("status"),
            "summary": _step_summary(result, step.get("error")),
            "error_category": str(step.get("error_category"))[:64]
            if step.get("error_category")
            else None,
            "error_code": str(step.get("error_code"))[:96]
            if step.get("error_code")
            else None,
            "governance": step.get("governance")
            if isinstance(step.get("governance"), dict)
            else None,
        })

    if payload.get("geojson_ref"):
        references.append({"kind": "geojson", "ref": payload["geojson_ref"]})

    geometry_evidence = _geometry_evidence(payload, geometry_sources)
    lineage = build_lineage_index(
        payload,
        steps=steps,
        geometry_evidence=geometry_evidence,
    )
    degradation = _degradation_matrix(
        payload,
        steps=steps,
        geometry_evidence=geometry_evidence,
        result_type=result_type,
        registry=registry,
    )
    replanning = build_replanning_evidence(_replanning_events_from_payload(payload))
    lifecycle = project_action_lifecycle(payload)
    selection_interaction = build_selection_interaction(
        selection=(payload.get("plan_evidence") or {}).get("workflow_selection")
        if isinstance(payload.get("plan_evidence"), Mapping)
        else None,
        clarification=payload.get("clarification"),
        decision=payload.get("decision_evidence"),
        lifecycle=lifecycle,
        status=payload.get("status"),
        subject_id=payload.get("run_id"),
    )
    workspace = _workspace_contract(
        result_type,
        registry=registry,
        steps=steps,
        geometry_evidence=geometry_evidence,
        geojson_ref=payload.get("geojson_ref"),
    )
    views = registry.build_views(
        result_type,
        steps=steps,
        geometry_evidence=geometry_evidence,
        geojson_ref=payload.get("geojson_ref"),
        workspace=workspace,
    )
    views = _ensure_view_fallbacks(
        views,
        workspace=workspace,
        payload=payload,
        degradation=degradation,
    )
    normalized_runtime_context = normalize_runtime_context(payload.get("runtime_context"))
    contract = {
        "schema_version": RESULT_ENVELOPE_SCHEMA_VERSION,
        "type": result_type,
        "title": str(output.get("title") or registry.title_for(result_type)),
        "summary": payload.get("answer") or payload.get("error") or "暂无结果摘要。",
        "request_identity": build_request_identity(payload),
        "request_facts": payload.get("request_facts") or {"available": False},
        "data": {
            "evidence_steps": evidence_steps,
            "degradations": degradation["items"],
        },
        "clarification": payload.get("clarification"),
        "decision": payload.get("decision_evidence") or {"available": False},
        "selection_interaction": selection_interaction,
        "lifecycle": lifecycle,
        "context": payload.get("context_evidence") or {"available": False},
        "planning": payload.get("plan_evidence") or {"available": False},
        "references": references,
        "lineage": lineage,
        "replanning": replanning,
        "execution_timeline": build_execution_timeline(payload),
        "degradation": degradation,
        "workspace": workspace,
        "views": views,
        "geometry": {
            "available": geometry_evidence["status"] in {"real_geometry", "boundary_geometry"},
            "status": geometry_evidence["status"],
            "reason": geometry_evidence["reason"],
            "feature_count": geometry_evidence["feature_count"],
            "truncated": geometry_evidence["truncated"],
            "geojson_ref": payload.get("geojson_ref"),
            "sources": sorted(set(geometry_sources) | set(geometry_evidence.get("sources", []))),
            "crs": sorted(geometry_crs),
        },
        "model_evidence": _model_evidence(
            payload.get("planner_metrics"),
            normalized_runtime_context,
        ),
    }
    contract["deployment_evidence"] = build_deployment_evidence(
        payload,
        model_evidence=contract["model_evidence"],
        degradation=degradation,
    )
    evidence_specs = []
    resolver = getattr(registry, "evidence_specs_for", None)
    if callable(resolver):
        evidence_specs = resolver(result_type)
    contract["evidence_registry"] = build_evidence_registry({
        "result": contract,
        "status": payload.get("status"),
    }, custom_entries=evidence_specs)
    contract["evidence_recovery"] = project_evidence_recovery(
        {"result": contract}
    )
    action_receipt = payload.get("action_receipt") or payload.get("interaction_receipt")
    if isinstance(action_receipt, Mapping):
        contract["action_receipt"] = normalize_action_receipt(action_receipt)
    if normalized_runtime_context is not None:
        contract["runtime_context"] = normalized_runtime_context
    if payload.get("run_id") or payload.get("action_execution_id"):
        # Rebuild from the current payload: AgentRunResult.to_dict() may have
        # produced an earlier record before Service assigned artifact_ref.
        record = build_execution_record(payload)
        contract["execution"] = execution_record_summary(record)
    if isinstance(payload.get("failure"), dict):
        contract["failure"] = dict(payload["failure"])
    nested_error = payload.get("_nested_schema_error")
    if nested_error:
        contract["schema_warnings"] = [{
            "code": "nested_schema_unavailable",
            "reason_code": str(nested_error)[:96],
        }]
    # One shared seam for all domain-owned view builders.  Rich panel fields
    # remain untouched; nested versions and required panel shape are checked
    # before the result reaches HTTP, artifact, async or Console consumers.
    return normalize_result_contract(contract)


def _model_evidence(metrics: Any, runtime_context: Any) -> Dict[str, Any]:
    """Project planner metrics without copying provider response content."""
    value = metrics if isinstance(metrics, Mapping) else {}
    result: Dict[str, Any] = {
        "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
        "available": bool(value),
    }
    execution_mode = str(value.get("execution_mode") or "").strip().lower()
    if execution_mode not in {"rule", "offline_replay", "live_model"}:
        context_mapping = runtime_context if isinstance(runtime_context, Mapping) else {}
        execution_mode = (
            "rule"
            if context_mapping.get("planner") == "rule"
            else "live_model"
            if value
            else "unknown"
        )
    result["execution_mode"] = execution_mode
    context_fingerprint = runtime_context_fingerprint(runtime_context)
    if context_fingerprint:
        result["context_fingerprint"] = context_fingerprint
    for key in ("provider", "model", "wire_api", "status", "error_type"):
        item = value.get(key)
        if isinstance(item, str) and item:
            result[key] = item[:96]
    if execution_mode == "offline_replay":
        fixture_id = value.get("fixture_id")
        if isinstance(fixture_id, str) and fixture_id:
            result["fixture_id"] = fixture_id[:96]
    for key in ("attempts", "retries"):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool):
            result[key] = max(0, min(item, 128))
    latency = value.get("latency_ms")
    if isinstance(latency, (int, float)) and not isinstance(latency, bool):
        result["latency_ms"] = round(max(0.0, min(float(latency), 3_600_000.0)), 3)
    usage = value.get("usage")
    if isinstance(usage, Mapping):
        safe_usage = {}
        for key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens"):
            item = usage.get(key)
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                safe_usage[key] = min(item, 10_000_000)
        if safe_usage:
            result["usage"] = safe_usage
    return result


def _ensure_view_fallbacks(
    views: Any,
    *,
    workspace: Mapping[str, Any],
    payload: Mapping[str, Any],
    degradation: Mapping[str, Any],
) -> Dict[str, Any]:
    """Keep declared views renderable when a run has no view data.

    Domain builders own successful view models.  The public envelope owns the
    failure/empty state so sync, async, artifact and recovery consumers see
    the same bounded reason instead of inventing a raw JSON fallback.
    """
    result = dict(views) if isinstance(views, Mapping) else {}
    panels = result.get("panels")
    panels = dict(panels) if isinstance(panels, Mapping) else {}
    specs = workspace.get("view_specs")
    specs = list(specs) if isinstance(specs, list) else []
    if not specs and "generic" in (workspace.get("panels") or []):
        specs = [{"id": "generic", "title": "结构化结果", "renderer": "generic"}]
    if not specs and payload.get("_nested_schema_error"):
        # Recovery of a future nested schema must still produce one bounded
        # renderer target.  Never copy the unknown panel into the contract.
        specs = [{"id": "generic", "title": "结构化结果", "renderer": "generic"}]
    items = degradation.get("items") if isinstance(degradation, Mapping) else []
    first_item = items[0] if isinstance(items, list) and items else {}
    reason = (
        str(payload.get("_nested_schema_error"))
        if payload.get("_nested_schema_error")
        else None
    ) or (
        first_item.get("message")
        if isinstance(first_item, Mapping)
        else None
    ) or "本次运行没有返回该视图的数据。"
    artifact = payload.get("artifact_ref")
    if not artifact and isinstance(payload.get("result"), Mapping):
        lineage = payload["result"].get("lineage")
        artifact_info = lineage.get("artifact") if isinstance(lineage, Mapping) else None
        artifact = artifact_info.get("available") if isinstance(artifact_info, Mapping) else None
    for spec in specs[:12]:
        if not isinstance(spec, Mapping):
            continue
        view_id = str(spec.get("id") or "")[:48]
        if not view_id or view_id in panels:
            continue
        panels[view_id] = {
            "kind": "unavailable",
            "view_id": view_id,
            "title": str(spec.get("title") or view_id)[:120],
            "reason": str(reason)[:320],
            "artifact_available": bool(artifact),
        }
    result["schema_version"] = str(
        result.get("schema_version") or "spatial-agent.views.v1"
    )[:80]
    result["panels"] = panels
    return result


def build_action_result_contract(
    payload: Dict[str, Any],
    *,
    registry: ResultContractRegistry | None = None,
) -> Dict[str, Any]:
    """Project a Domain Action through the same result/trace seam as a run.

    Actions are explicit Domain-owned operations rather than planner steps, so
    this adapter creates one bounded synthetic evidence step for the generic
    envelope. The action's own view model is retained when supplied; callers
    do not need a GIS-specific result contract to display an action result.
    """
    action_id = str(payload.get("action_id") or "")[:96]
    action_result = payload.get("action_result")
    action_result = action_result if isinstance(action_result, Mapping) else {}
    synthetic = dict(payload)
    synthetic["steps"] = [
        {
            "id": "action-execution",
            "tool": "action:" + action_id,
            "status": payload.get("status", "COMPLETED"),
            "result": dict(action_result),
            "error": payload.get("error"),
        }
    ]
    contract = build_result_contract(synthetic, registry=registry)
    supplied_views = action_result.get("views")
    if isinstance(supplied_views, Mapping):
        try:
            contract["views"] = normalize_views(supplied_views)
        except NestedSchemaError:
            contract["views"] = unavailable_nested_view(
                result_type=contract.get("type"),
                reason_code="action_view_schema_unavailable",
            )["views"]
    action_execution = payload.get("action_execution")
    if isinstance(action_execution, Mapping):
        contract["action_execution"] = _safe_action_execution(action_execution)
    contract["action"] = {
        "id": action_id,
        "domain_id": str(payload.get("domain_id") or "unknown")[:80],
        "artifact_ref": _basename_ref(payload.get("artifact_ref")),
    }
    contract["data"]["action"] = {
        "action_id": action_id,
        "result_keys": sorted(str(key)[:64] for key in action_result.keys())[:32],
    }
    contract["lineage"]["action_execution"] = {
        "available": bool(action_id),
        "action_id": action_id,
        "ref": payload.get("action_execution_id") or payload.get("run_id"),
    }
    # The artifact reference can be assigned between the first and final
    # result projection, so never reuse a stale pre-artifact record here.
    record = build_execution_record(payload, kind="action")
    contract["execution"] = execution_record_summary(record)
    return contract


def _safe_action_execution(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep action evidence stable and bounded across HTTP/artifact replay."""
    result = {
        "schema_version": str(
            value.get("schema_version") or "spatial-agent.action-execution.v1"
        )[:80],
        "status": str(value.get("status") or "UNKNOWN")[:32],
        "action_id": str(value.get("action_id") or "")[:96],
        "input_validated": bool(value.get("input_validated", False)),
    }
    try:
        duration = float(value.get("duration_ms"))
        if math.isfinite(duration) and duration >= 0:
            result["duration_ms"] = round(min(duration, 86_400_000), 3)
    except (TypeError, ValueError):
        pass
    if value.get("error_code"):
        result["error_code"] = str(value["error_code"])[:96]
    return result


def build_replanning_evidence(events: Any) -> Dict[str, Any]:
    """Normalize bounded adaptive-replanning evidence for every result surface.

    Runtime already keeps the raw event shape deliberately small. This is the
    result-envelope seam: it validates and bounds the shape again so an old
    artifact or custom planner cannot make HTTP, recovery, and Console
    consumers interpret different fields. Raw exception text is excluded.
    """
    normalized: List[Dict[str, Any]] = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        failed_step_id = _bounded_replan_token(event.get("failed_step_id"))
        failed_tool = _bounded_replan_token(event.get("failed_tool"))
        if not failed_step_id or not failed_tool:
            continue
        replacement_ids = [
            token
            for token in (
                _bounded_replan_token(item)
                for item in (event.get("replanned_step_ids") or [])
            )
            if token
        ][:24]
        item: Dict[str, Any] = {
            "failed_step_id": failed_step_id,
            "failed_tool": failed_tool,
            "failure_category": _bounded_replan_token(
                event.get("failure_category")
            ) or "unknown",
            "replanned_step_ids": replacement_ids,
        }
        repair_status = _bounded_replan_token(event.get("repair_status"))
        if repair_status in {"repaired", "failed"}:
            item["repair_status"] = repair_status
        repair_reason = _bounded_replan_token(event.get("repair_reason_code"))
        if repair_reason:
            item["repair_reason_code"] = repair_reason
        phase = _bounded_replan_token(event.get("phase"))
        if phase in {"planning", "execution"}:
            item["phase"] = phase
        for source_key, target_key in (
            ("plan_quality_before", "plan_quality_before"),
            ("plan_quality_after", "plan_quality_after"),
        ):
            quality = event.get(source_key)
            if isinstance(quality, Mapping):
                item[target_key] = project_plan_quality_evidence(quality)
        try:
            latency = float(event.get("latency_ms"))
            if math.isfinite(latency) and latency >= 0:
                item["latency_ms"] = round(min(latency, 86_400_000), 3)
        except (TypeError, ValueError):
            pass
        try:
            occurred_at = float(event.get("occurred_at"))
            if math.isfinite(occurred_at) and occurred_at > 0:
                item["occurred_at"] = round(occurred_at, 3)
        except (TypeError, ValueError):
            pass
        normalized.append(item)
        if len(normalized) >= 8:
            break
    return {
        "schema_version": REPLANNING_SCHEMA_VERSION,
        "available": bool(normalized),
        "count": len(normalized),
        "events": normalized,
    }


def _bounded_replan_token(value: Any) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    return str(value).strip()[:96]


def _replanning_events_from_payload(payload: Dict[str, Any]) -> Any:
    """Read current and legacy artifact locations without duplicating policy."""
    events = payload.get("replan_events")
    if isinstance(events, list):
        return events
    nested_result = payload.get("result")
    if isinstance(nested_result, dict):
        nested = nested_result.get("replanning")
        if isinstance(nested, dict) and isinstance(nested.get("events"), list):
            return nested["events"]
    return []


def _workspace_contract(
    result_type: str,
    *,
    registry: ResultContractRegistry,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any = None,
) -> Dict[str, Any]:
    registered = registry.is_registered(result_type)
    panels = list(registry.panels_for(result_type))
    map_evidence = _workspace_map(steps, geometry_evidence, geojson_ref)
    if map_evidence["available"] and "map" not in panels:
        panels.append("map")
    if not registered and steps:
        panels.append("generic")
    return {
        "schema_version": "spatial-agent.workspace.v1",
        "result_type": result_type,
        "registered_type": registered,
        "primary_panel": panels[0] if panels else "answer",
        "common_panels": list(COMMON_WORKSPACE_PANELS),
        "panels": panels[:12],
        "view_specs": registry.view_specs_for(result_type),
        "map": map_evidence,
    }


def _workspace_map(
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any,
) -> Dict[str, Any]:
    status = str(geometry_evidence.get("status") or "unknown")
    if status in {"real_geometry", "boundary_geometry"} and geojson_ref:
        return {
            "available": True,
            "mode": "geojson",
            "reason": str(geometry_evidence.get("reason") or "GeoJSON 空间要素可绘制")[:240],
        }
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        if _has_bounds(result):
            return {
                "available": True,
                "mode": "raster_bounds",
                "reason": "工具结果包含栅格范围，可绘制覆盖范围预览。",
            }
    return {
        "available": False,
        "mode": "none",
        "reason": str(geometry_evidence.get("reason") or "本次结果没有可绘制空间范围")[:240],
    }


def _has_bounds(result: Dict[str, Any]) -> bool:
    bounds = result.get("bounds")
    if _is_bounds(bounds):
        return True
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and _is_bounds(metadata.get("bounds")):
        return True
    return False


def _is_bounds(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
    )


# Small generic view primitives used by comparison results. Domain-specific
# view builders keep their own copies so the common envelope does not import
# or interpret domain tool names.
def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _view_metric(label: str, value: Any) -> Dict[str, Any]:
    return {
        "label": str(label)[:80],
        "value": "-" if value is None else value,
    }


# Domain-owned view implementations are dispatched by ResultContractRegistry.
def build_lineage_index(
    payload: Dict[str, Any],
    steps: List[Any] = None,
    geometry_evidence: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Build the bounded evidence index shared by every run-facing entry point."""
    steps = steps if isinstance(steps, list) else (
        payload.get("steps") if isinstance(payload.get("steps"), list) else []
    )
    if not isinstance(geometry_evidence, dict):
        geometry_sources = {
            str((step.get("result") or {}).get("geometry_source"))
            for step in steps
            if isinstance(step, dict)
            and isinstance(step.get("result"), dict)
            and (step.get("result") or {}).get("geometry_source")
        }
        geometry_evidence = _geometry_evidence(payload, geometry_sources)
    run_id = str(payload.get("run_id") or "")
    artifact_ref = _basename_ref(payload.get("artifact_ref"))
    geojson_ref = _basename_ref(payload.get("geojson_ref"))
    references = []
    if run_id:
        references.extend(
            [
                {"kind": "run", "ref": run_id},
                {"kind": "answer", "ref": run_id},
                {"kind": "trace", "ref": run_id},
            ]
        )
    if artifact_ref:
        references.append({"kind": "artifact", "ref": artifact_ref})
    if geojson_ref:
        references.append({"kind": "geojson", "ref": geojson_ref})
    references.append(
        {
            "kind": "release_evidence",
            "ref": "/release-evidence?max_files=10",
            "scope": "configured_data_volume",
        }
    )
    try:
        retry_count = max(0, int(payload.get("retry_count") or 0))
    except (TypeError, ValueError):
        retry_count = 0
    replanning = build_replanning_evidence(_replanning_events_from_payload(payload))
    return {
        "run_id": run_id or None,
        "answer": {"available": bool(payload.get("answer") or payload.get("error"))},
        "trace": {
            "available": bool(payload.get("trace_summary")),
            "step_count": len(steps),
        },
        "artifact": {"available": bool(artifact_ref), "ref": artifact_ref},
        "geojson": {
            "available": bool(geojson_ref),
            "ref": geojson_ref,
            "status": geometry_evidence.get("status", "unknown"),
        },
        "retry": {
            "available": retry_count > 0,
            "count": retry_count,
            "ref": run_id if retry_count > 0 else None,
        },
        "replanning": {
            "available": replanning["available"],
            "count": replanning["count"],
            "ref": run_id if replanning["available"] else None,
        },
        "map_layers": _map_layers(steps, geometry_evidence),
        "release_evidence": {
            "available": True,
            "ref": "/release-evidence?max_files=10",
            "scope": "configured_data_volume",
        },
        "references": references,
    }


def build_history_lineage(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build a safe index for compact session/run history records."""
    payload = dict(record or {})
    lineage = build_lineage_index(payload, steps=[], geometry_evidence={
        "status": "unknown",
        "reason": "历史摘要需打开运行详情查看空间证据",
        "feature_count": 0,
        "truncated": False,
        "sources": [],
    })
    lineage["trace"]["available"] = False
    lineage["trace"]["deferred"] = bool(lineage.get("run_id"))
    return lineage


def build_comparison_lineage(rows: List[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    """Index the child runs behind a comparison without duplicating their payloads."""
    run_ids = []
    references = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("run_id"):
            continue
        run_id = str(row["run_id"])
        if run_id in run_ids:
            continue
        run_ids.append(run_id)
        references.extend([
            {"kind": "run", "ref": run_id},
            {"kind": "lineage", "ref": run_id},
        ])
    return {
        "schema_version": 1,
        "kind": str(kind),
        "run_ids": run_ids,
        "row_count": len(rows) if isinstance(rows, list) else 0,
        "references": references,
    }


def build_comparison_views(
    rows: List[Dict[str, Any]],
    kind: str,
    *,
    title: str,
    x_field: str,
    x_label: str,
    y_field: str,
    y_label: str,
    table_columns: List[tuple[str, str]] = None,
    note: str = "",
) -> Dict[str, Any]:
    """Build bounded chart/table views for comparison endpoints."""
    safe_rows = [row for row in rows if isinstance(row, dict)][:50]
    points = []
    for row in safe_rows:
        y_value = row.get(y_field)
        try:
            numeric_y = float(y_value)
        except (TypeError, ValueError):
            numeric_y = None
        points.append({
            "x": _first_present(row.get(x_field), "-"),
            "y": numeric_y,
            "label": _comparison_label(row.get(x_field), x_label),
            "run_id": row.get("run_id"),
            "status": row.get("status"),
        })
    completed = len([row for row in safe_rows if str(row.get("status") or "") == "COMPLETED"])
    values = [point["y"] for point in points if point.get("y") is not None]
    columns = table_columns or [(x_label, x_field), (y_label, y_field), ("状态", "status")]
    return normalize_views({
        "schema_version": "spatial-agent.views.v1",
        "panels": {
            "chart": {
                "kind": "comparison_chart",
                "chart_type": "bar",
                "comparison_kind": str(kind)[:120],
                "title": str(title)[:160],
                "metrics": [
                    _view_metric("场景数", len(safe_rows)),
                    _view_metric("完成数", completed),
                    _view_metric("最大值", max(values) if values else None),
                ],
                "encodings": {
                    "x": {"field": str(x_field)[:80], "label": str(x_label)[:80]},
                    "y": {"field": str(y_field)[:80], "label": str(y_label)[:80]},
                },
                "series": [
                    {
                        "name": str(y_label)[:80],
                        "points": points[:50],
                    }
                ],
                "table": {
                    "columns": [label for label, _ in columns[:12]],
                    "rows": [[_comparison_cell(row.get(field)) for _, field in columns[:12]] for row in safe_rows],
                },
                "note": str(note or "对比图由后端 result views 生成；详细子运行可通过 run_id 查看。")[:320],
            }
        },
    })


def _comparison_label(value: Any, x_label: str) -> str:
    if value is None or value == "":
        return "-"
    if "坡度" in x_label:
        return "{}°".format(_format_compact_number(value))
    if "距离" in x_label:
        return "{} 米".format(_format_compact_number(value))
    return str(value)[:120]


def _comparison_cell(value: Any) -> Any:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (int, bool)):
        return value
    return str(value)[:180]


def _format_compact_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)[:80]
    return "{:g}".format(number)


def _basename_ref(value: Any) -> str | None:
    if not value:
        return None
    return Path(str(value)).name or None


def _map_layers(steps: List[Any], geometry_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    layers = []
    seen = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        dataset = result.get("dataset")
        source = result.get("geometry_source")
        if not dataset and not source:
            continue
        key = (str(dataset or ""), str(source or ""))
        if key in seen:
            continue
        seen.add(key)
        layers.append(
            {
                "id": "|".join(item for item in key if item) or "空间图层",
                "dataset": dataset,
                "source": source,
                "result_ref": result.get("result_ref"),
            }
        )
    if not layers and geometry_evidence.get("sources"):
        layers.extend(
            {
                "id": str(source),
                "dataset": None,
                "source": str(source),
                "result_ref": None,
            }
            for source in geometry_evidence["sources"]
        )
    return layers[:20]


def _geometry_evidence(payload: Dict[str, Any], geometry_sources) -> Dict[str, Any]:
    explicit = payload.get("_geometry_evidence")
    if isinstance(explicit, dict):
        status = explicit.get("status") if explicit.get("status") in GEOMETRY_STATUS else "unknown"
        return {
            "status": status,
            "reason": str(explicit.get("reason") or "运行结果未提供几何证据")[:240],
            "feature_count": int(explicit.get("feature_count") or 0),
            "truncated": bool(explicit.get("truncated")),
            "sources": [str(item) for item in explicit.get("sources", []) if item],
        }
    if payload.get("_geometry_feature_count"):
        status = "boundary_geometry" if geometry_sources == {"geojson"} else "real_geometry"
        return {
            "status": status,
            "reason": "导出摘要包含真实空间要素",
            "feature_count": int(payload.get("_geometry_feature_count") or 0),
            "truncated": False,
            "sources": sorted(geometry_sources),
        }
    if payload.get("geojson_ref"):
        return {
            "status": "no_geometry",
            "reason": "GeoJSON 引用存在，但摘要没有可绘制空间要素",
            "feature_count": 0,
            "truncated": False,
            "sources": [],
        }
    return {
        "status": "unknown",
        "reason": "本次运行尚未生成空间导出证据",
        "feature_count": 0,
        "truncated": False,
        "sources": [],
    }


_SEVERITY_RANK = {
    "none": 0,
    "warning": 1,
    "degraded": 2,
    "unavailable": 3,
}

_STATUS_LABEL = {
    "ready": "可用",
    "passed": "通过",
    "warning": "警告",
    "degraded": "部分可用",
    "unavailable": "不可用",
    "not_ready": "未就绪",
    "unknown": "未知",
}

_RUN_STATUS_LABEL = {
    "NEEDS_CLARIFICATION": "需要澄清",
    "FAILED": "失败",
    "REJECTED": "已拒绝",
    "CANCELLED": "已取消",
    "TIMED_OUT": "超时",
}

def _degradation_matrix(
    payload: Dict[str, Any],
    *,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    result_type: str,
    registry: ResultContractRegistry,
) -> Dict[str, Any]:
    explicit = payload.get("degradation")
    if not isinstance(explicit, dict) and isinstance(payload.get("result"), dict):
        explicit = payload["result"].get("degradation")
    if isinstance(explicit, dict):
        return _sanitize_degradation(explicit)

    items: List[Dict[str, str]] = []
    seen = set()

    def add(code: str, severity: str, message: str, source: str) -> None:
        severity = severity if severity in _SEVERITY_RANK else "warning"
        code = str(code or "degradation")[:96]
        message = str(message or "结果存在降级或限制。")[:320]
        source = str(source or "result")[:160]
        key = (code, message, source)
        if key in seen:
            return
        seen.add(key)
        items.append({
            "code": code,
            "severity": severity,
            "message": message,
            "source": source,
        })

    run_status = str(payload.get("status") or "")
    if run_status == "NEEDS_CLARIFICATION":
        add(
            "run_needs_clarification",
            "warning",
            "请求仍在澄清阶段，尚未形成完整执行结果。",
            "run.status",
        )
    elif run_status == "WAITING_FOR_DECISION":
        add(
            "run_waiting_for_decision",
            "warning",
            "计划已生成，等待用户确认后才会执行。",
            "run.status",
        )
    elif run_status in {"FAILED", "REJECTED", "CANCELLED", "TIMED_OUT"}:
        add(
            "run_not_completed",
            "unavailable",
            "运行状态为{}，结果不能视为完整分析。".format(
                _RUN_STATUS_LABEL.get(run_status, run_status)
            ),
            "run.status",
        )

    geometry_status = str(geometry_evidence.get("status") or "unknown")
    if geometry_status == "truncated_geometry":
        add(
            "geometry_truncated",
            "warning",
            str(geometry_evidence.get("reason") or "空间导出达到大小上限，地图只代表截断后的摘要。"),
            "result.geometry",
        )
    elif geometry_status == "no_geometry":
        add(
            "geometry_empty",
            "warning",
            str(geometry_evidence.get("reason") or "结果没有可绘制空间要素，只能查看摘要。"),
            "result.geometry",
        )
    elif geometry_status == "unknown" and registry.requires_geometry(result_type) and steps:
        add(
            "geometry_unknown",
            "warning",
            str(geometry_evidence.get("reason") or "本次运行尚未形成空间几何证据。"),
            "result.geometry",
        )

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or step.get("tool") or "step")[:80]
        source = "step:{}".format(step_id)
        step_status = str(step.get("status") or "")
        if step_status and step_status != "COMPLETED":
            severity = "unavailable" if step_status in {"FAILED", "ERROR"} else "warning"
            add(
                "tool_step_not_completed:{}".format(step_id),
                severity,
                "工具 {} 状态为{}。".format(
                    step.get("tool") or step_id,
                    _RUN_STATUS_LABEL.get(step_status, step_status),
                ),
                source,
            )
        if step.get("error"):
            add(
                "tool_step_error:{}".format(step_id),
                "unavailable",
                str(step.get("error")),
                source,
            )

        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        _add_result_degradations(result, add, source, step_id)

    status = "none"
    for item in items:
        if _SEVERITY_RANK[item["severity"]] > _SEVERITY_RANK[status]:
            status = item["severity"]
    return {
        "schema_version": "spatial-agent.degradation.v1",
        "available": True,
        "status": status,
        "item_count": len(items),
        "items": items[:40],
    }


def _add_result_degradations(result: Dict[str, Any], add, source: str, step_id: str) -> None:
    result_status = str(result.get("status") or "")
    if result_status in {"warning", "degraded", "unavailable"}:
        add(
            "data_health_{}".format(result_status),
            _status_severity(result_status),
            "数据健康状态为{}。{}".format(
                _STATUS_LABEL.get(result_status, result_status),
                " " + str(result.get("warning")) if result.get("warning") else "",
            ),
            source,
        )
    data_readiness = str(result.get("data_readiness") or "")
    if data_readiness and data_readiness != "ready":
        add(
            "data_readiness_{}".format(data_readiness),
            "unavailable" if data_readiness == "not_ready" else _status_severity(data_readiness),
            "数据就绪状态为{}。".format(_STATUS_LABEL.get(data_readiness, data_readiness)),
            source,
        )

    for dataset in result.get("datasets") or []:
        if not isinstance(dataset, dict):
            continue
        dataset_status = str(dataset.get("status") or dataset.get("quality") or "")
        if dataset_status not in {"warning", "degraded", "unavailable"}:
            continue
        dataset_name = str(dataset.get("dataset") or "dataset")[:64]
        details = _dataset_limit_details(dataset)
        add(
            "dataset_{}:{}".format(dataset_status, dataset_name),
            _status_severity(dataset_status),
            "{} 数据集状态为{}。{}".format(
                dataset_name,
                _STATUS_LABEL.get(dataset_status, dataset_status),
                details,
            ),
            source,
        )

    analysis_ready = result.get("analysis_ready") if isinstance(result.get("analysis_ready"), dict) else {}
    analysis_status = str(analysis_ready.get("status") or "")
    if analysis_status in {"warning", "degraded", "unavailable"}:
        add(
            "analysis_ready_{}".format(analysis_status),
            _status_severity(analysis_status),
            "分析就绪派生层状态为{}，联合像元结果不能视为完整可复现证据。".format(
                _STATUS_LABEL.get(analysis_status, analysis_status)
            ),
            source,
        )
    source_binding = analysis_ready.get("source_binding")
    if isinstance(source_binding, dict):
        binding_status = str(source_binding.get("status") or "")
        if binding_status in {"warning", "degraded", "unavailable"}:
            add(
                "source_binding_{}".format(binding_status),
                _status_severity(binding_status),
                "源数据绑定状态为{}，不能确认派生层仍对应当前来源。".format(
                    _STATUS_LABEL.get(binding_status, binding_status)
                ),
                source,
            )
    output_manifest = analysis_ready.get("output_manifest")
    if isinstance(output_manifest, dict):
        manifest_status = str(output_manifest.get("status") or "")
        if manifest_status in {"warning", "degraded", "unavailable"}:
            add(
                "output_manifest_{}".format(manifest_status),
                _status_severity(manifest_status),
                "派生输出 manifest 状态为{}，输出文件与发布记录存在一致性限制。".format(
                    _STATUS_LABEL.get(manifest_status, manifest_status)
                ),
                source,
            )
        elif (
            manifest_status == "ready"
            and output_manifest.get("verification_mode") == "metadata"
            and not output_manifest.get("hashes_verified")
        ):
            add(
                "output_manifest_metadata_only",
                "warning",
                "输出 manifest 当前仅完成 metadata 核验；发布前仍需显式执行输出文件 SHA-256 verifier。",
                source,
            )

    for key in ("manifest", "source_binding", "output_manifest"):
        evidence = result.get(key)
        if not isinstance(evidence, dict):
            continue
        status = str(evidence.get("status") or "")
        if status in {"warning", "degraded", "unavailable"}:
            add(
                "{}_{}".format(key, status),
                _status_severity(status),
                "{} 状态为{}。".format(key, _STATUS_LABEL.get(status, status)),
                source,
            )

    for container_name in ("statistics", "summary"):
        container = result.get(container_name)
        if isinstance(container, dict) and container.get("error"):
            add(
                "tool_result_error:{}".format(step_id),
                "degraded",
                str(container.get("error")),
                source + ".{}".format(container_name),
            )
    if result.get("error"):
        add(
            "tool_result_error:{}".format(step_id),
            "degraded",
            str(result.get("error")),
            source,
        )
    if result.get("warning"):
        add(
            "tool_result_warning:{}".format(step_id),
            "warning",
            str(result.get("warning")),
            source,
        )

    for check in result.get("checks") or []:
        if not isinstance(check, dict):
            continue
        check_status = str(check.get("status") or "")
        if check_status and check_status != "passed":
            add(
                "check_{}:{}".format(check_status, str(check.get("name") or "check")[:48]),
                _status_severity(check_status),
                str(check.get("message") or "数据检查未通过。"),
                source,
            )


def _dataset_limit_details(dataset: Dict[str, Any]) -> str:
    details = []
    for error in dataset.get("errors") or []:
        if error:
            details.append(str(error))
    for check in dataset.get("checks") or []:
        if (
            isinstance(check, dict)
            and check.get("status")
            and check.get("status") != "passed"
            and check.get("message")
        ):
            details.append(str(check["message"]))
    return "；".join(details[:3])[:240]


def _status_severity(status: str) -> str:
    if status == "unavailable":
        return "unavailable"
    if status == "degraded":
        return "degraded"
    return "warning"


def _sanitize_degradation(value: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    seen = set()
    for item in value.get("items") or []:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "warning")
        if severity not in _SEVERITY_RANK:
            severity = "warning"
        normalized = {
            "code": str(item.get("code") or "degradation")[:96],
            "severity": severity,
            "message": str(item.get("message") or "结果存在降级或限制。")[:320],
            "source": str(item.get("source") or "result")[:160],
        }
        key = (normalized["code"], normalized["message"], normalized["source"])
        if key in seen:
            continue
        seen.add(key)
        items.append(normalized)
    status = str(value.get("status") or "none")
    if status not in _SEVERITY_RANK:
        status = "none"
    for item in items:
        if _SEVERITY_RANK[item["severity"]] > _SEVERITY_RANK[status]:
            status = item["severity"]
    return {
        "schema_version": str(value.get("schema_version") or "spatial-agent.degradation.v1")[:80],
        "available": True,
        "status": status,
        "item_count": len(items),
        "items": items[:40],
    }


def _step_summary(result: Dict[str, Any], error: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for key in ("dataset", "admin_name", "count", "file_count", "result_ref", "crs"):
        value = result.get(key)
        if isinstance(value, (str, int, float, bool)):
            summary[key] = value
    statistics = result.get("statistics")
    if isinstance(statistics, dict):
        for key in (
            "minimum", "maximum", "mean", "standard_deviation", "valid_pixel_count",
            "nodata_ratio", "category_count", "candidate_pixel_count", "candidate_ratio",
            "slope_limit_degrees",
        ):
            value = statistics.get(key)
            if isinstance(value, (str, int, float, bool)):
                summary[key] = value
        if statistics.get("error"):
            summary["error"] = str(statistics["error"])
    detail = result.get("summary")
    if isinstance(detail, dict) and detail.get("error"):
        summary["error"] = str(detail["error"])
    if result.get("error"):
        summary["error"] = str(result["error"])
    if result.get("warning"):
        summary["warning"] = str(result["warning"])
    if error:
        summary["error"] = str(error)
    return summary
