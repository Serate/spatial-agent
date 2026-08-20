"""Generic, bounded guidance for domain-owned request understanding.

Request extraction and capability discovery are domain policies.  The Runtime
only carries this small projection to planners and evidence; it does not
interpret task names, dataset names, or lexical hints.
"""

from __future__ import annotations

from typing import Any, Mapping


REQUEST_UNDERSTANDING_GUIDANCE_SCHEMA_VERSION = (
    "spatial-agent.request-understanding-guidance.v1"
)


def normalize_request_understanding_guidance(
    value: Any,
    *,
    domain_id: str = "unknown",
) -> dict[str, Any]:
    """Return a bounded JSON-safe projection for context and plan evidence."""

    source = value if isinstance(value, Mapping) else {}
    result: dict[str, Any] = {
        "schema_version": REQUEST_UNDERSTANDING_GUIDANCE_SCHEMA_VERSION,
        "domain_id": str(source.get("domain_id") or domain_id)[:80],
        "available": bool(source),
        "fact_fields": _strings(source.get("fact_fields"), 16, 80),
        "task_hints": _hint_items(source.get("task_hints")),
        "constraint_hints": _hint_items(source.get("constraint_hints")),
        "evidence_hints": _hint_items(source.get("evidence_hints")),
        "clarification_policy": _strings(source.get("clarification_policy"), 12, 240),
        "discovery_policy": _strings(source.get("discovery_policy"), 12, 240),
    }
    return result


def _strings(value: Any, limit: int, max_chars: int) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    result = []
    for item in list(value)[:limit]:
        text = str(item).strip()
        if text:
            result.append(text[:max_chars])
    return result


def _hint_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in list(value)[:24]:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("id") or item.get("key") or "").strip()
        if not key:
            continue
        entry: dict[str, Any] = {"id": key[:96]}
        for field in ("label", "description"):
            if item.get(field):
                entry[field] = str(item[field])[:240]
        phrases = _strings(item.get("phrases"), 12, 80)
        if phrases:
            entry["phrases"] = phrases
        result.append(entry)
    return result


def guidance_context(value: Any, *, domain_id: str = "unknown") -> dict[str, Any]:
    """Alias with an intent-revealing name for callers assembling context."""

    return normalize_request_understanding_guidance(value, domain_id=domain_id)
