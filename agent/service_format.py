"""Result formatting, geometry evidence, and request normalization helpers.

These functions are stateless and shared by the AgentService facade, HTTP
entry points, and tests. Keeping them here removes the formatting concerns
from the service orchestration module.
"""

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from agent.artifact_store import ArtifactStore
from agent.geojson_exporter import export_run_summary
from agent.models import AgentRunResult
from agent.provenance import build_provenance
from agent.trace_formatter import format_trace
from agent.workflow_templates import normalize_workflow_selection
from result_contract import build_result_contract


def result_type(payload: Dict) -> str:
    return str(((payload.get("plan") or {}).get("output") or {}).get("type") or "unknown")


def crs_name(crs) -> str | None:
    if isinstance(crs, str):
        return crs
    if isinstance(crs, dict):
        return (crs.get("properties") or {}).get("name")
    if isinstance(crs, list) and len(crs) == 1:
        return crs_name(crs[0])
    return None


def tag_geometry_features(features, source=None, crs=None, source_crs=None, dataset=None):
    """Keep CRS/source beside each feature when result collections are merged."""
    tagged = []
    crs_value = crs_name(crs)
    for feature in features or []:
        if not isinstance(feature, dict):
            continue
        properties = dict(feature.get("properties") or {})
        if source:
            properties["geometry_source"] = source
        if crs_value:
            properties["geometry_crs"] = crs_value
        if source_crs:
            properties["geometry_source_crs"] = source_crs
        if dataset:
            properties["dataset"] = dataset
        tagged.append({**feature, "properties": properties})
    return tagged


def geometry_evidence_for_features(features) -> Dict[str, Any]:
    features = [
        item for item in features or []
        if isinstance(item, dict) and item.get("geometry")
    ]
    if not features:
        return {
            "status": "no_geometry",
            "reason": "导出摘要没有可绘制空间要素",
            "feature_count": 0,
            "truncated": False,
        }
    sources = {
        str((item.get("properties") or {}).get("geometry_source"))
        for item in features
        if (item.get("properties") or {}).get("geometry_source")
    }
    status = "boundary_geometry" if sources == {"geojson"} else "real_geometry"
    return {
        "status": status,
        "reason": "导出摘要包含可绘制空间要素",
        "feature_count": len(features),
        "truncated": any(
            bool((item.get("properties") or {}).get("geometry_truncated"))
            for item in features
        ),
        "sources": sorted(sources),
    }


def exported_geometry_evidence(geojson_ref) -> Tuple[int, Dict[str, Any]]:
    """Measure the bounded artifact, not the pre-truncation feature list."""
    path = Path(str(geojson_ref))
    if not path.exists():
        return 0, {
            "status": "unknown",
            "reason": "GeoJSON 导出文件不存在",
            "feature_count": 0,
            "truncated": False,
            "sources": [],
        }
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, {
            "status": "unknown",
            "reason": "GeoJSON 导出文件无法读取",
            "feature_count": 0,
            "truncated": False,
            "sources": [],
        }
    features = [item for item in document.get("features", []) if isinstance(item, dict)]
    evidence = geometry_evidence_for_features(features)
    truncated = bool((document.get("properties") or {}).get("geometry_truncated"))
    if truncated:
        evidence["status"] = "truncated_geometry"
        evidence["reason"] = "GeoJSON 摘要达到大小上限，空间要素已截断"
        evidence["truncated"] = True
    return len([item for item in features if item.get("geometry")]), evidence


def normalize_spatial_context(context: Dict[str, Any]) -> Dict[str, Any]:
    if context is None:
        return {}
    if not isinstance(context, dict):
        raise ValueError("spatial_context must be an object")
    normalized = {}
    for key in ("admin_name", "source", "crs", "geometry_type"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()[:160]
    if context.get("geometry_available") is True:
        normalized["geometry_available"] = True
    return normalized


def contextualize_request(request: str, context: Dict[str, Any]) -> str:
    admin_name = context.get("admin_name")
    if not admin_name:
        return request
    return f"{request}（当前地图选中区域：{admin_name}）"


def normalize_workflow_payload(workflow: Dict[str, Any]) -> Dict[str, Any] | None:
    if workflow is None:
        return None
    if not isinstance(workflow, dict):
        raise ValueError("workflow must be an object")
    template_id = workflow.get("template_id")
    if not isinstance(template_id, str) or not template_id.strip():
        raise ValueError("workflow.template_id must be a non-empty string")
    return normalize_workflow_selection(
        template_id.strip(),
        workflow.get("constraints", {}),
        workflow.get("evidence"),
    )


def format_result(result: AgentRunResult, spatial_context: Dict[str, Any]) -> Dict[str, Any]:
    payload = result.to_dict()
    explicit_geometry = payload.pop("geometry_evidence", None)
    if explicit_geometry is not None:
        payload["_geometry_evidence"] = explicit_geometry
    payload["spatial_context"] = spatial_context
    payload["trace_summary"] = format_trace(result)
    payload["provenance"] = build_provenance(payload)
    payload["result_type"] = result_type(payload)
    payload["result"] = build_result_contract(payload)
    payload.pop("_geometry_evidence", None)
    _attach_error_category(payload)
    return payload


def _attach_error_category(payload: Dict[str, Any]) -> None:
    """Add a bounded, machine-readable error category to failed results.

    The ``error`` string stays backward compatible; ``error_category`` uses
    the same bounded taxonomy as the async observability layer.
    """
    status = str(payload.get("status") or "")
    if status == "COMPLETED" or payload.get("error_category") is not None:
        return
    error = payload.get("error")
    if not error:
        return
    text = str(error).lower()
    category = None
    if status in {"CANCELLED", "TIMED_OUT"}:
        category = "timeout" if status == "TIMED_OUT" else "cancelled"
    elif status == "REJECTED":
        category = "rejected"
    elif status == "NEEDS_CLARIFICATION":
        category = "clarification"
    elif any(token in text for token in ("timeout", "timed out", "超时")):
        category = "timeout"
    elif any(token in text for token in ("openai", "provider", "http", "url", "socket", "network", "api")):
        category = "provider"
    elif any(token in text for token in ("planner", "plan", "schema", "规划")):
        category = "planning"
    elif any(token in text for token in ("tool", "backend", "dataset", "raster", "栅格", "数据")):
        category = "tool"
    elif status == "FAILED":
        category = "execution"
    if category:
        payload["error_category"] = category


def analysis_ready_summary(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    """Keep comparison responses tied to the same bounded health evidence."""
    health = next(
        (
            step.get("result") or {}
            for step in payload.get("steps", [])
            if step.get("tool") == "get_dataset_health_report"
        ),
        {},
    )
    evidence = health.get("analysis_ready")
    if not isinstance(evidence, dict):
        return None
    return {
        "status": evidence.get("status", "unknown"),
        "required": bool(evidence.get("required", False)),
        "derived_version": str(evidence.get("derived_version", "unknown"))[:128],
        "target_grid": dict(evidence.get("target_grid") or {}),
        "grid_alignment": dict(evidence.get("grid_alignment") or {}),
        "verification_mode": evidence.get("verification_mode", "metadata"),
        "data_readiness": health.get("data_readiness", "unknown"),
        **({"source_binding": {
            "binding_version": evidence["source_binding"].get("binding_version"),
            "fingerprint": str(evidence["source_binding"].get("fingerprint", ""))[:80],
            "verification_mode": evidence["source_binding"].get("verification_mode", "sha256"),
            "datasets": list(evidence["source_binding"].get("datasets") or [])[:10],
            "status": evidence["source_binding"].get("status", "recorded"),
        }} if isinstance(evidence.get("source_binding"), dict) else {}),
        **({"output_manifest": {
            "status": evidence["output_manifest"].get("status", "unknown"),
            "verification_mode": evidence["output_manifest"].get("verification_mode", "metadata"),
            "hashes_verified": bool(evidence["output_manifest"].get("hashes_verified", False)),
            "verified_files": int(evidence["output_manifest"].get("verified_files") or 0),
            "mismatch_count": int(evidence["output_manifest"].get("mismatch_count") or 0),
            "outputs": {
                str(name)[:32]: {
                    "reported": str(item.get("reported", ""))[:160],
                    "manifest": [str(value)[:160] for value in (item.get("manifest") or [])[:3]],
                    "matched": bool(item.get("matched", False)),
                }
                for name, item in (evidence["output_manifest"].get("outputs") or {}).items()
                if isinstance(item, dict)
            },
        }} if isinstance(evidence.get("output_manifest"), dict) else {}),
    }


def export_geometry(
    payload: Dict[str, Any],
    artifact_store: ArtifactStore,
    export_artifact: bool,
    export_geojson: bool,
    geojson_max_features: int,
    runtime,
) -> None:
    """Write artifact and bounded GeoJSON summaries into the payload in place."""
    if export_artifact:
        payload["artifact_ref"] = artifact_store.write_run(payload)
    if export_geojson:
        geometry_features = []
        for step in payload.get("steps", []):
            result_ref = (step.get("result") or {}).get("result_ref")
            if result_ref:
                exported = runtime.export_result(result_ref, max_features=geojson_max_features)
                geometry_features.extend(
                    tag_geometry_features(
                        exported.get("features", []),
                        source=exported.get("geometry_source"),
                        crs=exported.get("crs"),
                        source_crs=exported.get("source_crs"),
                        dataset=(step.get("result") or {}).get("dataset"),
                    )
                )
        payload["geojson_ref"] = export_run_summary(
            payload,
            geometry_features=geometry_features or None,
        )
        payload["_geometry_feature_count"], payload["_geometry_evidence"] = exported_geometry_evidence(payload["geojson_ref"])
