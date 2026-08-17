"""Build the bounded result envelope shared by API clients and the Console."""

from pathlib import Path
from typing import Any, Dict, List


TITLE_BY_TYPE = {
    "direct_answer": "通用回答",
    "spatial_overview_result": "区域空间总览",
    "admin_area_result": "行政区边界",
    "raster_metadata_result": "栅格元数据",
    "raster_statistics_result": "栅格统计",
    "zonal_raster_statistics_result": "区域栅格统计",
    "terrain_land_use_analysis_result": "综合空间分析",
    "unknown": "空间分析结果",
}

GEOMETRY_STATUS = {
    "real_geometry",
    "boundary_geometry",
    "no_geometry",
    "truncated_geometry",
    "unknown",
}


def build_result_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
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
        })

    if payload.get("geojson_ref"):
        references.append({"kind": "geojson", "ref": payload["geojson_ref"]})

    geometry_evidence = _geometry_evidence(payload, geometry_sources)
    lineage = build_lineage_index(
        payload,
        steps=steps,
        geometry_evidence=geometry_evidence,
    )
    return {
        "type": result_type,
        "title": str(output.get("title") or TITLE_BY_TYPE.get(result_type, "空间分析结果")),
        "summary": payload.get("answer") or payload.get("error") or "暂无结果摘要。",
        "data": {"evidence_steps": evidence_steps},
        "clarification": payload.get("clarification"),
        "context": payload.get("context_evidence") or {"available": False},
        "planning": payload.get("plan_evidence") or {"available": False},
        "references": references,
        "lineage": lineage,
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
    }


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
    if error:
        summary["error"] = str(error)
    return summary
