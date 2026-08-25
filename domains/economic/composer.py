"""Concise user-facing composition for Economic Domain results."""

from __future__ import annotations

from agent.models import AgentRunResult


class EconomicAnswerComposer:
    def compose(self, result: AgentRunResult) -> str:
        values = [step.result for step in result.steps if isinstance(step.result, dict)]
        value = next((item for item in values if item.get("result_type") or item.get("indicators") or item.get("sources")), {})
        if not value:
            return "经济分析已完成，但没有返回可展示的数据。"
        status = str(value.get("status") or "ready")
        if status != "ready":
            return self._unavailable(value)
        if value.get("indicators") is not None:
            count = len(value.get("indicators") or [])
            return f"当前来源提供 {count} 项可用经济指标。请指定指标和区域后，我再分析最新值或变化趋势。"
        rows = value.get("rows") or []
        metrics = value.get("metrics") or {}
        operation = str(value.get("operation") or "")
        indicator = str(value.get("indicator") or "经济指标")
        if operation == "trend":
            changes = metrics.get("changes") or {}
            change = next(iter(changes.values()), None)
            suffix = f"，期间变化 {self._number(change)}" if change is not None else ""
            return f"{indicator}趋势分析完成，共 {len(rows)} 条观测{suffix}。最新期间和来源请查看下方结果。"
        if operation == "compare":
            return f"已完成 {indicator} 的区域比较，覆盖 {metrics.get('region_count', 0)} 个区域。结果保留了对应统计期间和来源证据。"
        return f"{indicator}查询完成，返回 {len(rows)} 条最新观测。结果中的期间、单位和官方来源可展开查看。"

    def compose_failure(self, result: AgentRunResult) -> str:
        return "经济分析未完成：" + str(result.error or "数据不可用，请补充指标、区域或数据源。")

    @staticmethod
    def _unavailable(value: dict) -> str:
        code = str(value.get("code") or "economic_data_unavailable")
        messages = {
            "economic_data_unavailable": "当前没有可用的经济数据源。",
            "economic_field_mismatch": "经济数据字段或来源证据不完整，暂不能安全分析。",
            "economic_indicator_unavailable": "当前数据源没有找到该经济指标。",
            "economic_region_unavailable": "当前数据源没有找到请求的统计区域。",
            "economic_time_range_unavailable": "当前数据源没有覆盖请求的期间或期间类型。",
            "economic_data_not_found": "没有找到同时满足指标、区域和期间条件的观测。",
            "economic_source_evidence_unavailable": "没有找到该请求对应的来源证据。",
        }
        return messages.get(code, "经济数据当前不可用，请检查指标、区域和数据期间。")

    @staticmethod
    def _number(value):
        if value is None:
            return "—"
        return f"{float(value):,.4g}"
