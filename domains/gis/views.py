"""GIS-owned result view builders.

The public result envelope only knows how to dispatch a Domain Pack view
builder.  GIS-specific tool names, labels and panel models live here so a
different Domain Pack can provide its own views without editing the generic
contract.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_views(
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
    if raster_view and (
        "raster" in workspace_panels
        or result_type in {
            "raster_metadata_result",
            "raster_statistics_result",
            "zonal_raster_statistics_result",
        }
    ):
        panels["raster"] = raster_view
    overview_view = _overview_view(steps, geometry_evidence)
    if overview_view and (
        "overview" in workspace_panels or result_type == "spatial_overview_result"
    ):
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
        or result_type
        in {
            "zonal_vector_summary_result",
            "zonal_vector_result",
            "vector_result",
            "spatial_relation_result",
            "spatial_operation_result",
            "spatial_result",
        }
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
        if isinstance(result.get("metadata"), dict) and not isinstance(
            result.get("statistics"), dict
        ):
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
    if step.get("tool") in {
        "get_raster_statistics",
        "get_zonal_raster_statistics",
        "get_zonal_slope_statistics",
    }:
        return True
    statistics = result.get("statistics") or {}
    return any(
        key in statistics
        for key in (
            "minimum",
            "maximum",
            "mean",
            "standard_deviation",
            "nodata_ratio",
        )
    )


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
    title = (
        "{} · {}".format(result.get("admin_name"), result.get("dataset") or "栅格")
        if result.get("admin_name")
        else str(result.get("dataset") or "栅格")
    )
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
        }
        if bins
        else None,
        "coverage": coverage,
        "analysis": {
            "analyzed_files": (result.get("metrics") or {}).get("analyzed_files", 0)
            if isinstance(result.get("metrics"), dict)
            else 0,
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
    if status in {"real_geometry", "boundary_geometry", "truncated_geometry"} and geojson_ref:
        return {
            "kind": "map",
            "mode": "geojson",
            "geojson_ref": geojson_ref,
            "reason": str(
                geometry_evidence.get("reason")
                or (
                    "GeoJSON 空间要素可绘制（结果已截断，当前为部分几何）"
                    if status == "truncated_geometry"
                    else "GeoJSON 空间要素可绘制"
                )
            )[:240],
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
                "coverage_kind": "bounds_only",
                "reason": "当前只有栅格外接范围；不代表有效像元覆盖或分析区域。",
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
        rows.append(
            {
                "dataset": item.get("dataset"),
                "status": item.get("status") or item.get("quality") or "unknown",
                "status_label": labels.get(
                    str(item.get("status") or item.get("quality") or "unknown"),
                    str(item.get("status") or item.get("quality") or "未知"),
                ),
                "count": count,
                "detail": "；".join(details[:3])[:240],
                "usable_for": usable_for,
            }
        )
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
            "status_label": labels.get(
                str(alignment.get("status")) if alignment else "unknown",
                str(alignment.get("status")) if alignment else "未知",
            ),
            "overlapping_pairs": alignment.get("overlapping_pairs") if alignment else None,
        }
        if alignment
        else None,
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
        metrics.append(
            _view_metric(
                "土地利用类别",
                land_stats.get("category_count", len(land_stats.get("categories") or [])),
            )
        )
    categories = []
    for item in (land_stats.get("categories") or [])[:12]:
        if not isinstance(item, dict):
            continue
        categories.append(
            {
                "value": item.get("value"),
                "label": "{} 类".format(item.get("value")),
                "share": item.get("share"),
                "count": item.get("count"),
            }
        )
    return {
        "kind": "spatial_composite",
        "title": "综合空间分析",
        "metrics": metrics,
        "categories": categories,
        "note": "土地利用类别按栅格编码统计，未对编码进行人为语义映射。"
        if categories
        else "综合分析结果由高程、坡度与土地利用步骤汇总生成。",
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
            _view_metric(
                "坡度阈值",
                "{}°".format(statistics.get("slope_limit_degrees"))
                if statistics.get("slope_limit_degrees") is not None
                else "-",
            ),
        ],
        "coverage": {
            "candidate_ratio": ratio,
            "candidate_pixel_count": statistics.get("candidate_pixel_count", 0),
            "valid_pixel_count": statistics.get("valid_pixel_count", 0),
        },
        "note": str((result.get("rules") or {}).get("warning") or "仅用于演示筛选，不代表规划许可结论。")[:320]
        if isinstance(result.get("rules"), dict)
        else "仅用于演示筛选，不代表规划许可结论。",
    }


def _vector_view(steps: List[Any]) -> Dict[str, Any] | None:
    for tool, builder in (
        ("get_zonal_vector_summary", _zonal_vector_summary_view),
        ("spatial_operation", _spatial_operation_view),
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
            _view_metric(
                "相交要素",
                _first_present(summary.get("matched_features"), summary.get("feature_count"), result.get("count")),
            ),
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
    overlap_label = "输入要素" if str(operation) in {"buffer", "distance"} else "相交要素"
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


def _spatial_operation_view(step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    operation = _first_present(result.get("operation"), args.get("operation"))
    operation_label = {
        "clip": "裁剪",
        "intersect": "相交",
        "buffer": "缓冲",
        "distance": "距离测算",
    }.get(str(operation), operation)
    rows = [
        _view_row("输入", _first_present(result.get("input_ref"), args.get("input_ref"))),
        _view_row("掩膜", _first_present(result.get("mask_ref"), args.get("mask_ref"))),
        _view_row("结果引用", result.get("result_ref")),
        _view_row("CRS", _first_present(result.get("crs"), summary.get("crs"))),
    ]
    return {
        "kind": "spatial_operation",
        "source_step_id": step.get("id"),
        "source_tool": step.get("tool"),
        "title": "空间算子结果",
        "metrics": [
            _view_metric("操作", operation_label),
            _view_metric("返回要素", _first_present(result.get("count"), summary.get("returned_features"))),
            _view_metric(overlap_label, summary.get("intersecting_features")),
            _view_metric("距离阈值", _distance_label(result.get("distance_m"))),
            _view_metric("最近距离均值", _distance_label(summary.get("nearest_distance_mean_m"))),
            _view_metric("是否截断", _first_present(summary.get("truncated"), metrics.get("truncated"))),
        ],
        "rows": [row for row in rows if row.get("value") != "-"][:8],
        "note": "结果由已注册的空间算子生成；详细几何通过地图或 artifact 查看。"[:320],
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


def _is_bounds(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
    )


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
