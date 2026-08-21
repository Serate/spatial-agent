"""Domain-neutral evidence for capability-to-workflow selection.

The selection decision belongs to a Domain Pack or an explicit caller.  This
module only defines the bounded public projection consumed by planners,
clarification responses, result contracts, artifacts and the Contract
Harness.  It intentionally knows nothing about GIS names or tool behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


WORKFLOW_SELECTION_SCHEMA_VERSION = "spatial-agent.workflow-selection.v1"
WORKFLOW_SELECTION_STATES = {"selected", "ambiguous", "clarification", "unavailable"}
WORKFLOW_SELECTION_SOURCES = {
    "explicit_workflow",
    "domain_discovery",
    "domain_policy",
    "user_confirmation",
    "none",
}
_MAX_ITEMS = 16
_MAX_TEXT = 96


def build_workflow_selection_evidence(
    *,
    discovery: Mapping[str, Any] | None = None,
    domain_selection: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
    request_facts: Any = None,
    domain_id: str = "unknown",
    state: str | None = None,
    reason_code: str | None = None,
) -> dict[str, Any]:
    """Build a bounded selection projection without selecting by domain name."""

    discovery_map = _mapping(discovery)
    selected = _mapping(domain_selection)
    explicit = _mapping(workflow)
    candidate_ids = _string_list(
        selected.get("candidate_ids")
        if "candidate_ids" in selected
        else discovery_map.get("candidate_ids")
    )
    selected_capability = _text(
        selected.get("selected_capability_id")
        or discovery_map.get("selected_capability_id")
    ) or None
    if selected_capability and selected_capability not in candidate_ids:
        candidate_ids.insert(0, selected_capability)
    candidate_ids = candidate_ids[:_MAX_ITEMS]
    template_id = _text(
        explicit.get("template_id")
        or selected.get("workflow_template_id")
    ) or None
    template_version = _text(
        explicit.get("template_version")
        or selected.get("workflow_template_version")
    ) or None
    candidate_templates = _string_list(
        selected.get("candidate_workflow_ids")
        or selected.get("candidate_template_ids")
    )
    source = _text(selected.get("source")) or (
        "explicit_workflow" if template_id and explicit.get("template_id") else
        "domain_discovery" if selected_capability or candidate_ids else "none"
    )
    if source not in WORKFLOW_SELECTION_SOURCES:
        source = "none"
    missing = _normalize_missing(selected.get("missing_fields"))
    declared_state = _text(selected.get("state"))
    if state not in WORKFLOW_SELECTION_STATES:
        if declared_state in WORKFLOW_SELECTION_STATES and not template_id:
            state = declared_state
        elif missing:
            state = "clarification"
        elif template_id or selected_capability:
            state = "selected"
        elif len(candidate_ids) > 1:
            state = "ambiguous"
        else:
            state = "unavailable"
    available = bool(template_id or selected_capability or candidate_ids)
    if reason_code is None:
        reason_code = {
            "selected": "workflow_selected",
            "ambiguous": "multiple_capabilities",
            "clarification": "selection_requires_facts",
            "unavailable": "no_matching_capability",
        }.get(state, "workflow_selection_unavailable")
    facts = _facts_summary(request_facts)
    return {
        "schema_version": WORKFLOW_SELECTION_SCHEMA_VERSION,
        "available": available,
        "state": state,
        "reason_code": _text(reason_code) or "workflow_selection_unavailable",
        "domain_id": _text(domain_id) or "unknown",
        "source": source,
        "selected_by": _text(selected.get("selected_by")) or (
            "user" if explicit.get("template_id") else "domain" if available else "none"
        ),
        "selected_capability_id": selected_capability,
        "candidate_ids": candidate_ids,
        "candidate_count": _bounded_int(
            selected.get("candidate_count"), 0, _MAX_ITEMS
        ) if selected.get("candidate_count") is not None else len(candidate_ids),
        "workflow_template_id": template_id,
        "workflow_template_version": template_version,
        "candidate_workflow_ids": candidate_templates[:_MAX_ITEMS],
        "missing_fields": missing,
        "request_facts_schema_version": facts["schema_version"],
        "fact_keys": facts["fact_keys"],
    }


def normalize_workflow_selection_evidence(value: Any) -> dict[str, Any]:
    """Normalize current and unknown persisted selection evidence safely."""

    if not isinstance(value, Mapping):
        return build_workflow_selection_evidence(
            domain_id="unknown", state="unavailable", reason_code="selection_missing"
        )
    if value.get("schema_version") != WORKFLOW_SELECTION_SCHEMA_VERSION:
        return build_workflow_selection_evidence(
            domain_id=_text(value.get("domain_id")) or "unknown",
            state="unavailable",
            reason_code="selection_unknown_schema",
        )
    return build_workflow_selection_evidence(
        discovery=value,
        domain_selection=value,
        request_facts={
            "schema_version": value.get("request_facts_schema_version"),
            **{key: True for key in (value.get("fact_keys") or [])},
        },
        domain_id=_text(value.get("domain_id")) or "unknown",
        state=_text(value.get("state")) or "unavailable",
        reason_code=_text(value.get("reason_code")) or "workflow_selection_unavailable",
    )


def _facts_summary(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    if not source and value is not None:
        method = getattr(value, "as_context_dict", None)
        candidate = method() if callable(method) else None
        source = candidate if isinstance(candidate, Mapping) else {}
    keys = []
    for key in ("admin_name", "region", "entity", "place", "tasks", "datasets", "constraints", "evidence"):
        raw = source.get(key)
        if raw:
            keys.append(key)
    return {
        "schema_version": _text(source.get("schema_version")) or "spatial-agent.request-facts.v1",
        "fact_keys": keys[:_MAX_ITEMS],
    }


def _normalize_missing(value: Any) -> list[dict[str, str]]:
    values = value if isinstance(value, (list, tuple)) else []
    result = []
    for item in values[:_MAX_ITEMS]:
        if isinstance(item, Mapping):
            field_id = _text(item.get("id"))
            label = _text(item.get("label"))
            kind = _text(item.get("kind"))
            if field_id and label:
                result.append({"id": field_id, "label": label, "kind": kind or "fact"})
        elif _text(item):
            result.append({"id": _text(item), "label": _text(item), "kind": "fact"})
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


def _string_list(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else []
    result = []
    for item in values:
        value = _text(item)
        if value and value not in result:
            result.append(value)
        if len(result) >= _MAX_ITEMS:
            break
    return result


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(minimum, min(value, maximum))


__all__ = [
    "WORKFLOW_SELECTION_SCHEMA_VERSION",
    "WORKFLOW_SELECTION_SOURCES",
    "WORKFLOW_SELECTION_STATES",
    "build_workflow_selection_evidence",
    "normalize_workflow_selection_evidence",
]
