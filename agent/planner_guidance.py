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
