"""Declarative indicator workflow templates."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Mapping


KNOWN_TOOL_NAMES = ["list_indicators", "indicator_query"]
KNOWN_RESULT_TYPES = [
    "direct_answer",
    "indicator_catalog_result",
    "indicator_metrics_result",
    "indicator_timeseries_result",
    "indicator_comparison_result",
]

_COMMON_CONSTRAINTS = [
    {
        "name": "dataset",
        "label": "数据集",
        "type": "enum",
        "required": True,
        "choices": ["regional_indicators"],
    },
    {"name": "indicator", "label": "指标 ID", "type": "string", "required": True, "min_length": 1, "max_length": 96},
    {"name": "regions", "label": "区域列表", "type": "array", "required": True, "min_items": 1, "max_items": 16},
]


WORKFLOW_TEMPLATE_CATALOG: Dict[str, Dict] = {
    "indicator_discovery": {
        "id": "indicator_discovery",
        "version": "1.0.0",
        "label": "指标目录查询",
        "goal_template": "discover available regional indicators",
        "allowed_tools": ["list_indicators"],
        "result_types": ["indicator_catalog_result"],
        "max_steps": 1,
        "required_constraints": [],
        "constraint_specs": [],
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": [{"id": "list-indicators", "tool": "list_indicators", "args": {}, "depends_on": []}],
        "output_template": {"type": "indicator_catalog_result", "summary": True},
    },
    "indicator_latest": {
        "id": "indicator_latest",
        "version": "1.0.0",
        "label": "指标查询",
        "goal_template": "query the latest values for an indicator",
        "allowed_tools": ["indicator_query"],
        "result_types": ["indicator_metrics_result"],
        "max_steps": 1,
        "required_constraints": ["dataset", "indicator", "regions"],
        "constraint_specs": _COMMON_CONSTRAINTS,
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": [{
            "id": "query-indicator",
            "tool": "indicator_query",
            "args": {"dataset": {"$constraint": "dataset"}, "operation": "latest", "indicator": {"$constraint": "indicator"}, "regions": {"$constraint": "regions"}},
            "depends_on": [],
        }],
        "output_template": {"type": "indicator_metrics_result", "summary": True},
    },
    "indicator_trend": {
        "id": "indicator_trend",
        "version": "1.0.0",
        "label": "指标趋势分析",
        "goal_template": "analyze an indicator time series",
        "allowed_tools": ["indicator_query"],
        "result_types": ["indicator_timeseries_result"],
        "max_steps": 1,
        "required_constraints": ["dataset", "indicator", "regions"],
        "constraint_specs": _COMMON_CONSTRAINTS,
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": [{
            "id": "trend-indicator",
            "tool": "indicator_query",
            "args": {"dataset": {"$constraint": "dataset"}, "operation": "trend", "indicator": {"$constraint": "indicator"}, "regions": {"$constraint": "regions"}},
            "depends_on": [],
        }],
        "output_template": {"type": "indicator_timeseries_result", "summary": True},
    },
    "indicator_compare": {
        "id": "indicator_compare",
        "version": "1.0.0",
        "label": "区域指标比较",
        "goal_template": "compare an indicator across regions",
        "allowed_tools": ["indicator_query"],
        "result_types": ["indicator_comparison_result"],
        "max_steps": 1,
        "required_constraints": ["dataset", "indicator", "regions"],
        "constraint_specs": _COMMON_CONSTRAINTS,
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": [{
            "id": "compare-indicator",
            "tool": "indicator_query",
            "args": {"dataset": {"$constraint": "dataset"}, "operation": "compare", "indicator": {"$constraint": "indicator"}, "regions": {"$constraint": "regions"}},
            "depends_on": [],
        }],
        "output_template": {"type": "indicator_comparison_result", "summary": True},
    },
}


def workflow_template_catalog() -> Dict[str, Dict]:
    return deepcopy(WORKFLOW_TEMPLATE_CATALOG)
