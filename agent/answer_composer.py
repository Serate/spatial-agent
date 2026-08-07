from typing import Any, Dict, Iterable, Optional

from .models import AgentRunResult, StepRun


class AnswerComposer:
    """Turns completed tool traces into a user-facing answer."""

    def compose(self, result: AgentRunResult) -> str:
        output_type = result.plan.output.get("type") if result.plan else None
        has_elevation = _first_result(result.steps, "get_zonal_raster_statistics") is not None
        has_slope = _first_result(result.steps, "get_zonal_slope_statistics") is not None
        has_land_use = _first_result(result.steps, "get_zonal_land_use_distribution") is not None
        has_buildability = _first_result(result.steps, "get_zonal_buildability_analysis") is not None
        if has_elevation and (has_slope or has_land_use or has_buildability):
            return self._compose_terrain_land_use_result(result.steps)
        if output_type == "admin_area_result":
            return self._compose_admin_area_result(result.steps)
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

    def _compose_slope_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_slope_statistics")
        statistics = (result or {}).get("statistics", {})
        area = (result or {}).get("admin_name", "指定区域")
        if statistics.get("error"):
            return f"{area}内坡度分析失败：{statistics['error']}。"
        return (
            f"{area}坡度分析：最小值 {statistics.get('minimum', '未知')} 度，"
            f"最大值 {statistics.get('maximum', '未知')} 度，平均值 "
            f"{statistics.get('mean', '未知')} 度，有效像元 {statistics.get('valid_pixel_count', 0)} 个。"
        )

    def _compose_land_use_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_land_use_distribution")
        statistics = (result or {}).get("statistics", {})
        area = (result or {}).get("admin_name", "指定区域")
        if statistics.get("error"):
            return f"{area}内土地利用分析失败：{statistics['error']}。"
        categories = statistics.get("categories", [])[:5]
        category_text = "、".join(
            f"{item.get('value')}类 {float(item.get('share', 0)) * 100:.2f}%"
            for item in categories
        ) or "暂无"
        return (
            f"{area}土地利用分布：共 {statistics.get('category_count', 0)} 个栅格类别，"
            f"有效像元 {statistics.get('valid_pixel_count', 0)} 个，主要类别为 {category_text}。"
        )

    def _compose_buildability_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_buildability_analysis")
        statistics = (result or {}).get("statistics", {})
        area = (result or {}).get("admin_name", "指定区域")
        if statistics.get("error"):
            return f"{area}建设候选筛选失败：{statistics['error']}。"
        ratio = statistics.get("candidate_ratio")
        ratio_text = "未知" if ratio is None else f"{float(ratio) * 100:.2f}%"
        reference = (result or {}).get("result_ref")
        suffix = f"结果引用：{reference}。" if reference else ""
        return (
            f"{area}建设候选演示筛选：候选像元 {statistics.get('candidate_pixel_count', 0)} 个，"
            f"有效像元 {statistics.get('valid_pixel_count', 0)} 个，候选比例 {ratio_text}，"
            f"坡度阈值 {statistics.get('slope_limit_degrees', '未知')} 度。"
            f"{suffix}以上结果仅用于演示，不代表法定建设适宜性或规划许可结论。"
        )

    def _compose_terrain_land_use_result(self, steps: Iterable[StepRun]) -> str:
        elevation = _first_result(steps, "get_zonal_raster_statistics")
        slope = _first_result(steps, "get_zonal_slope_statistics")
        land_use = _first_result(steps, "get_zonal_land_use_distribution")
        buildability = _first_result(steps, "get_zonal_buildability_analysis")
        area = (elevation or slope or land_use or {}).get("admin_name", "指定区域")
        parts = [f"{area}综合空间分析已完成。"]
        errors = [
            item.get("statistics", {}).get("error", "")
            for item in (elevation, slope, land_use, buildability)
            if item
        ]
        if any("in-memory backend" in error for error in errors):
            parts.insert(0, "当前使用内存演示后端，未读取真实 GIS 栅格像元；请切换到本地 GIS 后端。")
        if elevation:
            stats = elevation.get("statistics", {})
            if stats.get("error"):
                parts.append(f"高程：{stats['error']}。")
            else:
                parts.append(f"高程范围 {stats.get('minimum', '未知')}–{stats.get('maximum', '未知')} 米，平均 {stats.get('mean', '未知')} 米，有效像元 {stats.get('valid_pixel_count', 0)} 个。")
        if slope:
            stats = slope.get("statistics", {})
            if stats.get("error"):
                parts.append(f"坡度：{stats['error']}。")
            else:
                parts.append(f"由 DEM 动态计算的坡度范围 {stats.get('minimum', '未知')}–{stats.get('maximum', '未知')} 度，平均 {stats.get('mean', '未知')} 度。")
        if land_use:
            stats = land_use.get("statistics", {})
            if stats.get("error"):
                parts.append(f"土地利用：{stats['error']}。")
            else:
                categories = stats.get("categories", [])[:5]
                category_text = "、".join(f"{item['value']}类 {round(float(item['share']) * 100, 2)}%" for item in categories)
                parts.append(f"土地利用共识别 {stats.get('category_count', 0)} 个栅格类别，主要类别为 {category_text or '暂无'}。")
        if buildability:
            stats = buildability.get("statistics", {})
            if stats.get("error"):
                parts.append(f"建设候选筛选：{stats['error']}。")
            else:
                ratio = float(stats.get("candidate_ratio", 0)) * 100
                parts.append(f"按演示规则筛选出约 {ratio:.2f}% 的候选像元（{stats.get('candidate_pixel_count', 0)} / {stats.get('valid_pixel_count', 0)}），坡度阈值为 {stats.get('slope_limit_degrees', 15)} 度。")
        parts.append("当前结果提供地形与土地利用事实统计；“适合建设”还需要明确坡度阈值、禁建地类和权重后才能生成可审计的候选区域。")
        if buildability:
            parts[-1] = "以上建设候选仅是演示筛选，不代表法定建设适宜性或规划许可结论。"
        return "".join(parts)

    def _compose_admin_area_result(self, steps: Iterable[StepRun]) -> str:
        schema = _first_result(steps, "get_dataset_schema")
        range_result = _first_result(steps, "range_query")
        if range_result is None:
            return _zh("行政区查询已完成，但没有找到可展示的查询结果。")

        count = int(range_result.get("count", 0))
        names = range_result.get("sample_names") or []
        crs = range_result.get("crs") or (schema or {}).get("crs") or _zh("未知")
        result_ref = range_result.get("result_ref", _zh("无"))
        metrics = range_result.get("metrics", {})
        source = metrics.get("source")

        if count == 0:
            answer = _zh("未找到匹配的行政区边界。")
        else:
            name_text = _join_names(names) if names else _zh("未返回名称样例")
            answer = _zh("已找到 {count} 个匹配行政区：{names}。").format(
                count=count,
                names=name_text,
            )

        details = [
            _zh("坐标系：{crs}").format(crs=crs),
            _zh("结果引用：{result_ref}").format(result_ref=result_ref),
        ]
        if source:
            details.append(_zh("数据源：{source}").format(source=source))
        return answer + _zh(" ") + _zh("；").join(details) + _zh("。")

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
            return _zh("{dataset} 栅格元数据查询完成，但未匹配到本地文件：{error}。").format(
                dataset=dataset,
                error=metadata["error"],
            )

        details = [
            _zh("文件数：{count}").format(count=file_count),
            _zh("已抽样：{count} 个文件").format(count=probed_files),
            _zh("首个样本尺寸：{width}x{height}").format(
                width=metadata.get("width", _zh("未知")),
                height=metadata.get("height", _zh("未知")),
            ),
            _zh("波段数：{count}").format(count=metadata.get("band_count", _zh("未知"))),
        ]
        if dtype_values:
            details.append(_zh("数据类型：{values}").format(values=", ".join(dtype_values)))
        if crs_values:
            details.append(_zh("坐标系：{values}").format(values=", ".join(crs_values)))
        if pixel_size:
            details.append(_zh("像元大小：{values}").format(values=", ".join(str(item) for item in pixel_size)))
        if bounds:
            details.append(_zh("范围：{values}").format(values=", ".join(str(round(float(item), 3)) for item in bounds)))
        return _zh("{dataset} 栅格元数据：").format(dataset=dataset) + _zh("；").join(details) + _zh("。")

    def _compose_raster_statistics_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_raster_statistics")
        if result is None:
            return _zh("栅格统计分析已完成，但没有找到可展示的结果。")
        statistics = result.get("statistics", {})
        if statistics.get("error"):
            return _zh("{dataset} 栅格统计分析未匹配到本地文件：{error}。").format(
                dataset=result.get("dataset", _zh("未知数据集")),
                error=statistics["error"],
            )
        metrics = result.get("metrics", {})
        details = [
            _zh("文件总数：{count}").format(count=result.get("file_count", 0)),
            _zh("已分析：{count} 个文件").format(count=metrics.get("analyzed_files", 0)),
            _zh("最小值：{value}").format(value=statistics.get("minimum", _zh("未知"))),
            _zh("最大值：{value}").format(value=statistics.get("maximum", _zh("未知"))),
            _zh("平均值：{value}").format(value=statistics.get("mean", _zh("未知"))),
            _zh("标准差：{value}").format(value=statistics.get("standard_deviation", _zh("未知"))),
            _zh("有效像元：{count}").format(count=statistics.get("valid_pixel_count", 0)),
        ]
        nodata_ratio = statistics.get("nodata_ratio")
        if nodata_ratio is not None:
            details.append(_zh("NoData 比例：{ratio}%").format(ratio=round(float(nodata_ratio) * 100, 3)))
        return _zh("{dataset} 栅格统计：").format(dataset=result.get("dataset", _zh("未知数据集"))) + _zh("；").join(details) + _zh("。")

    def _compose_zonal_raster_statistics_result(self, steps: Iterable[StepRun]) -> str:
        result = _first_result(steps, "get_zonal_raster_statistics")
        if result is None:
            return _zh("区域栅格统计已完成，但没有找到可展示的结果。")
        statistics = result.get("statistics", {})
        admin_name = result.get("admin_name", _zh("指定区域"))
        if statistics.get("error"):
            return _zh("{area} 内没有可统计的 {dataset} 栅格像元：{error}。").format(
                area=admin_name,
                dataset=result.get("dataset", _zh("未知数据集")),
                error=statistics["error"],
            )
        details = [
            _zh("最小值：{value}").format(value=statistics.get("minimum", _zh("未知"))),
            _zh("最大值：{value}").format(value=statistics.get("maximum", _zh("未知"))),
            _zh("平均值：{value}").format(value=statistics.get("mean", _zh("未知"))),
            _zh("标准差：{value}").format(
                value=statistics.get("standard_deviation", _zh("未知"))
            ),
            _zh("有效像元：{count}").format(
                count=statistics.get("valid_pixel_count", 0)
            ),
        ]
        if statistics.get("nodata_ratio") is not None:
            details.append(
                _zh("NoData 比例：{ratio}%").format(
                    ratio=round(float(statistics["nodata_ratio"]) * 100, 3)
                )
            )
        return _zh("{area}的 {dataset} 区域统计：").format(
            area=admin_name, dataset=result.get("dataset", _zh("未知数据集"))
        ) + _zh("；").join(details) + _zh("。")

    def _compose_default(self, steps: Iterable[StepRun]) -> str:
        completed = [step for step in steps if step.status == "COMPLETED"]
        refs = [
            str(step.result["result_ref"])
            for step in completed
            if step.result and "result_ref" in step.result
        ]
        counts = [
            str(step.result["count"])
            for step in completed
            if step.result and "count" in step.result
        ]
        parts = [_zh("已完成 {count} 个工具步骤").format(count=len(completed))]
        if refs:
            parts.append(_zh("结果引用：{refs}").format(refs=", ".join(refs)))
        if counts:
            parts.append(_zh("命中数量：{counts}").format(counts=", ".join(counts)))
        return _zh("；").join(parts) + _zh("。")


def _first_result(steps: Iterable[StepRun], tool: str) -> Optional[Dict[str, Any]]:
    for step in steps:
        if step.tool == tool and step.result:
            return step.result
    return None


def _join_names(names: Iterable[Any]) -> str:
    return _zh("、").join(str(name) for name in names)


def _zh(value: str) -> str:
    return value
