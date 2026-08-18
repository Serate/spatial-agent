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
    "spatial_analysis_result": "综合空间分析",
    "buildability_result": "建设适宜性筛选",
    "buildability_comparison": "建设适宜性对比",
    "constrained_buildability_result": "约束建设候选筛选",
    "dataset_health_result": "数据健康检查",
    "zonal_vector_summary_result": "区域矢量摘要",
    "vector_result": "矢量结果",
    "spatial_relation_result": "空间关系",
    "spatial_result": "空间结果",
    "unknown": "空间分析结果",
}

WORKSPACE_PANELS_BY_TYPE = {
    "direct_answer": [],
    "spatial_overview_result": ["overview"],
    "spatial_analysis_result": ["raster", "composite"],
    "terrain_land_use_analysis_result": ["raster", "composite"],
    "admin_area_result": [],
    "raster_metadata_result": ["raster"],
    "raster_statistics_result": ["raster"],
    "zonal_raster_statistics_result": ["raster"],
    "dataset_health_result": ["health"],
    "buildability_result": ["raster", "buildability", "compare"],
    "buildability_comparison": ["buildability", "compare"],
    "constrained_buildability_result": ["buildability", "compare"],
    "zonal_vector_summary_result": ["vector"],
    "vector_result": ["vector"],
    "spatial_relation_result": ["vector"],
    "spatial_result": ["vector"],
}

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
    degradation = _degradation_matrix(
        payload,
        steps=steps,
        geometry_evidence=geometry_evidence,
        result_type=result_type,
    )
    workspace = _workspace_contract(
        result_type,
        steps=steps,
        geometry_evidence=geometry_evidence,
        geojson_ref=payload.get("geojson_ref"),
    )
    return {
        "type": result_type,
        "title": str(output.get("title") or TITLE_BY_TYPE.get(result_type, "空间分析结果")),
        "summary": payload.get("answer") or payload.get("error") or "暂无结果摘要。",
        "data": {
            "evidence_steps": evidence_steps,
            "degradations": degradation["items"],
        },
        "clarification": payload.get("clarification"),
        "context": payload.get("context_evidence") or {"available": False},
        "planning": payload.get("plan_evidence") or {"available": False},
        "references": references,
        "lineage": lineage,
        "degradation": degradation,
        "workspace": workspace,
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


def _workspace_contract(
    result_type: str,
    *,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any = None,
) -> Dict[str, Any]:
    registered = result_type in WORKSPACE_PANELS_BY_TYPE
    panels = list(WORKSPACE_PANELS_BY_TYPE.get(result_type, []))
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
