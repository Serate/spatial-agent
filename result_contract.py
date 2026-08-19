"""Build the bounded result envelope shared by API clients and the Console."""

from pathlib import Path
import math
from typing import Any, Dict, List

from agent.result_registry import ResultContractRegistry, default_result_registry

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
    )
    replanning = build_replanning_evidence(_replanning_events_from_payload(payload))
    workspace = _workspace_contract(
        result_type,
        registry=registry,
        steps=steps,
        geometry_evidence=geometry_evidence,
        geojson_ref=payload.get("geojson_ref"),
    )
    views = _view_model(
        result_type,
        steps=steps,
        geometry_evidence=geometry_evidence,
        geojson_ref=payload.get("geojson_ref"),
        workspace=workspace,
    )
    contract = {
        "type": result_type,
        "title": str(output.get("title") or registry.title_for(result_type)),
        "summary": payload.get("answer") or payload.get("error") or "暂无结果摘要。",
        "request_facts": payload.get("request_facts") or {"available": False},
        "data": {
            "evidence_steps": evidence_steps,
            "degradations": degradation["items"],
        },
        "clarification": payload.get("clarification"),
        "context": payload.get("context_evidence") or {"available": False},
        "planning": payload.get("plan_evidence") or {"available": False},
        "references": references,
        "lineage": lineage,
        "replanning": replanning,
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
    }
    if isinstance(payload.get("failure"), dict):
        contract["failure"] = dict(payload["failure"])
    return contract


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


def _view_model(
    result_type: str,
    *,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any = None,
    workspace: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    panels: Dict[str, Any] = {}
    workspace_panels = set((workspace or {}).get("panels") or [])
    raster_view = _raster_view(steps)
    if raster_view and ("raster" in workspace_panels or result_type in {"raster_metadata_result", "raster_statistics_result", "zonal_raster_statistics_result"}):
        panels["raster"] = raster_view
    overview_view = _overview_view(steps, geometry_evidence)
    if overview_view and ("overview" in workspace_panels or result_type == "spatial_overview_result"):
        panels["overview"] = overview_view
    health_view = _health_view(steps)
    if health_view and "health" in workspace_panels:
        panels["health"] = health_view
    composite_view = _composite_view(steps)
    if composite_view and "composite" in workspace_panels:
        panels["composite"] = composite_view
    buildability_view = _buildability_view(steps)
    if buildability_view and "buildability" in workspace_panels:
        panels["buildability"] = buildability_view
    vector_view = _vector_view(steps)
    if vector_view and (
        "vector" in workspace_panels
        or result_type in {"zonal_vector_summary_result", "zonal_vector_result", "vector_result", "spatial_relation_result", "spatial_result"}
    ):
        panels["vector"] = vector_view
    map_view = _map_view(steps, geometry_evidence, geojson_ref)
    if map_view and ("map" in workspace_panels or map_view.get("mode") != "none"):
        panels["map"] = map_view
    return {
        "schema_version": "spatial-agent.views.v1",
        "panels": panels,
    }


def _raster_view(steps: List[Any]) -> Dict[str, Any] | None:
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        if isinstance(result.get("metadata"), dict) and not isinstance(result.get("statistics"), dict):
            return _raster_metadata_view(step, result)
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        if _is_raster_statistics_step(step, result):
            return _raster_statistics_view(step, result)
    return None


def _is_raster_statistics_step(step: Dict[str, Any], result: Dict[str, Any]) -> bool:
    if not isinstance(result.get("statistics"), dict):
        return False
    if step.get("tool") in {"get_raster_statistics", "get_zonal_raster_statistics", "get_zonal_slope_statistics"}:
        return True
    statistics = result.get("statistics") or {}
    return any(key in statistics for key in ("minimum", "maximum", "mean", "standard_deviation", "nodata_ratio"))


def _raster_metadata_view(step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    crs_values = metadata.get("crs_values")
    if isinstance(crs_values, list) and crs_values:
        crs = "、".join(str(item) for item in crs_values[:6])
    else:
        crs = metadata.get("crs") or result.get("crs") or "未声明"
    pixel = metadata.get("pixel_size")
    if isinstance(pixel, list):
        pixel_value = " × ".join(str(item) for item in pixel[:2])
    else:
        pixel_value = pixel or "-"
    width = metadata.get("width")
    height = metadata.get("height")
    size = "{} × {}".format(width if width is not None else 0, height if height is not None else 0)
    sample_files = [str(item) for item in (result.get("sample_files") or [])[:3]]
    sample_text = "、".join(sample_files) if sample_files else "无样本文件"
    return {
        "kind": "raster_metadata",
        "source_step_id": step.get("id"),
        "source_tool": step.get("tool"),
        "title": "{} · 元数据".format(result.get("dataset") or "栅格"),
        "subtitle": str(result.get("role") or result.get("format") or "metadata")[:120],
        "dataset": result.get("dataset"),
        "metrics": [
            _view_metric("文件数", result.get("file_count", 0)),
            _view_metric("抽样文件", metrics.get("probed_files", len(sample_files))),
            _view_metric("宽×高", size),
            _view_metric("波段数", metadata.get("band_count", 0)),
            _view_metric("像元大小", pixel_value),
            _view_metric("CRS", crs),
        ],
        "note": "样本：{}".format(sample_text)[:320],
    }


def _raster_statistics_view(step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    statistics = result.get("statistics") if isinstance(result.get("statistics"), dict) else {}
    if statistics.get("error"):
        return {
            "kind": "raster_statistics",
            "source_step_id": step.get("id"),
            "source_tool": step.get("tool"),
            "title": "{} · 统计".format(result.get("dataset") or "栅格"),
            "dataset": result.get("dataset"),
            "error": str(statistics.get("error"))[:320],
            "metrics": [],
        }
    nodata_ratio = statistics.get("nodata_ratio")
    try:
        nodata_display = "{:.3f}%".format(float(nodata_ratio) * 100)
    except (TypeError, ValueError):
        nodata_display = "-"
    title = "{} · {}".format(result.get("admin_name"), result.get("dataset") or "栅格") if result.get("admin_name") else str(result.get("dataset") or "栅格")
    distribution = statistics.get("distribution") if isinstance(statistics.get("distribution"), dict) else {}
    bins = distribution.get("bins") if isinstance(distribution.get("bins"), list) else []
    coverage = {
        "valid_pixel_count": statistics.get("valid_pixel_count", 0),
        "nodata_ratio": nodata_ratio,
    }
    return {
        "kind": "raster_statistics",
        "source_step_id": step.get("id"),
        "source_tool": step.get("tool"),
        "title": title,
        "dataset": result.get("dataset"),
        "bounds": _bounds_from_result(result),
        "crs": result.get("crs"),
        "metrics": [
            _view_metric("最小值", statistics.get("minimum")),
            _view_metric("最大值", statistics.get("maximum")),
            _view_metric("平均值", statistics.get("mean")),
            _view_metric("标准差", statistics.get("standard_deviation")),
            _view_metric("有效像元", statistics.get("valid_pixel_count", 0)),
            _view_metric("NoData比例", nodata_display),
        ],
        "distribution": {
            "sample_count": distribution.get("sample_count", 0),
            "bins": bins[:30],
        } if bins else None,
        "coverage": coverage,
        "analysis": {
            "analyzed_files": (result.get("metrics") or {}).get("analyzed_files", 0) if isinstance(result.get("metrics"), dict) else 0,
            "file_count": result.get("file_count", 0),
        },
    }


def _overview_view(steps: List[Any], geometry_evidence: Dict[str, Any]) -> Dict[str, Any]:
    datasets = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        dataset = result.get("dataset")
        if dataset:
            datasets.append(str(dataset))
        for item in result.get("datasets") or []:
            if isinstance(item, dict) and item.get("dataset"):
                datasets.append(str(item["dataset"]))
            elif isinstance(item, str):
                datasets.append(item)
    unique_datasets = sorted(set(datasets))
    status = str(geometry_evidence.get("status") or "unknown")
    status_label = {
        "truncated_geometry": "已截断",
        "real_geometry": "可绘制",
        "boundary_geometry": "边界可绘制",
        "no_geometry": "无几何",
        "unknown": "摘要",
    }.get(status, status)
    return {
        "kind": "spatial_overview",
        "source_step_id": None,
        "title": "空间总览摘要",
        "metrics": [
            _view_metric("工具步骤", len([step for step in steps if isinstance(step, dict)])),
            _view_metric("数据来源", len(unique_datasets) or "-"),
            _view_metric("空间要素", geometry_evidence.get("feature_count", 0)),
            _view_metric("空间证据", status_label),
        ],
        "datasets": unique_datasets[:20],
        "note": "行政区、道路、水体图层使用不同颜色；{}".format(
            geometry_evidence.get("reason") or "空间证据由最终结果生成。"
        )[:320],
    }


def _map_view(
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any,
) -> Dict[str, Any] | None:
    status = str(geometry_evidence.get("status") or "unknown")
    if status in {"real_geometry", "boundary_geometry"} and geojson_ref:
        return {
            "kind": "map",
            "mode": "geojson",
            "geojson_ref": geojson_ref,
            "reason": str(geometry_evidence.get("reason") or "GeoJSON 空间要素可绘制")[:240],
            "feature_count": geometry_evidence.get("feature_count", 0),
        }
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        bounds = _bounds_from_result(result)
        if bounds:
            metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
            return {
                "kind": "map",
                "mode": "raster_bounds",
                "bounds": bounds,
                "dataset": result.get("dataset"),
                "crs": result.get("crs") or metadata.get("crs"),
                "source_step_id": step.get("id"),
                "reason": "工具结果包含栅格范围，可绘制覆盖范围预览。",
            }
    return None


def _health_view(steps: List[Any]) -> Dict[str, Any] | None:
    step, result = _first_step_result(steps, tool="get_dataset_health_report")
    if not result:
        return None
    labels = {
        "ready": "可用",
        "degraded": "部分可用",
        "unavailable": "不可用",
        "warning": "警告",
        "unknown": "未知",
    }
    rows = []
    for item in result.get("datasets") or []:
        if not isinstance(item, dict):
            continue
        count = ""
        if item.get("feature_count") is not None:
            count = "{} 个要素".format(item.get("feature_count"))
        elif item.get("file_count") is not None:
            count = "{} 个文件".format(item.get("file_count"))
        details = []
        for check in item.get("checks") or []:
            if isinstance(check, dict) and check.get("status") != "passed" and check.get("message"):
                details.append(str(check["message"]))
        if not details:
            details.append("基础检查通过")
        usable_for = [str(tool) for tool in (item.get("usable_for") or [])[:8]]
        rows.append({
            "dataset": item.get("dataset"),
            "status": item.get("status") or item.get("quality") or "unknown",
            "status_label": labels.get(str(item.get("status") or item.get("quality") or "unknown"), str(item.get("status") or item.get("quality") or "未知")),
            "count": count,
            "detail": "；".join(details[:3])[:240],
            "usable_for": usable_for,
        })
    relationships = result.get("relationships") if isinstance(result.get("relationships"), dict) else {}
    alignment = relationships.get("dem_land_use") if isinstance(relationships.get("dem_land_use"), dict) else None
    return {
        "kind": "dataset_health",
        "source_step_id": step.get("id") if step else None,
        "source_tool": step.get("tool") if step else None,
        "title": "数据健康检查",
        "status": result.get("status") or "unknown",
        "metrics": [
            _view_metric("整体状态", labels.get(str(result.get("status") or "unknown"), result.get("status") or "未知")),
            _view_metric("核心数据", labels.get(str(result.get("core_status") or "unknown"), result.get("core_status") or "未检查")),
            _view_metric("可选数据", labels.get(str(result.get("optional_status") or "unknown"), result.get("optional_status") or "未检查")),
            _view_metric("数据集", len(rows)),
        ],
        "rows": rows[:40],
        "alignment": {
            "label": "DEM/土地利用覆盖关系",
            "status": alignment.get("status") if alignment else None,
            "status_label": labels.get(str(alignment.get("status")) if alignment else "unknown", str(alignment.get("status")) if alignment else "未知"),
            "overlapping_pairs": alignment.get("overlapping_pairs") if alignment else None,
        } if alignment else None,
        "note": str(result.get("warning") or "健康检查不代表数据的法定权威性。")[:320],
    }


def _composite_view(steps: List[Any]) -> Dict[str, Any] | None:
    _, elevation = _first_step_result(steps, tool="get_zonal_raster_statistics")
    _, slope = _first_step_result(steps, tool="get_zonal_slope_statistics")
    _, land = _first_step_result(steps, tool="get_zonal_land_use_distribution")
    elevation_stats = elevation.get("statistics") if isinstance(elevation.get("statistics"), dict) else {}
    slope_stats = slope.get("statistics") if isinstance(slope.get("statistics"), dict) else {}
    land_stats = land.get("statistics") if isinstance(land.get("statistics"), dict) else {}
    if not elevation_stats and not slope_stats and not land_stats:
        return None
    metrics = []
    if elevation_stats and not elevation_stats.get("error"):
        metrics.append(_view_metric("高程均值（米）", elevation_stats.get("mean")))
    if slope_stats and not slope_stats.get("error"):
        metrics.append(_view_metric("坡度均值（度）", slope_stats.get("mean")))
    if land_stats and not land_stats.get("error"):
        metrics.append(_view_metric("土地利用类别", land_stats.get("category_count", len(land_stats.get("categories") or []))))
    categories = []
    for item in (land_stats.get("categories") or [])[:12]:
        if not isinstance(item, dict):
            continue
        categories.append({
            "value": item.get("value"),
            "label": "{} 类".format(item.get("value")),
            "share": item.get("share"),
            "count": item.get("count"),
        })
    return {
        "kind": "spatial_composite",
        "title": "综合空间分析",
        "metrics": metrics,
        "categories": categories,
        "note": "土地利用类别按栅格编码统计，未对编码进行人为语义映射。" if categories else "综合分析结果由高程、坡度与土地利用步骤汇总生成。",
    }


def _buildability_view(steps: List[Any]) -> Dict[str, Any] | None:
    step, result = _first_step_result(steps, tool="get_zonal_buildability_analysis")
    if not result:
        for candidate_step in steps:
            if not isinstance(candidate_step, dict):
                continue
            candidate = candidate_step.get("result") if isinstance(candidate_step.get("result"), dict) else {}
            statistics = candidate.get("statistics") if isinstance(candidate.get("statistics"), dict) else {}
            if "candidate_ratio" in statistics or "candidate_pixel_count" in statistics:
                step, result = candidate_step, candidate
                break
    if not result:
        return None
    statistics = result.get("statistics") if isinstance(result.get("statistics"), dict) else {}
    if statistics.get("error"):
        return {
            "kind": "buildability_screening",
            "source_step_id": step.get("id") if step else None,
            "source_tool": step.get("tool") if step else None,
            "title": "建设适宜性筛选",
            "error": str(statistics.get("error"))[:320],
            "metrics": [],
        }
    ratio = statistics.get("candidate_ratio")
    try:
        ratio_display = "{:.2f}%".format(float(ratio) * 100)
    except (TypeError, ValueError):
        ratio_display = "-"
    return {
        "kind": "buildability_screening",
        "source_step_id": step.get("id") if step else None,
        "source_tool": step.get("tool") if step else None,
        "title": "建设适宜性筛选",
        "metrics": [
            _view_metric("候选像元比例", ratio_display),
            _view_metric("候选像元", statistics.get("candidate_pixel_count", 0)),
            _view_metric("坡度阈值", "{}°".format(statistics.get("slope_limit_degrees")) if statistics.get("slope_limit_degrees") is not None else "-"),
        ],
        "coverage": {
            "candidate_ratio": ratio,
            "candidate_pixel_count": statistics.get("candidate_pixel_count", 0),
            "valid_pixel_count": statistics.get("valid_pixel_count", 0),
        },
        "note": str((result.get("rules") or {}).get("warning") or "仅用于演示筛选，不代表规划许可结论。")[:320] if isinstance(result.get("rules"), dict) else "仅用于演示筛选，不代表规划许可结论。",
    }


def _vector_view(steps: List[Any]) -> Dict[str, Any] | None:
    for tool, builder in (
        ("get_zonal_vector_summary", _zonal_vector_summary_view),
        ("spatial_join", _spatial_relation_view),
        ("range_query", _vector_query_view),
    ):
        step, result = _first_step_result(steps, tool=tool)
        if result:
            return builder(step or {}, result)
    return None


def _vector_query_view(step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    dataset = _first_present(result.get("dataset"), args.get("dataset"))
    count = _first_present(result.get("count"), metrics.get("returned_features"), metrics.get("feature_count"))
    rows = [
        _view_row("数据集", dataset),
        _view_row("结果引用", result.get("result_ref")),
    ]
    if metrics.get("source") is not None:
        rows.append(_view_row("来源", metrics.get("source")))
    return {
        "kind": "vector_query",
        "source_step_id": step.get("id"),
        "source_tool": step.get("tool"),
        "title": "矢量查询结果",
        "metrics": [
            _view_metric("要素数", count),
            _view_metric("CRS", _first_present(result.get("crs"), metrics.get("crs"))),
            _view_metric("后端", metrics.get("backend")),
        ],
        "rows": rows[:8],
        "note": "矢量结果只保留摘要、引用和可展示指标；原始几何通过 artifact/GeoJSON 引用查看。"[:320],
    }


def _zonal_vector_summary_view(step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    category_counts = summary.get("category_counts") if isinstance(summary.get("category_counts"), dict) else {}
    rows = [
        _view_row("数据集", _first_present(result.get("dataset"), args.get("dataset"))),
        _view_row("行政区", _first_present(result.get("admin_name"), args.get("admin_name"))),
    ]
    table_rows = sorted(
        ([str(label), count] for label, count in category_counts.items()),
        key=lambda item: (-_numeric_sort_value(item[1]), item[0]),
    )[:20]
    return {
        "kind": "zonal_vector_summary",
        "source_step_id": step.get("id"),
        "source_tool": step.get("tool"),
        "title": "区域矢量摘要",
        "metrics": [
            _view_metric("相交要素", _first_present(summary.get("matched_features"), summary.get("feature_count"), result.get("count"))),
            _view_metric("返回几何", summary.get("returned_features")),
            _view_metric("已命名要素", summary.get("named_features")),
        ],
        "rows": rows[:8],
        "table": {
            "columns": ["类别", "数量"],
            "rows": table_rows,
        },
        "note": "分类表按数量降序展示，最多保留 20 类；不直接内联原始几何。"[:320],
    }


def _spatial_relation_view(step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    rows = [
        _view_row("左侧数据集", _first_present(result.get("left_dataset"), args.get("left_dataset"))),
        _view_row("右侧数据集", _first_present(result.get("right_dataset"), args.get("right_dataset"))),
        _view_row("结果引用", result.get("result_ref")),
        _view_row("CRS", _first_present(result.get("crs"), metrics.get("crs"))),
    ]
    return {
        "kind": "spatial_relation",
        "source_step_id": step.get("id"),
        "source_tool": step.get("tool"),
        "title": "空间关系结果",
        "metrics": [
            _view_metric("关系要素", _first_present(result.get("count"), metrics.get("returned_features"), metrics.get("feature_count"))),
            _view_metric("关系", _first_present(result.get("relation"), args.get("relation"))),
            _view_metric("距离", _distance_label(_first_present(result.get("distance_m"), args.get("distance_m")))),
        ],
        "rows": [row for row in rows if row.get("value") != "-"][:8],
        "note": "空间关系结果展示有界摘要；详细要素应通过结果引用导出。"[:320],
    }


def _first_step_result(steps: List[Any], *, tool: str) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    for step in steps:
        if not isinstance(step, dict) or step.get("tool") != tool:
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        return step, result
    return None, {}


def _bounds_from_result(result: Dict[str, Any]) -> List[float] | None:
    bounds = result.get("bounds")
    if _is_bounds(bounds):
        return [float(item) for item in bounds]
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and _is_bounds(metadata.get("bounds")):
        return [float(item) for item in metadata["bounds"]]
    return None


def _view_metric(label: str, value: Any) -> Dict[str, Any]:
    return {
        "label": str(label)[:80],
        "value": "-" if value is None else value,
    }


def _view_row(label: str, value: Any) -> Dict[str, Any]:
    if value is None or value == "":
        display = "-"
    elif isinstance(value, (int, float, bool)):
        display = value
    else:
        display = str(value)[:220]
    return {
        "label": str(label)[:80],
        "value": display,
    }


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _numeric_sort_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _distance_label(value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        return "{} 米".format(int(float(value)))
    except (TypeError, ValueError):
        return value


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
    return {
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
    }


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

_SPATIAL_RESULT_TYPES = {
    "spatial_analysis_result",
    "spatial_overview_result",
    "terrain_land_use_analysis_result",
    "admin_area_result",
    "zonal_raster_statistics_result",
    "raster_statistics_result",
}


def _degradation_matrix(
    payload: Dict[str, Any],
    *,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    result_type: str,
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
    elif geometry_status == "unknown" and result_type in _SPATIAL_RESULT_TYPES and steps:
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
