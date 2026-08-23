"""Domain-owned text actions used to exercise the generic action seam."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domain_contract import DomainActionSpec

from .provider import TextToolProvider


TEXT_ACTION_SPECS = (
    DomainActionSpec(
        "text.normalize",
        "文本规范化动作",
        "规范化空白字符并返回文本计数证据。",
        {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "additionalProperties": False,
        },
        "text_normalize_result",
    ),
    DomainActionSpec(
        "text.summarize",
        "文本摘要动作",
        "对传入文本生成有界摘要和计数证据。",
        {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4000,
                },
            },
            "additionalProperties": False,
        },
        "text_summary_result",
    ),
    DomainActionSpec(
        "text.stats",
        "文本统计动作",
        "返回文本的字符、词和行数统计。",
        {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "additionalProperties": False,
        },
        "text_stats_result",
    ),
)


def execute_action(
    action_id: str,
    payload: Mapping[str, Any],
    *,
    service: Any = None,
) -> dict[str, Any]:
    """Run the declared action through the text provider adapter."""
    if action_id not in {"text.normalize", "text.summarize", "text.stats"}:
        raise ValueError("unknown text action: " + str(action_id))
    tool_name = {
        "text.normalize": "normalize_text",
        "text.summarize": "summarize_text",
        "text.stats": "text_stats",
    }[action_id]
    result = TextToolProvider().invoke(tool_name, {"text": payload["text"]})
    result["result_type"] = {
        "text.normalize": "text_normalize_result",
        "text.summarize": "text_summary_result",
        "text.stats": "text_stats_result",
    }[action_id]
    return result


__all__ = ["TEXT_ACTION_SPECS", "execute_action"]
