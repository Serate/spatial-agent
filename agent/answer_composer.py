from typing import Any, Dict, Iterable, Optional

from .models import AgentRunResult, StepRun


class AnswerComposer:
    """Turns completed tool traces into a user-facing answer."""

    def compose(self, result: AgentRunResult) -> str:
        output_type = result.plan.output.get("type") if result.plan else None
        if output_type == "admin_area_result":
            return self._compose_admin_area_result(result.steps)
        if output_type == "raster_metadata_result":
            return self._compose_raster_metadata_result(result.steps)
        return self._compose_default(result.steps)

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
