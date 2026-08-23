"""Text-owned declarative workflow catalog.

The generic workflow compiler owns validation and DAG composition.  This
module only declares text capabilities, tools, constraints and result types.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional


KNOWN_TOOL_NAMES = ["normalize_text", "summarize_text", "text_stats"]
KNOWN_RESULT_TYPES = [
    "direct_answer",
    "text_normalize_result",
    "text_summary_result",
    "text_stats_result",
    "text_analysis_result",
]


WORKFLOW_TEMPLATE_CATALOG: Dict[str, Dict[str, Any]] = {
    "text_normalize": {
        "id": "text_normalize",
        "version": "1.0.0",
        "label": "文本规范化",
        "goal_template": "normalize supplied text before downstream analysis",
        "allowed_tools": ["normalize_text"],
        "result_types": ["text_normalize_result"],
        "max_steps": 1,
        "required_constraints": ["text"],
        "constraint_specs": [
            {
                "name": "text",
                "label": "文本内容",
                "type": "string",
                "required": True,
                "min_length": 1,
                "max_length": 4000,
            }
        ],
        "evidence_options": ["summary", "trace"],
        "default_evidence": ["summary", "trace"],
        "step_blueprint": [
            {
                "id": "normalize-text",
                "tool": "normalize_text",
                "args": {"text": {"$constraint": "text"}},
                "depends_on": [],
            }
        ],
        "output_template": {"type": "text_normalize_result", "summary": True},
    },
    "text_summary": {
        "id": "text_summary",
        "version": "1.0.0",
        "label": "文本摘要",
        "goal_template": "summarize supplied text",
        "allowed_tools": ["summarize_text"],
        "result_types": ["text_summary_result"],
        "max_steps": 1,
        "required_constraints": ["text"],
        "constraint_specs": [
            {
                "name": "text",
                "label": "文本内容",
                "type": "string",
                "required": True,
                "min_length": 1,
                "max_length": 4000,
            }
        ],
        "evidence_options": ["summary", "trace"],
        "default_evidence": ["summary", "trace"],
        "step_blueprint": [
            {
                "id": "summary-text",
                "tool": "summarize_text",
                "args": {"text": {"$constraint": "text"}},
                "depends_on": [],
            }
        ],
        "output_template": {"type": "text_summary_result", "summary": True},
    },
    "text_stats": {
        "id": "text_stats",
        "version": "1.0.0",
        "label": "文本统计",
        "goal_template": "calculate bounded text statistics",
        "allowed_tools": ["text_stats"],
        "result_types": ["text_stats_result"],
        "max_steps": 1,
        "required_constraints": ["text"],
        "constraint_specs": [
            {
                "name": "text",
                "label": "文本内容",
                "type": "string",
                "required": True,
                "min_length": 1,
                "max_length": 4000,
            }
        ],
        "evidence_options": ["summary", "trace"],
        "default_evidence": ["summary", "trace"],
        "step_blueprint": [
            {
                "id": "text-stats",
                "tool": "text_stats",
                "args": {"text": {"$constraint": "text"}},
                "depends_on": [],
            }
        ],
        "output_template": {"type": "text_stats_result", "summary": True},
    },
}


def workflow_template_catalog(
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return an isolated copy of the Text-owned catalog."""

    source = WORKFLOW_TEMPLATE_CATALOG if catalog is None else catalog
    if not isinstance(source, Mapping):
        raise TypeError("catalog must be an object")
    return deepcopy(dict(source))


__all__ = [
    "KNOWN_RESULT_TYPES",
    "KNOWN_TOOL_NAMES",
    "WORKFLOW_TEMPLATE_CATALOG",
    "workflow_template_catalog",
]
