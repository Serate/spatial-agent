from typing import Any, Dict, Iterable, Optional

from agent.models import AgentRunResult, StepRun


class AnswerComposer:
    """Turns completed tool traces into a user-facing answer."""

    def compose(self, result: AgentRunResult) -> str:
        output_type = result.plan.output.get("type") if result.plan else None
        has_elevation = _first_result(result.steps, "get_zonal_raster_statistics") is not None
        has_slope = _first_result(result.steps, "get_zonal_slope_statistics") is not None
        has_land_use = _first_result(result.steps, "get_zonal_land_use_distribution") is not None
        has_buildability = _first_result(result.steps, "get_zonal_buildability_analysis") is not None
        output_type = result.plan.output.get("type") if result.plan else None
        if output_type == "spatial_analysis_result":
            return self._compose_spatial_analysis_result(result.steps)
        if output_type == "spatial_overview_result":
            return self._compose_spatial_overview_result(result.steps)
        if has_elevation and (has_slope or has_land_use or has_buildability):
            return self._compose_terrain_land_use_result(result.steps)
        if output_type == "admin_area_result":
            return self._compose_admin_area_result(result.steps)
        if output_type == "vector_result":
            return self._compose_vector_result(result.steps)
        if output_type == "zonal_vector_result":
            return self._compose_zonal_vector_result(result.steps)
        if output_type == "spatial_relation_result":
            return self._compose_spatial_relation_result(result.steps)
        if output_type == "spatial_operation_result":
            return self._compose_spatial_operation_result(result.steps)
        if output_type == "constrained_buildability_result":
            return self._compose_constrained_buildability_result(result.steps)
        if output_type == "dataset_health_result":
            return self._compose_dataset_health_result(result.steps)
        if output_type == "raster_metadata_result":
            return self._compose_raster_metadata_result(result.steps)
        if output_type == "raster_statistics_result":
            return self._compose_raster_statistics_result(result.steps)
        if output_type == "zonal_raster_statistics_result":
            return self._compose_zonal_raster_statistics_result(result.steps)
        if output_type == "terrain_land_use_analysis_result":
            return self._compose_terrain_land_use_result(result.steps)
        if has_buildability:
            return self._compose_buildability_result(result.steps)
        if has_land_use:
            return self._compose_land_use_result(result.steps)
        if has_slope:
            return self._compose_slope_result(result.steps)
        if _first_result(result.steps, "get_raster_statistics") is not None:
            return self._compose_raster_statistics_result(result.steps)
        if _first_result(result.steps, "get_zonal_raster_statistics") is not None:
            return self._compose_zonal_raster_statistics_result(result.steps)
        if _first_result(result.steps, "get_raster_metadata") is not None:
            return self._compose_raster_metadata_result(result.steps)
        return self._compose_default(result.steps)

    def compose_failure(self, result: AgentRunResult) -> str:
        """Explain a failed run while preserving preflight evidence."""
        health = _first_result(result.steps, "get_dataset_health_report") or {}
        error = result.error or "未知执行错误"
        if "数据预检阻止工具" in error:
            return "这次分析已暂停，因为所需数据没有通过可用性检查。请先补齐或切换数据源，再重新执行。"
        if health.get("status") == "unavailable":
            return "这次分析没有完成：所需空间数据当前不可用。请检查本地 GIS 数据和运行环境后重试。"
        return f"这次分析没有完成：{_friendly_error(error)}"

    def _compose_dataset_health_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_dataset_health_report") or {}
        status = result.get("status", "unknown")
        labels = {"ready": "可用", "degraded": "部分可用", "unavailable": "不可用"}
        reports = result.get("datasets") or []
        available = []
        unavailable = []
        for item in reports:
            name = item.get("dataset", "未知数据集")
            label = labels.get(item.get("status"), item.get("status", "未知"))
            if item.get("status") in {"ready", "degraded"}:
                available.append(f"{name}（{label}）")
            else:
                unavailable.append(str(name))
        parts = [f"数据检查完成，整体{labels.get(status, '状态未知')}。"]
        if available:
            parts.append("可用数据包括：" + "、".join(available) + "。")
        if unavailable:
            parts.append("暂不可用：" + "、".join(unavailable) + "。")
        note = result.get("warning") or _user_health_note(result)
        if note:
            parts.append(str(note).rstrip("。") + "。")
        return "".join(parts)

    def _compose_spatial_overview_result(self, steps: Iterable[StepRun]) -> str:
        return self._compose_spatial_analysis_result(steps)

    def _compose_spatial_analysis_result(self, steps: Iterable[StepRun]) -> str:
        """Create a short conclusion first; execution details remain in evidence."""
        steps = list(steps)
        health = _first_result(steps, "get_dataset_health_report") or {}
        elevation = _first_result(steps, "get_zonal_raster_statistics")
        slope = _first_result(steps, "get_zonal_slope_statistics")
        land_use = _first_result(steps, "get_zonal_land_use_distribution")
        area = next((step.result.get("admin_name") for step in steps if step.result and step.result.get("admin_name")), "指定区域")
        findings = []
        raster_stats = [item.get("statistics") or {} for item in (elevation, slope) if item]
        valid_counts = [item.get("valid_pixel_count") for item in raster_stats if item.get("valid_pixel_count") is not None and not item.get("error")]
        if elevation or slope:
            if any(item.get("error") for item in raster_stats):
                findings.append("高程或坡度统计未能完整返回，请查看空间结果中的具体提示。")
            elif valid_counts:
                findings.append(f"高程和坡度统计已完成，覆盖{_approx_pixels(max(valid_counts))}有效像元。")
        if land_use:
            statistics = land_use.get("statistics") or {}
            if statistics.get("error"):
                findings.append("土地利用统计未能完成，请查看空间结果中的具体提示。")
            else:
                category_count = statistics.get("category_count")
                suffix = f"，识别出 {_fmt_count(category_count)} 个类别" if category_count is not None else ""
                findings.append(f"土地利用数据已完成汇总{suffix}。")
        for step in steps:
            if step.tool != "get_zonal_vector_summary" or not step.result:
                continue
            summary = step.result.get("summary") or {}
            dataset = step.result.get("dataset")
            label = "道路" if dataset == "roads" else "水体" if dataset == "water" else "相关矢量数据"
            count = summary.get("matched_features", summary.get("feature_count", step.result.get("count", 0)))
            findings.append(f"{label}约 {_fmt_count(count)} 条。")
        constrained = _first_result(steps, "get_zonal_constrained_buildability_analysis")
        buildability = constrained or _first_result(steps, "get_zonal_buildability_analysis")
        if buildability:
            statistics = buildability.get("statistics") or {}
            if statistics.get("error"):
                findings.append("建设候选筛选未能完成，请先检查 DEM、土地利用和道路数据是否对齐。")
            else:
                ratio = statistics.get("candidate_ratio")
                ratio_text = f"约 {float(ratio) * 100:.1f}%" if ratio is not None else "一部分"
                findings.append(f"按当前演示条件筛得{ratio_text}的候选区域。")
        failed = [step for step in steps if step.status == "FAILED"]
        blocked = [step for step in steps if step.status == "BLOCKED"]
        if failed or blocked:
            findings.append(f"有 {_fmt_count(len(failed) + len(blocked))} 项分析未完成，已保留在执行详情中。")
        if not findings:
            findings.append("结果已生成，但当前没有可提炼的统计摘要。")
        note = "建设候选区域仅用于演示筛选，不代表法定规划或许可结论。" if buildability else "以上结论仅反映当前数据中的统计事实。"
        health_note = _user_health_note(health)
        if health_note:
            note = health_note + " " + note
        return f"{area}综合空间分析已完成。\n\n主要发现：\n- " + "\n- ".join(findings) + f"\n\n需要注意：{note}"

    def _compose_slope_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_slope_statistics")
        statistics = (result or {}).get("statistics", {})
        area = (result or {}).get("admin_name", "指定区域")
        if statistics.get("error"):
            return f"{area}的坡度分析没有完成：{_friendly_error(statistics['error'])}。"
        return (
            f"{area}的坡度分析已完成。坡度约在 {_fmt_number(statistics.get('minimum'))}–"
            f"{_fmt_number(statistics.get('maximum'))} 度之间，平均约 {_fmt_number(statistics.get('mean'))} 度，"
            f"覆盖{_approx_pixels(statistics.get('valid_pixel_count', 0))}有效像元。"
        )

    def _compose_land_use_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_land_use_distribution")
        statistics = (result or {}).get("statistics", {})
        area = (result or {}).get("admin_name", "指定区域")
        if statistics.get("error"):
            return f"{area}的土地利用分析没有完成：{_friendly_error(statistics['error'])}。"
        categories = statistics.get("categories", [])[:5]
        category_text = "、".join(
            f"{item.get('value')}类 {_fmt_number(float(item.get('share', 0)) * 100, 1)}%"
            for item in categories
        ) or "暂无"
        return (
            f"{area}的土地利用分布分析已完成，共识别 {_fmt_count(statistics.get('category_count', 0))} 个类别，"
            f"覆盖{_approx_pixels(statistics.get('valid_pixel_count', 0))}有效像元。主要类别：{category_text}。"
        )

    def _compose_buildability_result(self, steps: Iterable[StepRun]) -> str:
        health = _first_result(steps, "get_dataset_health_report") or {}
        result = _first_result(steps, "get_zonal_buildability_analysis")
        statistics = (result or {}).get("statistics", {})
        area = (result or {}).get("admin_name", "指定区域")
        if statistics.get("error"):
            return f"{area}的建设候选筛选没有完成：{_friendly_error(statistics['error'])}。"
        ratio = statistics.get("candidate_ratio")
        ratio_text = "未知" if ratio is None else f"{float(ratio) * 100:.1f}%"
        health_note = _user_health_note(health)
        note = (health_note + " ") if health_note else ""
        return (
            f"{area}的建设候选演示筛选已完成：约 {ratio_text} 的有效区域满足当前条件，"
            f"坡度阈值为 {_fmt_number(statistics.get('slope_limit_degrees'))} 度。"
            f"{note}以上仅用于演示，不代表法定建设适宜性或规划许可结论。"
        )

    def _compose_terrain_land_use_result(self, steps: Iterable[StepRun]) -> str:
        return self._compose_spatial_analysis_result(steps)

    def _compose_admin_area_result(self, steps: Iterable[StepRun]) -> str:
        range_result = _first_result(steps, "range_query")
        if range_result is None:
            return _zh("行政区查询已完成，但没有找到可展示的查询结果。")

        count = int(range_result.get("count", 0) or 0)
        names = range_result.get("sample_names") or []
        if count == 0:
            return _zh("没有找到匹配的行政区边界，请检查区域名称后重试。")
        name_text = _join_names(names) if names else _zh("目标区域")
        return _zh("已找到 {count} 个行政区边界：{names}。空间结果已准备好，可在地图中查看。 ").format(
            count=_fmt_count(count),
            names=name_text,
        ).strip()

    def _compose_vector_result(self, steps: Iterable[StepRun]) -> str:
        schema = _first_result(steps, "get_dataset_schema") or {}
        result = _first_result(steps, "range_query") or {}
        dataset = result.get("dataset") or schema.get("dataset") or "空间数据"
        count = result.get("count", 0)
        names = result.get("sample_names") or []
        label = "道路" if dataset == "roads" else "水体" if dataset == "water" else dataset
        detail = f"已查询{label}约 {_fmt_count(count)} 条"
        if names:
            detail += f"，名称样例：{'、'.join(names[:5])}"
        return f"{detail}。这是演示数据的统计结果，不代表法定道路或水体边界。"

    def _compose_zonal_vector_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_vector_summary") or {}
        summary = result.get("summary") or {}
        area = result.get("admin_name", "指定区域")
        dataset = result.get("dataset", "vector")
        label = "道路" if dataset == "roads" else "水体"
        if summary.get("error"):
            return f"{area}的{label}分析没有完成：{_friendly_error(summary['error'])}。"
        categories = summary.get("category_counts") or {}
        category_text = "、".join(f"{key} {_fmt_count(value)} 条" for key, value in list(categories.items())[:6]) or "暂无分类统计"
        return (
            f"{area}的{label}分析已完成，共涉及约 {_fmt_count(summary.get('matched_features', result.get('count', 0)))} 条要素。"
            f"分类统计：{category_text}。详细空间要素可在地图中查看；结果不代表法定边界。"
        )

    def _compose_spatial_relation_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "spatial_join") or {}
        metrics = result.get("metrics") or {}
        if result.get("error"):
            return f"空间关系分析没有完成：{_friendly_error(result['error'])}。"
        distance = result.get("distance_m", metrics.get("distance_m", "未知"))
        return (
            f"道路与水体的邻近分析已完成：约 {_fmt_count(result.get('count', 0))} 条关系满足 {_fmt_number(distance)} 米范围。"
            "结果基于演示图层，不代表法定道路、水体边界或规划结论。"
        )

    def _compose_spatial_operation_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "spatial_operation") or {}
        if result.get("error"):
            return f"空间几何处理没有完成：{_friendly_error(result['error'])}。"
        operation = result.get("operation")
        operation_label = {"clip": "裁剪", "intersect": "相交"}.get(str(operation), "空间处理")
        input_label = _spatial_source_label(result.get("input_ref"))
        mask_label = _spatial_source_label(result.get("mask_ref"))
        summary = result.get("summary") or {}
        truncated = bool(summary.get("truncated"))
        note = "结果达到要素上限，地图和导出内容可能不完整。" if truncated else "空间结果已准备好，可在地图中查看。"
        return (
            f"已完成{operation_label}：将{input_label}按{mask_label}处理，"
            f"得到约 {_fmt_count(result.get('count', 0))} 个空间要素。{note}"
        )

    def _compose_constrained_buildability_result(self, steps: Iterable[StepRun]) -> str:
        health = _first_result(steps, "get_dataset_health_report") or {}
        result = _first_result(steps, "get_zonal_constrained_buildability_analysis") or {}
        area = result.get("admin_name", "指定区域")
        statistics = result.get("statistics") or {}
        if statistics.get("error"):
            return f"{area}的联合建设候选筛选没有完成：{_friendly_error(statistics['error'])}。"
        constraints = result.get("constraint_summary") or {}
        ratio = statistics.get("candidate_ratio")
        ratio_text = "未知" if ratio is None else f"{float(ratio) * 100:.1f}%"
        health_note = _user_health_note(health)
        return (
            f"{area}的联合建设候选演示筛选已完成：约 {ratio_text} 的候选样本满足道路距离条件，"
            f"其中约 {_fmt_count(constraints.get('water_excluded_features', 0))} 个因水体被排除。"
            f"道路距离阈值为 {_fmt_number(constraints.get('road_distance_m'))} 米。"
            f"{health_note + ' ' if health_note else ''}结果仅用于演示，不代表全像元精确适宜性或法定规划结论。"
        )

    def _compose_raster_metadata_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_raster_metadata")
        if result is None:
            return _zh("栅格元数据查询已完成，但没有找到可展示的结果。")

        dataset = result.get("dataset", _zh("未知数据集"))
        file_count = int(result.get("file_count", 0))
        metadata = result.get("metadata", {})
        metrics = result.get("metrics", {})
        probed_files = metrics.get("probed_files", 0)
        crs_values = metadata.get("crs_values") or []
        dtype_values = metadata.get("dtypes") or []
        pixel_size = metadata.get("pixel_size")
        bounds = metadata.get("bounds")

        if metadata.get("error"):
            return _zh("{dataset} 的栅格信息没有读取成功：{error}。").format(
                dataset=dataset,
                error=_friendly_error(metadata["error"]),
            )
        size = f"{metadata.get('width', '未知')}x{metadata.get('height', '未知')}"
        details = [f"文件数：{_fmt_count(file_count)} 个", f"首个样本尺寸：{size}"]
        if probed_files:
            details.append(f"已抽查 {_fmt_count(probed_files)} 个文件")
        if metadata.get("band_count") is not None:
            details.append(f"包含 {_fmt_count(metadata.get('band_count'))} 个波段")
        return f"{dataset} 栅格元数据已读取。" + "，".join(details) + "。详细坐标系和范围可在结构化结果中查看。"

    def _compose_raster_statistics_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_raster_statistics")
        if result is None:
            return _zh("栅格统计分析已完成，但没有找到可展示的结果。")
        statistics = result.get("statistics", {})
        if statistics.get("error"):
            return _zh("{dataset} 的栅格统计没有完成：{error}。").format(
                dataset=result.get("dataset", _zh("未知数据集")),
                error=_friendly_error(statistics["error"]),
            )
        return (
            f"{result.get('dataset', '栅格')} 的统计分析已完成。"
            f"数值范围约为 {_fmt_number(statistics.get('minimum'))}–{_fmt_number(statistics.get('maximum'))}，"
            f"平均值约 {_fmt_number(statistics.get('mean'))}，覆盖{_approx_pixels(statistics.get('valid_pixel_count', 0))}有效像元。"
        )

    def _compose_zonal_raster_statistics_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_raster_statistics")
        if result is None:
            return _zh("区域栅格统计已完成，但没有找到可展示的结果。")
        health = _first_result(steps, "get_dataset_health_report") or {}
        statistics = result.get("statistics", {})
        admin_name = result.get("admin_name", _zh("指定区域"))
        if statistics.get("error"):
            return _zh("{area} 内没有可统计的 {dataset} 栅格像元：{error}。").format(
                area=admin_name,
                dataset=result.get("dataset", _zh("未知数据集")),
                error=_friendly_error(statistics["error"]),
            )
        health_note = _user_health_note(health)
        note = health_note + " " if health_note else ""
        if statistics.get("nodata_ratio") is not None:
            note += f"缺失值比例约 {_fmt_number(float(statistics['nodata_ratio']) * 100, 1)}%。"
        return (
            f"{admin_name}的 {result.get('dataset', '栅格')} 区域统计已完成。{note}"
            f"数值范围约为 {_fmt_number(statistics.get('minimum'))}–{_fmt_number(statistics.get('maximum'))}，"
            f"平均值约 {_fmt_number(statistics.get('mean'))}，覆盖{_approx_pixels(statistics.get('valid_pixel_count', 0))}有效像元。"
        )

    def _compose_default(self, steps: Iterable[StepRun]) -> str:
        completed = [step for step in steps if step.status == "COMPLETED"]
        counts = [
            _fmt_count(step.result["count"])
            for step in completed
            if step.result and "count" in step.result
        ]
        parts = [_zh("这次空间处理已完成。")]
        if counts:
            parts.append(_zh("共涉及约 {counts} 条记录。").format(counts=", ".join(counts)))
        return "".join(parts)


def _spatial_source_label(value: Any) -> str:
    labels = {
        "roads": "道路数据",
        "water": "水体数据",
        "admin_areas": "行政区范围",
    }
    text = str(value or "空间数据")
    if text in labels:
        return labels[text]
    if "://" in text:
        return "前一步空间结果"
    return text[:80]

def _fmt_count(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "未知"


def _approx_pixels(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "约未知"
    if abs(number) >= 10000:
        return f"约 {number / 10000:.1f} 万个"
    return f"约 {_fmt_count(number)} 个"


def _fmt_number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "未知"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _user_health_note(health: Dict[str, Any]) -> str:
    status = str(health.get("status") or "")
    if status == "degraded":
        return "部分数据可用，结论应谨慎解读。"
    if status == "unavailable":
        return "部分数据不可用，当前结果不能视为完整分析。"
    return ""


def _friendly_error(error: Any) -> str:
    text = str(error or "未知错误")
    replacements = {
        "in-memory backend has no raster geometry": "当前后端没有可用的栅格空间信息",
        "in-memory backend has no vector geometry": "当前后端没有可用的矢量几何",
        "in-memory backend has no DEM pixels": "当前后端没有可用的 DEM 像元",
        "rasterio is required for RasterMetadataBackend": "本地 GIS 环境缺少 rasterio 依赖",
    }
    for source, target in replacements.items():
        if source in text:
            return target
    return text[:240]


def _first_result(steps: Iterable[StepRun], tool: str) -> Optional[Dict[str, Any]]:
    for step in steps:
        if step.tool == tool and step.result:
            return step.result
    return None


def _join_names(names: Iterable[Any]) -> str:
    return _zh("、").join(str(name) for name in names)


def _zh(value: str) -> str:
    return value


def _analysis_ready_note(health: Dict[str, Any]) -> str:
    evidence = health.get("analysis_ready") or {}
    if not evidence:
        return ""
    status = str(evidence.get("status") or "")
    if status == "ready":
        return "联合分析所需的数据已完成对齐。"
    if status == "degraded":
        return "联合分析所需的数据只有部分可用。"
    return "联合分析所需的数据尚未完全准备好。"
