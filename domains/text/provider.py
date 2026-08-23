"""In-process text tool provider for the cross-domain Runtime replay."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from agent.errors import ToolError

from .catalog import TEXT_TOOL_DEFINITIONS


class TextToolProvider:
    provider_id = "text-native"

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        return deepcopy(TEXT_TOOL_DEFINITIONS)

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ready",
            "checks": [
                {"name": "definitions", "status": "passed"},
                {"name": "adapter", "status": "passed"},
            ],
        }

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in {"normalize_text", "summarize_text", "text_stats"}:
            raise ToolError("unknown text tool: " + str(name))
        text = " ".join(str(arguments["text"]).split())
        words = text.split() if text else []
        if name == "normalize_text":
            return {
                "normalized_text": text,
                "char_count": len(text),
                "word_count": len(words),
            }
        if name == "text_stats":
            return {
                "char_count": len(text),
                "word_count": len(words),
                "line_count": len(str(arguments["text"]).splitlines()) or 1,
            }
        summary = text if len(text) <= 180 else text[:177].rstrip() + "..."
        return {
            "summary": summary,
            "char_count": len(text),
            "word_count": len(words),
        }
