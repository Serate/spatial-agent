"""Workflow template catalog + compiler (compatibility facade).

The implementation lives in ``agent.templates.common``, ``agent.templates.catalog``
and ``agent.templates.compiler``.  This module keeps the historical import path
stable while new callers may import from the ``agent.templates`` package.
"""

from agent.templates.common import (  # noqa: F401
    WorkflowTemplateError,
    DEFAULT_TEMPLATE_VERSION,
    WORKFLOW_COMPOSITION_SCHEMA_VERSION,
    SUPPORTED_CONSTRAINT_TYPES,
    _TEMPLATE_KEYS, _REQUIRED_TEMPLATE_KEYS, _PLAN_KEYS, _STEP_KEYS,
    _STEP_BLUEPRINT_KEYS, _CONSTRAINT_SPEC_KEYS, _CHINESE_LABEL, _SEMVER,
)
from agent.templates.catalog import *  # noqa: F401,F403
from agent.templates.compiler import *  # noqa: F401,F403


def __getattr__(name: str):
    if name in {"KNOWN_TOOL_NAMES", "KNOWN_TOOLS", "KNOWN_RESULT_TYPES", "WORKFLOW_TEMPLATE_CATALOG"}:
        from domains.gis import workflow_templates as gis_templates

        return getattr(gis_templates, name)
    raise AttributeError(name)


__all__ = [
    "WorkflowTemplateError",
    "DEFAULT_TEMPLATE_VERSION",
    "WORKFLOW_COMPOSITION_SCHEMA_VERSION",
    "SUPPORTED_CONSTRAINT_TYPES",
    "workflow_template_catalog",
    "get_workflow_template",
    "validate_workflow_template_catalog",
    "validate_workflow_template",
    "workflow_template_context_summary",
    "compile_workflow_plan",
    "compile_workflow_composition",
    "validate_workflow_plan",
    "revise_workflow_plan",
    "validate_template",
    "normalize_workflow_composition",
    "normalize_workflow_constraints",
    "normalize_workflow_evidence",
    "normalize_workflow_selection",
]
