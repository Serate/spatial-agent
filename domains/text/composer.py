"""User-facing answer composition for the text Domain Pack."""

from __future__ import annotations

from agent.models import AgentRunResult


class TextAnswerComposer:
    def compose(self, result: AgentRunResult) -> str:
        output_type = str((result.plan.output if result.plan else {}).get("type") or "")
        summary = next(
            (item.result for item in result.steps if item.tool == "summarize_text" and item.result),
            None,
        )
        stats = next(
            (item.result for item in result.steps if item.tool == "text_stats" and item.result),
            None,
        )
        normalized = next(
            (item.result for item in result.steps if item.tool == "normalize_text" and item.result),
            None,
        )
        if output_type == "text_analysis_result":
            parts = ["组合文本分析已完成。"]
            if normalized:
                parts.append(
                    f"规范化文本 {normalized.get('char_count', 0)} 个字符、"
                    f"{normalized.get('word_count', 0)} 个词。"
                )
            if summary:
                parts.append(f"摘要：{summary.get('summary', '')}。")
            if stats:
                parts.append(
                    f"统计：{stats.get('char_count', 0)} 个字符、"
                    f"{stats.get('word_count', 0)} 个词、"
                    f"{stats.get('line_count', 0)} 行。"
                )
            return "".join(parts)
        if summary:
            return (
                f"文本摘要：{summary.get('summary', '')}"
                f"（字符数 {summary.get('char_count', 0)}，词数 {summary.get('word_count', 0)}）。"
            )
        if stats:
            return (
                f"文本统计：字符数 {stats.get('char_count', 0)}，"
                f"词数 {stats.get('word_count', 0)}，行数 {stats.get('line_count', 0)}。"
            )
        if normalized:
            return (
                f"文本规范化已完成：字符数 {normalized.get('char_count', 0)}，"
                f"词数 {normalized.get('word_count', 0)}。"
            )
        return "文本处理已完成，但没有返回可展示的内容。"

    def compose_failure(self, result: AgentRunResult) -> str:
        return "文本摘要未完成：" + str(result.error or "未知执行错误")
