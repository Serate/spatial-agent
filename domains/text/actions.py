"""Domain-owned text actions used to exercise the generic action seam."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domain_contract import DomainActionSpec

from .provider import TextToolProvider


TEXT_ACTION_SPECS = (
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
)


def execute_action(
    action_id: str,
    payload: Mapping[str, Any],
    *,
    service: Any = None,
) -> dict[str, Any]:
    """Run the declared action through the text provider adapter."""
    if action_id != "text.summarize":
        raise ValueError("unknown text action: " + str(action_id))
    result = TextToolProvider().invoke("summarize_text", {"text": payload["text"]})
    result["result_type"] = "text_summary_result"
    return result


__all__ = ["TEXT_ACTION_SPECS", "execute_action"]
