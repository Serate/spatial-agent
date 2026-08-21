"""Domain-neutral evidence for Planner capability alignment.

The Domain Pack owns discovery and the candidate catalog.  This module only
compares the selected candidate with the result type declared by a generated
TaskPlan, so a model/domain disagreement is visible to every result surface
without making the Runtime understand GIS or another business vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PLANNER_SELECTION_SCHEMA_VERSION = "spatial-agent.planner-selection.v1"
_STATES = {"matched", "mismatch", "unresolved", "unavailable", "not_applicable"}


def build_planner_selection_evidence(
    plan: Any,
    selection: Mapping[str, Any] | None,
    *,
    planner_kind: str = "unknown",
) -> dict[str, Any]:
    """Return bounded evidence comparing a plan with Domain selection."""

    output = getattr(plan, "output", None)
    if not isinstance(output, Mapping):
        output = plan.get("output") if isinstance(plan, Mapping) else {}
    result_type = _text(output.get("type"))
    if result_type == "direct_answer":
        return _payload(
            state="not_applicable",
            reason_code="direct_answer_has_no_capability_selection",
            result_type=result_type,
            selected=None,
            planner_capability=None,
            planner_kind=planner_kind,
            candidates=[],
        )

    source = selection if isinstance(selection, Mapping) else {}
    selected = _text(source.get("selected_capability_id")) or None
    candidate_ids = _string_list(source.get("candidate_ids"))
    details = source.get("candidate_details")
    details = details if isinstance(details, list) else []
    # A selected planner context intentionally keeps one candidate card in
    # detail to stay within the model budget.  Domain Packs may still expose
    # a compact id -> result-type summary for every candidate so a model plan
    # that chooses another capability is reported as ``mismatch`` rather than
    # being incorrectly downgraded to ``unresolved``.
    summaries = source.get("candidate_result_types")
    summaries = summaries if isinstance(summaries, list) else []
    known_summaries = source.get("known_capability_result_types")
    known_summaries = known_summaries if isinstance(known_summaries, list) else []
    matches = []
    for item in [*details[:16], *summaries[:16], *known_summaries[:16]]:
        if not isinstance(item, Mapping):
            continue
        capability_id = _text(item.get("id") or item.get("capability_id"))
        result_types = _string_list(item.get("result_types"))
        workflow = item.get("workflow")
        if isinstance(workflow, Mapping):
            result_types.extend(_string_list(workflow.get("result_types")))
        if capability_id and result_type in result_types and capability_id not in matches:
            matches.append(capability_id)
    matches = matches[:8]
    planner_capability = matches[0] if len(matches) == 1 else None

    if not selected and not candidate_ids:
        state = "unavailable"
        reason = "domain_selection_unavailable"
    elif planner_capability is None:
        state = "unresolved"
        reason = "planner_result_type_not_bound_to_candidate"
    elif selected == planner_capability:
        state = "matched"
        reason = "planner_matches_selected_capability"
    else:
        state = "mismatch"
        reason = "planner_differs_from_selected_capability"
    return _payload(
        state=state,
        reason_code=reason,
        result_type=result_type or None,
        selected=selected,
        planner_capability=planner_capability,
        planner_kind=planner_kind,
        candidates=candidate_ids,
    )


def normalize_planner_selection_evidence(value: Any) -> dict[str, Any]:
    """Normalize persisted alignment evidence and degrade unknown schemas."""

    if not isinstance(value, Mapping) or value.get("schema_version") != PLANNER_SELECTION_SCHEMA_VERSION:
        return _payload(
            state="unavailable",
            reason_code="planner_selection_unknown_schema",
            result_type=None,
            selected=None,
            planner_capability=None,
            planner_kind="unknown",
            candidates=[],
        )
    state = _text(value.get("state"))
    if state not in _STATES:
        state = "unavailable"
    return _payload(
        state=state,
        reason_code=_text(value.get("reason_code")) or "planner_selection_unavailable",
        result_type=_text(value.get("result_type")) or None,
        selected=_text(value.get("selected_capability_id")) or None,
        planner_capability=_text(value.get("planner_capability_id")) or None,
        planner_kind=_text(value.get("planner_kind")) or "unknown",
        candidates=_string_list(value.get("candidate_ids")),
    )


def _payload(*, state: str, reason_code: str, result_type: str | None,
             selected: str | None, planner_capability: str | None,
             planner_kind: Any, candidates: list[str]) -> dict[str, Any]:
    return {
        "schema_version": PLANNER_SELECTION_SCHEMA_VERSION,
        "state": state if state in _STATES else "unavailable",
        "reason_code": _text(reason_code) or "planner_selection_unavailable",
        "result_type": _text(result_type) or None,
        "selected_capability_id": _text(selected) or None,
        "planner_capability_id": _text(planner_capability) or None,
        "planner_kind": _text(planner_kind) or "unknown",
        "candidate_ids": _string_list(candidates),
    }


def _text(value: Any) -> str:
    return str(value or "").strip()[:96]


def _string_list(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else []
    result = []
    for item in values:
        text = _text(item)
        if text and text not in result:
            result.append(text)
        if len(result) >= 16:
            break
    return result


__all__ = [
    "PLANNER_SELECTION_SCHEMA_VERSION",
    "build_planner_selection_evidence",
    "normalize_planner_selection_evidence",
]
