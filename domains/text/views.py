"""Text-domain view models consumed by the generic Console renderer."""

from __future__ import annotations

from typing import Any, Dict, List


def build_views(
    result_type: str,
    *,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any = None,
    workspace: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a bounded summary view without adding text-specific UI code."""
    if result_type != "text_summary_result":
        return {"schema_version": "spatial-agent.views.v1", "panels": {}}

    for step in steps:
        if not isinstance(step, dict) or step.get("tool") != "summarize_text":
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        if not result:
            continue
        summary = str(result.get("summary") or "")[:240]
        return {
            "schema_version": "spatial-agent.views.v1",
            "panels": {
                "generic": {
                    "kind": "text_summary",
                    "source_step_id": step.get("id"),
                    "source_tool": step.get("tool"),
                    "title": "文本摘要",
                    "metrics": [
                        {"label": "字符数", "value": result.get("char_count", 0)},
                        {"label": "词数", "value": result.get("word_count", 0)},
                    ],
                    "rows": [{"label": "摘要", "value": summary or "无摘要内容"}],
                }
            },
        }

    return {"schema_version": "spatial-agent.views.v1", "panels": {}}


__all__ = ["build_views"]
