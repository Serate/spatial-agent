"""Build the bounded result envelope shared by API clients and the Console."""

from typing import Any, Dict, List


TITLE_BY_TYPE = {
    "direct_answer": "通用回答",
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
    return {
        "type": result_type,
        "title": str(output.get("title") or TITLE_BY_TYPE.get(result_type, "空间分析结果")),
        "summary": payload.get("answer") or payload.get("error") or "暂无结果摘要。",
        "data": {"evidence_steps": evidence_steps},
        "references": references,
        "geometry": {
            "available": geometry_evidence["status"] in {"real_geometry", "boundary_geometry"},
            "status": geometry_evidence["status"],
            "reason": geometry_evidence["reason"],
            "feature_count": geometry_evidence["feature_count"],
            "truncated": geometry_evidence["truncated"],
            "geojson_ref": payload.get("geojson_ref"),
            "sources": sorted(geometry_sources),
            "crs": sorted(geometry_crs),
        },
    }


def _geometry_evidence(payload: Dict[str, Any], geometry_sources) -> Dict[str, Any]:
    explicit = payload.get("_geometry_evidence")
    if isinstance(explicit, dict):
        status = explicit.get("status") if explicit.get("status") in GEOMETRY_STATUS else "unknown"
        return {
            "status": status,
            "reason": str(explicit.get("reason") or "运行结果未提供几何证据")[:240],
            "feature_count": int(explicit.get("feature_count") or 0),
            "truncated": bool(explicit.get("truncated")),
        }
    if payload.get("_geometry_feature_count"):
        status = "boundary_geometry" if geometry_sources == {"geojson"} else "real_geometry"
        return {
            "status": status,
            "reason": "导出摘要包含真实空间要素",
            "feature_count": int(payload.get("_geometry_feature_count") or 0),
            "truncated": False,
        }
    if payload.get("geojson_ref"):
        return {
            "status": "no_geometry",
            "reason": "GeoJSON 引用存在，但摘要没有可绘制空间要素",
            "feature_count": 0,
            "truncated": False,
        }
    return {
        "status": "unknown",
        "reason": "本次运行尚未生成空间导出证据",
        "feature_count": 0,
        "truncated": False,
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
