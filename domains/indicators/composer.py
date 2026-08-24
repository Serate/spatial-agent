"""User-facing indicator answer composition."""

from __future__ import annotations

from agent.models import AgentRunResult


class IndicatorsAnswerComposer:
    def compose(self, result: AgentRunResult) -> str:
        step = next((item for item in result.steps if item.result), None)
        value = step.result if step else {}
        if not value:
            return "指标分析已完成，但没有返回可展示的数据。"
        if value.get("indicators") is not None:
            count = len(value.get("indicators") or [])
            return f"已找到 {count} 个可用指标。具体指标、区域范围和来源请查看结构化结果。"
        rows = value.get("rows") or []
        metrics = value.get("metrics") or {}
        operation = value.get("operation")
        label = {"latest": "最新值", "trend": "趋势", "compare": "区域比较"}.get(operation, "指标分析")
        return (
            f"{label}已完成，共整理 {len(rows)} 条记录；"
            f"数值范围约为 {metrics.get('minimum')}–{metrics.get('maximum')}。"
            "详细期间、区域和来源见结构化结果。"
        )

    def compose_failure(self, result: AgentRunResult) -> str:
        return "指标分析未完成：" + str(result.error or "数据不可用，请补充指标、区域或数据源。")
