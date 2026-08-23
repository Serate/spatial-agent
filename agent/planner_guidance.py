"""Shared contract and rendering helpers for Domain-owned planner policy.

The LLM Planner owns the output protocol. A Domain Pack owns the vocabulary
and planning policy that makes that protocol useful for a particular domain.
Keeping normalization here gives both sides a small, testable seam.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


PLANNER_GUIDANCE_SCHEMA_VERSION = "spatial-agent.planner-guidance.v1"
_MAX_ITEMS = 64
_MAX_TEXT = 800


def normalize_planner_guidance(value: Any) -> dict[str, Any]:
    """Return a bounded JSON-safe planner guidance projection."""
    source = value if isinstance(value, Mapping) else {}
    return {
        "schema_version": PLANNER_GUIDANCE_SCHEMA_VERSION,
        "domain_id": _text(source.get("domain_id"), "generic", 80),
        "domain_description": _text(source.get("domain_description"), "", _MAX_TEXT),
        "tool_semantics": _text_map(source.get("tool_semantics")),
        "result_types": _text_map(source.get("result_types")),
        "planning_rules": _text_list(source.get("planning_rules")),
        "clarification_policy": _text_list(source.get("clarification_policy")),
        "rejection_policy": _text_list(source.get("rejection_policy")),
    }


def render_planner_guidance(value: Any, allowed_tools: Iterable[str] = ()) -> str:
    """Render domain policy while exposing only registered tool semantics."""
    guidance = normalize_planner_guidance(value)
    allowed = {str(item) for item in allowed_tools if str(item)}
    semantics = guidance["tool_semantics"]
    if allowed:
        guidance["tool_semantics"] = {
            name: description
            for name, description in semantics.items()
            if name in allowed
        }
    return json.dumps(guidance, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_planner_guidance_for_context(
    value: Any,
    allowed_tools: Iterable[str] = (),
    context: Any = None,
) -> str:
    """Render policy without repeating an already selected workflow contract.

    Domain guidance remains the authoritative source.  When Runtime context
    already carries a selected blueprint and input schemas, tool descriptions
    and tool/result-specific planning rules are duplicate prompt material.
    General Domain invariants, clarification, and rejection policy are always
    retained.
    """

    guidance = normalize_planner_guidance(value)
    allowed = {str(item) for item in allowed_tools if str(item)}
    sections = context.get("sections") if isinstance(context, Mapping) else None
    sections = sections if isinstance(sections, Mapping) else {}
    catalog = sections.get("capability_catalog")
    catalog = catalog if isinstance(catalog, Mapping) else {}
    schemas = catalog.get("tool_schemas")
    schema_tools = {
        str(name)
        for name, definition in (schemas.items() if isinstance(schemas, Mapping) else ())
        if isinstance(definition, Mapping)
    }
    templates_section = sections.get("workflow_templates")
    templates_section = templates_section if isinstance(templates_section, Mapping) else {}
    templates = [
        item
        for item in (templates_section.get("templates") or [])
        if isinstance(item, Mapping)
    ]
    selected_tools = {
        str(tool)
        for item in templates
        for tool in (item.get("allowed_tools") or [])
        if str(tool)
    }
    selected_result_types = {
        str(result_type)
        for item in templates
        for result_type in (
            list(item.get("result_types") or [])
            + ([item.get("output_type")] if item.get("output_type") else [])
        )
        if str(result_type)
    }
    has_blueprint = any(item.get("step_blueprint") for item in templates)

    semantics = guidance["tool_semantics"]
    described_by_schema = schema_tools.intersection(selected_tools or schema_tools)
    guidance["tool_semantics"] = {
        name: description
        for name, description in semantics.items()
        if (not allowed or name in allowed) and name not in described_by_schema
    }
    if selected_result_types:
        guidance["result_types"] = {
            name: description
            for name, description in guidance["result_types"].items()
            if name in selected_result_types
        }
    if has_blueprint:
        duplicate_terms = selected_tools | selected_result_types
        guidance["planning_rules"] = [
            rule
            for rule in guidance["planning_rules"]
            if not any(term and term in rule for term in duplicate_terms)
        ]
    return json.dumps(guidance, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: Any, default: str, limit: int) -> str:
    if value is None:
        return default
    return str(value).strip()[:limit]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_text(item, "", _MAX_TEXT) for item in value[:_MAX_ITEMS] if str(item).strip()]


def _text_map(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, item in list(value.items())[:_MAX_ITEMS]:
        name = _text(key, "", 120)
        description = _text(item, "", _MAX_TEXT)
        if name and description:
            result[name] = description
    return result
