from typing import Any, Dict, Iterable, Optional

from .models import AgentRunResult, StepRun


class AnswerComposer:
    """Turns completed tool traces into a user-facing answer."""

    def compose(self, result: AgentRunResult) -> str:
        output_type = result.plan.output.get("type") if result.plan else None
        if output_type == "admin_area_result":
            return self._compose_admin_area_result(result.steps)
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
