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
    if result_type not in {
        "text_normalize_result",
        "text_summary_result",
        "text_stats_result",
        "text_analysis_result",
    }:
        return {"schema_version": "spatial-agent.views.v1", "panels": {}}

    rows = []
    title = {
        "text_normalize_result": "文本规范化",
        "text_summary_result": "文本摘要",
        "text_stats_result": "文本统计",
        "text_analysis_result": "组合文本分析",
    }.get(result_type, "文本结果")
    for step in steps:
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        if not result:
            continue
        if step.get("tool") == "summarize_text":
            rows.append({"label": "摘要", "value": str(result.get("summary") or "无摘要内容")[:240]})
        elif step.get("tool") == "normalize_text":
            rows.append({"label": "规范化文本", "value": str(result.get("normalized_text") or "")[:240]})
        elif step.get("tool") == "text_stats":
            rows.append({"label": "行数", "value": result.get("line_count", 0)})
        if result.get("char_count") is not None:
            rows.append({"label": "字符数", "value": result.get("char_count", 0)})
        if result.get("word_count") is not None:
            rows.append({"label": "词数", "value": result.get("word_count", 0)})

    if rows:
        return {
            "schema_version": "spatial-agent.views.v1",
            "panels": {
                "generic": {
                    "kind": "text_analysis" if result_type == "text_analysis_result" else result_type.replace("_result", ""),
                    "title": title,
                    "rows": rows[:16],
                }
            },
        }

    return {"schema_version": "spatial-agent.views.v1", "panels": {}}


__all__ = ["build_views"]
