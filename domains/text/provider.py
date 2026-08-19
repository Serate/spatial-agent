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
        if name != "summarize_text":
            raise ToolError("unknown text tool: " + str(name))
        text = " ".join(str(arguments["text"]).split())
        words = text.split() if text else []
        summary = text if len(text) <= 180 else text[:177].rstrip() + "..."
        return {
            "summary": summary,
            "char_count": len(text),
            "word_count": len(words),
        }
