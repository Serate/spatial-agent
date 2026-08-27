"""Declarative Economic Domain workflows."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict

from .catalog import ECONOMIC_DATASET


KNOWN_TOOL_NAMES = [
    "economic_list_indicators",
    "economic_indicator_query",
    "economic_source_evidence",
]
KNOWN_RESULT_TYPES = [
    "direct_answer",
    "economic_catalog_result",
    "economic_metrics_result",
    "economic_timeseries_result",
    "economic_comparison_result",
    "economic_evidence_result",
]

_COMMON_CONSTRAINTS = [
    {"name": "dataset", "label": "数据集", "type": "enum", "required": True, "choices": [ECONOMIC_DATASET]},
    {"name": "indicator", "label": "指标 ID", "type": "string", "required": True, "min_length": 1, "max_length": 96},
    {"name": "regions", "label": "区域列表", "type": "array", "required": True, "min_items": 1, "max_items": 16},
    {"name": "period_type", "label": "期间类型", "type": "enum", "required": False, "default": "annual", "choices": ["annual", "quarter", "half_year", "month", "month_ytd"]},
    {"name": "geography_level", "label": "区域层级", "type": "string", "required": False, "min_length": 1, "max_length": 32},
    {"name": "period_start", "label": "起始期间", "type": "string", "required": False, "max_length": 32},
    {"name": "period_end", "label": "结束期间", "type": "string", "required": False, "max_length": 32},
]


def _query_steps(operation: str) -> list[dict]:
    return [
        {
            "id": "query-economic-indicator",
            "tool": "economic_indicator_query",
            "args": {
                "dataset": {"$constraint": "dataset"},
                "operation": operation,
                "indicator": {"$constraint": "indicator"},
                "regions": {"$constraint": "regions"},
                "period_type": {"$constraint": "period_type"},
            },
            "depends_on": [],
        },
        {
            "id": "collect-economic-evidence",
            "tool": "economic_source_evidence",
            "args": {
                "dataset": {"$constraint": "dataset"},
                "indicator": {"$constraint": "indicator"},
                "regions": {"$constraint": "regions"},
                "period_type": {"$constraint": "period_type"},
            },
            "depends_on": ["query-economic-indicator"],
        },
    ]


WORKFLOW_TEMPLATE_CATALOG: Dict[str, Dict] = {
    "economic_discovery": {
        "id": "economic_discovery",
        "version": "1.0.0",
        "label": "经济指标目录查询",
        "goal_template": "discover available economic indicators",
        "allowed_tools": ["economic_list_indicators"],
        "result_types": ["economic_catalog_result"],
        "max_steps": 1,
        "required_constraints": [],
        "constraint_specs": [],
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": [{"id": "list-economic-indicators", "tool": "economic_list_indicators", "args": {}, "depends_on": []}],
        "output_template": {"type": "economic_catalog_result", "summary": True},
    },
    "economic_latest": {
        "id": "economic_latest",
        "version": "1.0.0",
        "label": "经济指标查询",
        "goal_template": "query the latest economic indicator values",
        "allowed_tools": ["economic_indicator_query", "economic_source_evidence"],
        "result_types": ["economic_metrics_result", "economic_evidence_result"],
        "max_steps": 2,
        "required_constraints": ["dataset", "indicator", "regions"],
        "constraint_specs": _COMMON_CONSTRAINTS,
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": _query_steps("latest"),
        "output_template": {"type": "economic_metrics_result", "summary": True},
    },
    "economic_trend": {
        "id": "economic_trend",
        "version": "1.0.0",
        "label": "经济指标趋势分析",
        "goal_template": "analyze an economic indicator time series",
        "allowed_tools": ["economic_indicator_query", "economic_source_evidence"],
        "result_types": ["economic_timeseries_result", "economic_evidence_result"],
        "max_steps": 2,
        "required_constraints": ["dataset", "indicator", "regions"],
        "constraint_specs": _COMMON_CONSTRAINTS,
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": _query_steps("trend"),
        "output_template": {"type": "economic_timeseries_result", "summary": True},
    },
    "economic_compare": {
        "id": "economic_compare",
        "version": "1.0.0",
        "label": "经济指标区域比较",
        "goal_template": "compare an economic indicator across regions",
        "allowed_tools": ["economic_indicator_query", "economic_source_evidence"],
        "result_types": ["economic_comparison_result", "economic_evidence_result"],
        "max_steps": 2,
        "required_constraints": ["dataset", "indicator", "regions"],
        "constraint_specs": _COMMON_CONSTRAINTS,
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": _query_steps("compare"),
        "output_template": {"type": "economic_comparison_result", "summary": True},
    },
    "economic_evidence": {
        "id": "economic_evidence",
        "version": "1.0.0",
        "label": "经济数据来源证据",
        "goal_template": "inspect the source evidence for an economic indicator",
        "allowed_tools": ["economic_source_evidence"],
        "result_types": ["economic_evidence_result"],
        "max_steps": 1,
        "required_constraints": ["dataset", "indicator", "regions"],
        "constraint_specs": _COMMON_CONSTRAINTS,
        "evidence_options": ["summary", "provenance", "trace"],
        "default_evidence": ["summary", "provenance", "trace"],
        "step_blueprint": [{
            "id": "inspect-economic-evidence",
            "tool": "economic_source_evidence",
            "args": {"dataset": {"$constraint": "dataset"}, "indicator": {"$constraint": "indicator"}, "regions": {"$constraint": "regions"}, "period_type": {"$constraint": "period_type"}},
            "depends_on": [],
        }],
        "output_template": {"type": "economic_evidence_result", "summary": True},
    },
}


def workflow_template_catalog() -> Dict[str, Dict]:
    return deepcopy(WORKFLOW_TEMPLATE_CATALOG)
