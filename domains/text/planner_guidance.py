"""Text-owned policy supplied to the generic LLM Planner."""

from __future__ import annotations

from typing import Any


TEXT_PLANNER_GUIDANCE: dict[str, Any] = {
    "domain_id": "text",
    "domain_description": "对用户提供的文本执行有界摘要，并返回可审计的文本结果。",
    "tool_semantics": {
        "summarize_text": "对输入文本生成确定性、有界摘要；参数 text 必须是非空字符串。",
    },
    "result_types": {
        "text_summary_result": "文本摘要、字符数和词数。",
    },
    "planning_rules": [
        "For a text summary request, use summarize_text with the supplied text and output type \"text_summary_result\".",
        "Keep the request text within the registered tool limit and do not invent source content.",
    ],
    "clarification_policy": [
        "Ask for the text or a clear text operation when the request does not provide one.",
    ],
    "rejection_policy": [
        "Reject destructive, unauthorized, oversized, or code-execution requests.",
    ],
}
