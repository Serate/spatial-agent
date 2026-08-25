"""Indicator views consumed by the domain-neutral Console renderer."""

from __future__ import annotations

from typing import Any, Dict, List

from agent.analysis.record_views import build_record_analysis_view


def build_views(
    result_type: str,
    *,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any = None,
    workspace: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del geometry_evidence, geojson_ref, workspace
    result = next(
        (step.get("result") for step in steps if isinstance(step, dict) and isinstance(step.get("result"), dict)),
        {},
    )
    if result_type == "record_analysis_result":
        return {"schema_version": "spatial-agent.views.v1", "panels": {"generic": build_record_analysis_view(result)}}
    if result_type == "indicator_catalog_result":
        indicators = result.get("indicators") or []
        rows = [[item.get("id"), item.get("label"), ", ".join(item.get("units") or [])] for item in indicators[:32]]
        return {"schema_version": "spatial-agent.views.v1", "panels": {"generic": {
            "kind": "indicator_catalog", "title": "可用指标", "table": {"columns": ["指标 ID", "名称", "单位"], "rows": rows},
        }}}
    if result_type not in {"indicator_metrics_result", "indicator_timeseries_result", "indicator_comparison_result"}:
        return {"schema_version": "spatial-agent.views.v1", "panels": {}}
    rows = result.get("rows") or []
    values = [float(item.get("value")) for item in rows if isinstance(item, dict) and isinstance(item.get("value"), (int, float))]
    metrics = result.get("metrics") or {}
    metric_cards = [
        {"label": "记录数", "value": metrics.get("record_count", len(rows))},
        {"label": "最小值", "value": metrics.get("minimum")},
        {"label": "最大值", "value": metrics.get("maximum")},
        {"label": "平均值", "value": metrics.get("mean")},
    ]
    table_rows = [[item.get("region"), item.get("period"), item.get("value"), item.get("unit")] for item in rows[:40] if isinstance(item, dict)]
    panel = {
        "kind": "comparison_chart" if result_type in {"indicator_timeseries_result", "indicator_comparison_result"} else "indicator_metrics",
        "title": str(result.get("indicator") or "指标结果"),
        "metrics": metric_cards,
        "table": {"columns": ["区域", "期间", "数值", "单位"], "rows": table_rows},
        "note": "数据来源：" + str((result.get("provenance") or {}).get("source") or "未提供")[:160],
    }
    if panel["kind"] == "comparison_chart":
        panel["comparison_kind"] = "区域/期间比较"
        panel["encodings"] = {"y": {"label": str((rows[0] if rows else {}).get("unit") or "值")}}
        panel["series"] = [{"id": "indicator", "points": [
            {"x": item.get("period"), "y": item.get("value"), "label": str(item.get("region") or "") + " · " + str(item.get("period") or "")}
            for item in rows[:40] if isinstance(item, dict)
        ]}]
    return {"schema_version": "spatial-agent.views.v1", "panels": {"generic": panel}}
