"""Bounded capability-selection evidence for Planner and public results.

Capability discovery answers which Domain-declared abilities are plausible;
workflow selection answers which executable workflow was resolved.  This
module keeps the smaller, user-visible bridge between those decisions.  It
contains identifiers, bounded fact names, and descriptor summaries only.  It
never carries request text, prompts, model output, tool arguments, or raw
provider details.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .capability_descriptor import (
    normalize_capability_descriptor,
)


CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION = (
    "spatial-agent.capability-selection.v1"
)
CAPABILITY_SELECTION_STATES = frozenset(
    {"selected", "ambiguous", "clarification", "unavailable", "not_applicable"}
)
_MAX_ITEMS = 16
_MAX_SUMMARIES = 8
_MAX_TEXT = 320
_CODE_RE = re.compile(r"[^a-z0-9_.-]+")


def build_capability_selection_evidence(
    *,
    discovery: Mapping[str, Any] | None = None,
    selection: Mapping[str, Any] | None = None,
    capability_catalog: Mapping[str, Any] | None = None,
    request_facts: Mapping[str, Any] | None = None,
    not_applicable: bool = False,
) -> dict[str, Any]:
    """Build a stable explanation of capability discovery and selection."""

    discovery_map = _mapping(discovery)
    selection_map = _mapping(selection)
    if not selection_map:
        selection_map = discovery_map

    candidate_ids = _strings(
        selection_map.get("candidate_ids")
        if "candidate_ids" in selection_map
        else discovery_map.get("candidate_ids")
    )
    selected = _text(
        selection_map.get("selected_capability_id")
        or discovery_map.get("selected_capability_id")
    ) or None
    if selected and selected not in candidate_ids:
        candidate_ids.insert(0, selected)
    candidate_ids = candidate_ids[:_MAX_ITEMS]

    state = _state(
        "not_applicable"
        if not_applicable
        else selection_map.get("state")
        or discovery_map.get("selection_state")
    )
    suggested_ids = _strings(
        selection_map.get("suggested_capability_ids")
        or discovery_map.get("suggested_capability_ids")
        or _mapping(discovery_map.get("guidance")).get(
            "suggested_capability_ids"
        )
    )
    reason_code = _code(
        # Discovery owns the capability decision.  A later workflow layer
        # may report the broader ``workflow_selected`` code, but that would
        # hide the reason users need at this boundary.
        discovery_map.get("discovery_reason_code")
        or selection_map.get("reason_code")
        or _mapping(discovery_map.get("guidance")).get("reason_code")
        or _default_reason(state)
    )
    source = _code(
        selection_map.get("source")
        or discovery_map.get("source")
        or "none"
    )
    if source not in {
        "catalog",
        "domain",
        "domain_discovery",
        "domain_composition",
        "explicit_workflow",
        "user_confirmation",
        "none",
    }:
        source = "none"

    missing = _missing_fields(
        selection_map.get("missing_fields")
        if "missing_fields" in selection_map
        else discovery_map.get("missing_fields")
    )
    if not missing:
        guidance = _mapping(discovery_map.get("guidance"))
        missing = _missing_fields(guidance.get("missing_fields"))

    facts = _mapping(request_facts)
    fact_keys = _strings(
        selection_map.get("fact_keys")
        or discovery_map.get("fact_keys")
        or _fact_keys(facts)
    )
    matched_signals = _strings(discovery_map.get("signals"))
    descriptors = _descriptor_index(capability_catalog)
    summaries = [
        _descriptor_summary(descriptors[item])
        for item in candidate_ids
        if item in descriptors
    ][: _MAX_SUMMARIES]

    available = bool(selected or candidate_ids or suggested_ids)
    domain_id = _text(
        selection_map.get("domain_id") or discovery_map.get("domain_id"), 80
    ) or "unknown"
    candidate_count = _bounded_int(
        selection_map.get("candidate_count")
        if selection_map.get("candidate_count") is not None
        else discovery_map.get("candidate_count"),
        len(candidate_ids),
    )
    return {
        "schema_version": CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION,
        "available": available,
        "state": state,
        "domain_id": domain_id,
        "source": source,
        "reason_code": reason_code,
        "chosen_capability_id": selected,
        "selected_capability_id": selected,
        "candidate_ids": candidate_ids,
        "candidate_count": candidate_count,
        "suggested_capability_ids": suggested_ids[:_MAX_ITEMS],
        "missing_fields": missing[:_MAX_ITEMS],
        "missing_fact_ids": [item["id"] for item in missing[:_MAX_ITEMS]],
        "fact_keys": fact_keys[:_MAX_ITEMS],
        "matched_signals": matched_signals[:_MAX_ITEMS],
        "selection_basis": {
            "source": source,
            "fact_keys": fact_keys[:_MAX_ITEMS],
            "matched_signal_count": len(matched_signals),
        },
        "candidate_summaries": summaries,
    }


def normalize_capability_selection_evidence(value: Any) -> dict[str, Any]:
    """Normalize persisted selection evidence and fail closed on new schemas."""

    if not isinstance(value, Mapping):
        return _unavailable("capability_selection_missing")
    if value.get("schema_version") != CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION:
        return _unavailable("capability_selection_unknown_schema")
    state = _state(value.get("state"))
    candidate_ids = _strings(value.get("candidate_ids"))[:_MAX_ITEMS]
    selected = _text(
        value.get("chosen_capability_id") or value.get("selected_capability_id")
    ) or None
    if selected and selected not in candidate_ids:
        candidate_ids.insert(0, selected)
    missing = _missing_fields(value.get("missing_fields"))[:_MAX_ITEMS]
    fact_keys = _strings(value.get("fact_keys"))[:_MAX_ITEMS]
    signals = _strings(value.get("matched_signals"))[:_MAX_ITEMS]
    summaries = _normalize_summaries(value.get("candidate_summaries"))
    source = _code(value.get("source"))
    if source not in {
        "catalog",
        "domain",
        "domain_discovery",
        "domain_composition",
        "explicit_workflow",
        "user_confirmation",
        "none",
    }:
        source = "none"
    return {
        "schema_version": CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "state": state,
        "domain_id": _text(value.get("domain_id"), 80) or "unknown",
        "source": source,
        "reason_code": _code(value.get("reason_code")) or _default_reason(state),
        "chosen_capability_id": selected,
        "selected_capability_id": selected,
        "candidate_ids": candidate_ids,
        "candidate_count": _bounded_int(value.get("candidate_count"), len(candidate_ids)),
        "suggested_capability_ids": _strings(value.get("suggested_capability_ids"))[:_MAX_ITEMS],
        "missing_fields": missing,
        "missing_fact_ids": [item["id"] for item in missing],
        "fact_keys": fact_keys,
        "matched_signals": signals,
        "selection_basis": {
            "source": source,
            "fact_keys": fact_keys,
            "matched_signal_count": len(signals),
        },
        "candidate_summaries": summaries,
    }


def _unavailable(reason_code: str) -> dict[str, Any]:
    return normalize_capability_selection_evidence(
        {
            "schema_version": CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION,
            "available": False,
            "state": "unavailable",
            "reason_code": reason_code,
            "domain_id": "unknown",
            "source": "none",
            "candidate_ids": [],
            "candidate_count": 0,
        }
    )


def _descriptor_index(value: Any) -> dict[str, dict[str, Any]]:
    source = value if isinstance(value, Mapping) else {}
    descriptors = source.get("capability_descriptors")
    if not isinstance(descriptors, Sequence) or isinstance(descriptors, (str, bytes)):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in descriptors[:64]:
        normalized = normalize_capability_descriptor(item)
        if normalized is not None:
            result[normalized["capability_id"]] = normalized
    return result


def _descriptor_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    inputs = _mapping(value.get("inputs"))
    outputs = _mapping(value.get("outputs"))
    preconditions = _mapping(value.get("preconditions"))
    availability = _mapping(value.get("availability"))
    cost = _mapping(value.get("cost_hint"))
    return {
        "capability_id": _text(value.get("capability_id"), 96),
        "label": _text(value.get("label"), 96),
        "summary": _text(value.get("summary"), _MAX_TEXT),
        "input_facts": _strings(
            inputs.get("facts") or preconditions.get("required_facts")
        )[:24],
        "result_types": _strings(outputs.get("result_types"))[:16],
        "availability": {
            "available": bool(availability.get("available")),
            "mode": _code(availability.get("mode")) or "unknown",
            "status": _code(availability.get("status")) or "unknown",
            "reason": _text(availability.get("reason"), 96) or "unknown",
        },
        "cost_class": _code(cost.get("class")) or "unknown",
        "estimated_step_count": _bounded_int(cost.get("estimated_step_count"), 0),
    }


def _normalize_summaries(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    result = []
    for item in items[:_MAX_SUMMARIES]:
        if not isinstance(item, Mapping):
            continue
        capability_id = _text(item.get("capability_id") or item.get("id"), 96)
        if not capability_id:
            continue
        result.append(
            _descriptor_summary(
                {
                    "capability_id": capability_id,
                    "label": item.get("label"),
                    "summary": item.get("summary") or item.get("description"),
                    "inputs": {"facts": item.get("input_facts")},
                    "outputs": {"result_types": item.get("result_types")},
                    "availability": item.get("availability") or {
                        "available": item.get("available")
                    },
                    "cost_hint": {"class": item.get("cost_class")},
                }
            )
        )
    return result


def _missing_fields(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, (list, tuple)) else []
    result = []
    seen = set()
    for item in items[:_MAX_ITEMS]:
        if isinstance(item, Mapping):
            field_id = _text(item.get("id"), 80)
            label = _text(item.get("label"), 120) or field_id
            kind = _code(item.get("kind")) or "fact"
            required = item.get("required")
        else:
            field_id = _text(item, 80)
            label = field_id
            kind = "fact"
            required = None
        if not field_id or field_id in seen:
            continue
        seen.add(field_id)
        field = {"id": field_id, "label": label[:120], "kind": kind[:32]}
        if isinstance(required, bool):
            field["required"] = required
        result.append(field)
    return result


def _fact_keys(value: Mapping[str, Any]) -> list[str]:
    keys = []
    for name in ("entities", "tasks", "constraints", "datasets", "evidence"):
        if value.get(name):
            keys.append(name)
    return keys


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result = []
    for item in value:
        text = _text(item, 96)
        if text and text not in result:
            result.append(text)
        if len(result) >= _MAX_ITEMS:
            break
    return result


def _text(value: Any, limit: int = 96) -> str:
    return str(value or "").strip()[:limit]


def _code(value: Any) -> str:
    text = _text(value, 96).lower()
    return _CODE_RE.sub("_", text).strip("_")[:96]


def _state(value: Any) -> str:
    state = _code(value)
    return state if state in CAPABILITY_SELECTION_STATES else "unavailable"


def _default_reason(state: str) -> str:
    return {
        "selected": "capability_selected",
        "ambiguous": "multiple_capabilities",
        "clarification": "selection_requires_facts",
        "not_applicable": "capability_selection_not_applicable",
    }.get(state, "no_matching_capability")


def _bounded_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        value = fallback
    return max(0, min(int(value), _MAX_ITEMS))


__all__ = [
    "CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION",
    "CAPABILITY_SELECTION_STATES",
    "build_capability_selection_evidence",
    "normalize_capability_selection_evidence",
]
