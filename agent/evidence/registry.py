"""Domain-neutral registry for public evidence projections.

The registry is an index, not a new source of truth. It names the bounded
evidence projections already owned by the result, lifecycle, and timeline
seams and gives every consumer the same JSON location and schema version.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent.action_lifecycle import ACTION_LIFECYCLE_SCHEMA_VERSION, project_action_lifecycle
from agent.evidence.component import WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION
from agent.contract_versions import (
    COMPOSITE_EVIDENCE_SCHEMA_VERSION,
    DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION,
    INTERACTION_SCHEMA_VERSION,
    RESULT_ENVELOPE_SCHEMA_VERSION,
)
from agent.evidence.contract import DOMAIN_EVIDENCE_SCHEMA_VERSION
from agent.execution_timeline import EXECUTION_TIMELINE_SCHEMA_VERSION, normalize_execution_timeline
from agent.plan_quality import PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION, project_plan_quality_evidence
from agent.planner_selection import PLANNER_SELECTION_SCHEMA_VERSION
from agent.workflow_selection import WORKFLOW_SELECTION_SCHEMA_VERSION


EVIDENCE_REGISTRY_SCHEMA_VERSION = "spatial-agent.evidence-registry.v1"
EVIDENCE_COMPLETENESS_SCHEMA_VERSION = "spatial-agent.evidence-completeness.v2"
REPLANNING_SCHEMA_VERSION = "spatial-agent.replanning.v1"
_MAX_ENTRIES = 12
_MAX_TEXT = 96
_REQUIRED_ENTRY_IDS = (
    "result",
    "plan_quality",
    "execution_timeline",
    "action_lifecycle",
    "replanning",
    "workflow_selection",
    "planner_selection",
)
_KNOWN_SCHEMA_VERSIONS = {
    RESULT_ENVELOPE_SCHEMA_VERSION,
    PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION,
    EXECUTION_TIMELINE_SCHEMA_VERSION,
    ACTION_LIFECYCLE_SCHEMA_VERSION,
    REPLANNING_SCHEMA_VERSION,
    WORKFLOW_SELECTION_SCHEMA_VERSION,
    PLANNER_SELECTION_SCHEMA_VERSION,
    WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION,
    DOMAIN_EVIDENCE_SCHEMA_VERSION,
    DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION,
    COMPOSITE_EVIDENCE_SCHEMA_VERSION,
    INTERACTION_SCHEMA_VERSION,
}


def build_evidence_registry(
    payload: Mapping[str, Any] | None,
    *,
    custom_entries: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one bounded catalogue of evidence available for a result."""

    source = payload if isinstance(payload, Mapping) else {}
    result = source.get("result") if isinstance(source.get("result"), Mapping) else {}
    planning = result.get("planning") if isinstance(result.get("planning"), Mapping) else {}
    quality = project_plan_quality_evidence(planning.get("plan_quality"))
    timeline = normalize_execution_timeline(result.get("execution_timeline"))
    lifecycle = result.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        # Keep the lifecycle projection aligned with the authoritative result
        # payload.  Passing only status loses retryable/repairable failure
        # metadata at this public evidence boundary.
        lifecycle = project_action_lifecycle(source)
    replanning = result.get("replanning") if isinstance(result.get("replanning"), Mapping) else {}
    events = replanning.get("events") if isinstance(replanning.get("events"), list) else []
    selection = planning.get("workflow_selection") if isinstance(planning.get("workflow_selection"), Mapping) else {}
    planner_selection = planning.get("planner_selection") if isinstance(planning.get("planner_selection"), Mapping) else {}
    routing = result.get("domain_routing_evidence")
    routing = routing if isinstance(routing, Mapping) else {}
    interaction = result.get("interaction")
    interaction = interaction if isinstance(interaction, Mapping) else {}
    entries = [
        _entry("result", RESULT_ENVELOPE_SCHEMA_VERSION, bool(result), "available" if result else "unavailable", "result"),
        _entry("plan_quality", PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION, quality["available"], quality["state"], "result.planning.plan_quality"),
        _entry("execution_timeline", EXECUTION_TIMELINE_SCHEMA_VERSION, timeline["available"], "available" if timeline["available"] else "unavailable", "result.execution_timeline"),
        _entry("action_lifecycle", ACTION_LIFECYCLE_SCHEMA_VERSION, bool(lifecycle), str(lifecycle.get("state") or "unknown"), "result.lifecycle"),
        _entry("replanning", REPLANNING_SCHEMA_VERSION, bool(events), "available" if events else "none", "result.replanning", count=len(events)),
        _entry(
            "workflow_selection",
            WORKFLOW_SELECTION_SCHEMA_VERSION,
            bool(selection),
            _selection_state(selection),
            "result.planning.workflow_selection",
        ),
        _entry(
            "planner_selection",
            PLANNER_SELECTION_SCHEMA_VERSION,
            bool(planner_selection),
            _selection_state(planner_selection),
            "result.planning.planner_selection",
        ),
    ][: _MAX_ENTRIES]
    component_evidence = planning.get("workflow_component_evidence")
    component_evidence_reference = "result.planning.workflow_component_evidence"
    if not isinstance(component_evidence, Mapping):
        component_evidence = selection.get("workflow_component_evidence")
        component_evidence_reference = "result.planning.workflow_selection.workflow_component_evidence"
    if (
        isinstance(component_evidence, Mapping)
        and component_evidence.get("schema_version")
        == WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION
        and len(entries) < _MAX_ENTRIES
    ):
        summary = component_evidence.get("summary")
        summary = summary if isinstance(summary, Mapping) else {}
        count = summary.get("component_count")
        entries.append(
            _entry(
                "workflow_component_evidence",
                WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION,
                bool(component_evidence.get("available")),
                "available" if component_evidence.get("available") else "unavailable",
                component_evidence_reference,
                count=count if isinstance(count, int) and not isinstance(count, bool) else None,
            )
        )
    if routing.get("available") is True and len(entries) < _MAX_ENTRIES:
        routing_available = True
        binding = routing.get("binding") if isinstance(routing.get("binding"), Mapping) else {}
        entries.append(
            _entry(
                "domain_routing_evidence",
                DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION,
                routing_available,
                str(
                    binding.get("state")
                    or ("available" if routing_available else "unavailable")
                ),
                "result.domain_routing_evidence",
            )
        )
    if interaction.get("schema_version") == INTERACTION_SCHEMA_VERSION and len(entries) < _MAX_ENTRIES:
        entries.append(
            _entry(
                "interaction",
                INTERACTION_SCHEMA_VERSION,
                bool(interaction.get("available")),
                str(interaction.get("state") or "unavailable"),
                "result.interaction",
                count=len(interaction.get("actions") or ()),
            )
        )
    for item in custom_entries or ():
        candidate = _custom_entry(result, item)
        if candidate is not None and len(entries) < _MAX_ENTRIES:
            entries.append(candidate)
    return {
        "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION,
        "available": bool(result),
        "entry_count": len(entries),
        "entries": entries,
    }


def normalize_evidence_registry(value: Any) -> dict[str, Any]:
    """Normalize persisted registry data without trusting arbitrary entries."""

    if not isinstance(value, Mapping):
        return _unavailable("evidence_registry_missing")
    if value.get("schema_version") != EVIDENCE_REGISTRY_SCHEMA_VERSION:
        return _unavailable("evidence_registry_unknown_schema")
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list):
        return _unavailable("evidence_registry_entries_invalid")
    entries = []
    for item in raw_entries[:_MAX_ENTRIES]:
        if not isinstance(item, Mapping):
            continue
        entry_id = _text(item.get("id"))
        schema_version = _text(item.get("schema_version"))
        reference = _text(item.get("reference"))
        if not entry_id or not schema_version or not reference:
            continue
        if schema_version not in _KNOWN_SCHEMA_VERSIONS:
            return _unavailable("evidence_registry_unknown_entry_schema")
        if reference != "result" and not reference.startswith("result."):
            return _unavailable("evidence_registry_reference_invalid")
        normalized = {
            "id": entry_id,
            "schema_version": schema_version,
            "available": bool(item.get("available")),
            "state": _text(item.get("state")) or "unknown",
            "reference": reference,
        }
        count = item.get("count")
        if isinstance(count, int) and not isinstance(count, bool):
            normalized["count"] = max(0, min(count, 128))
        entries.append(normalized)
    if not entries:
        return _unavailable("evidence_registry_entries_missing")
    return {
        "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "entry_count": len(entries),
        "entries": entries,
    }


def project_evidence_registry_completeness(value: Any) -> dict[str, Any]:
    """Check the registry shape without interpreting evidence payloads.

    ``normalize_evidence_registry`` is intentionally forgiving for historical
    artifacts.  Replay and cross-entry acceptance need a stricter, separate
    projection: all core entries must be present exactly once, the declared
    count must match, and every entry must stay within the same safe schema
    and JSON-reference rules.  Domain-owned entries remain optional.
    """

    required = list(_REQUIRED_ENTRY_IDS)
    base = {
        "schema_version": EVIDENCE_COMPLETENESS_SCHEMA_VERSION,
        "available": False,
        "passed": False,
        "state": "unavailable",
        "entry_count": 0,
        "required_entry_ids": required,
        "present_entry_ids": [],
        "missing_entry_ids": required,
        "duplicate_entry_ids": [],
        "reason_codes": [],
    }
    if not isinstance(value, Mapping):
        base["reason_codes"] = ["evidence_registry_missing"]
        return base
    if value.get("schema_version") != EVIDENCE_REGISTRY_SCHEMA_VERSION:
        base["reason_codes"] = ["evidence_registry_unknown_schema"]
        return base

    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) > _MAX_ENTRIES:
        base["reason_codes"] = ["evidence_registry_entries_invalid"]
        return base
    declared_count = value.get("entry_count")
    reasons: list[str] = []
    if isinstance(declared_count, bool) or not isinstance(declared_count, int):
        reasons.append("evidence_registry_entry_count_invalid")
    elif declared_count != len(raw_entries):
        reasons.append("evidence_registry_entry_count_mismatch")

    present: list[str] = []
    duplicates: list[str] = []
    for item in raw_entries:
        if not isinstance(item, Mapping):
            reasons.append("evidence_registry_entry_invalid")
            continue
        entry_id = _text(item.get("id"))
        schema_version = _text(item.get("schema_version"))
        reference = _text(item.get("reference"))
        if not entry_id or not schema_version or not reference:
            reasons.append("evidence_registry_entry_identity_missing")
            continue
        if entry_id in present and entry_id not in duplicates:
            duplicates.append(entry_id)
        present.append(entry_id)
        if schema_version not in _KNOWN_SCHEMA_VERSIONS:
            reasons.append("evidence_registry_unknown_entry_schema")
        if reference != "result" and not reference.startswith("result."):
            reasons.append("evidence_registry_reference_invalid")

    missing = [entry_id for entry_id in required if entry_id not in present]
    if missing:
        reasons.append("evidence_registry_required_entry_missing")
    if duplicates:
        reasons.append("evidence_registry_duplicate_entry")
    # Keep codes deterministic and bounded for replay artifacts and UI.
    reasons = list(dict.fromkeys(reasons))[:12]
    passed = not reasons and bool(value.get("available"))
    base.update(
        {
            "available": bool(value.get("available")),
            "passed": passed,
            "state": "complete" if passed else "incomplete",
            "entry_count": len(raw_entries),
            "present_entry_ids": present[:_MAX_ENTRIES],
            "missing_entry_ids": missing,
            "duplicate_entry_ids": duplicates,
            "reason_codes": reasons or (["evidence_registry_unavailable"] if not value.get("available") else []),
        }
    )
    return base


def _entry(entry_id: str, schema_version: str, available: bool, state: str, reference: str, *, count: int | None = None) -> dict[str, Any]:
    result = {
        "id": entry_id[:_MAX_TEXT],
        "schema_version": schema_version[:_MAX_TEXT],
        "available": bool(available),
        "state": str(state or "unknown")[:_MAX_TEXT],
        "reference": reference[:_MAX_TEXT],
    }
    if count is not None:
        result["count"] = max(0, min(int(count), 128))
    return result


def _custom_entry(result: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build one Domain-owned entry without accepting arbitrary references."""
    entry_id = _text(item.get("id"))
    schema_version = _text(item.get("schema_version"))
    reference = _text(item.get("reference"))
    if not entry_id or not schema_version or not reference:
        return None
    if schema_version not in _KNOWN_SCHEMA_VERSIONS:
        return None
    if reference != "result" and not reference.startswith("result."):
        return None
    current: Any = result
    for part in reference.split(".")[1:]:
        if not isinstance(current, Mapping):
            current = None
            break
        current = current.get(part)
    available = current is not None and current != {}
    state = "available" if available else "unavailable"
    if isinstance(current, Mapping) and current.get("status"):
        state = _text(current.get("status")) or state
    return _entry(entry_id, schema_version, available, state, reference)


def _selection_state(value: Mapping[str, Any]) -> str:
    """Use only the declared bounded state in a Registry index entry."""

    state = _text(value.get("state")) if isinstance(value, Mapping) else ""
    return state or "unavailable"


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION,
        "available": False,
        "entry_count": 0,
        "entries": [],
        "reason_code": _text(reason_code),
    }


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


__all__ = [
    "EVIDENCE_COMPLETENESS_SCHEMA_VERSION",
    "EVIDENCE_REGISTRY_SCHEMA_VERSION",
    "REPLANNING_SCHEMA_VERSION",
    "build_evidence_registry",
    "normalize_evidence_registry",
    "project_evidence_registry_completeness",
]
