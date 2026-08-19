"""User-facing answer composition for the text Domain Pack."""

from __future__ import annotations

from typing import Iterable

from agent.models import AgentRunResult, StepRun


class TextAnswerComposer:
    def compose(self, result: AgentRunResult) -> str:
        step = next(
            (item for item in result.steps if item.tool == "summarize_text" and item.result),
            None,
        )
        if step is None:
            return "文本摘要已完成，但没有返回摘要内容。"
        output = step.result or {}
        return (
            f"文本摘要：{output.get('summary', '')}"
            f"（字符数 {output.get('char_count', 0)}，词数 {output.get('word_count', 0)}）。"
        )

    def compose_failure(self, result: AgentRunResult) -> str:
        return "文本摘要未完成：" + str(result.error or "未知执行错误")
