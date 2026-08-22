"""Domain-neutral, bounded execution timeline evidence.

The timeline is a display and comparison projection, not a second Runtime
state machine.  It combines the already-authoritative plan-quality,
step-status, repair and lifecycle contracts without copying requests,
arguments, timestamps or raw exceptions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .action_lifecycle import LIFECYCLE_ACTIONS, project_action_lifecycle
from .plan_quality import project_plan_quality_evidence


EXECUTION_TIMELINE_SCHEMA_VERSION = "spatial-agent.execution-timeline.v1"
ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION = "spatial-agent.action-timeline-linkage.v1"
_MAX_EVENTS = 64
_MAX_TEXT = 96


def build_execution_timeline(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    result = source.get("result") if isinstance(source.get("result"), Mapping) else {}
    planning = source.get("plan_evidence")
    if not isinstance(planning, Mapping):
        planning = result.get("planning") if isinstance(result.get("planning"), Mapping) else {}

    events: list[dict[str, Any]] = []
    quality = project_plan_quality_evidence(planning.get("plan_quality"))
    if planning or quality.get("available"):
        planning_event = {
            "kind": "planning",
            "state": quality["state"],
            "reason_code": quality["reason_code"],
        }
        if quality.get("template_id"):
            planning_event["template_id"] = quality["template_id"]
        events.append(planning_event)

    steps = source.get("steps") if isinstance(source.get("steps"), list) else []
    for step in steps[:24]:
        if not isinstance(step, Mapping):
            continue
        item = {
            "kind": "step",
            "id": _text(step.get("id")),
            "tool": _text(step.get("tool")),
            "status": _text(step.get("status")) or "UNKNOWN",
        }
        if step.get("error_category"):
            item["error_category"] = _text(step.get("error_category"))
        if step.get("error_code"):
            item["error_code"] = _text(step.get("error_code"))
        attempts = step.get("attempts")
        if isinstance(attempts, int) and not isinstance(attempts, bool):
            item["attempts"] = max(0, min(attempts, 128))
        if item["id"] and item["tool"]:
            events.append(item)

    raw_replans = source.get("replan_events")
    if not isinstance(raw_replans, list):
        nested = result.get("replanning") if isinstance(result.get("replanning"), Mapping) else {}
        raw_replans = nested.get("events") if isinstance(nested.get("events"), list) else []
    for event in raw_replans[:8]:
        if not isinstance(event, Mapping):
            continue
        failed_step = _text(event.get("failed_step_id"))
        failed_tool = _text(event.get("failed_tool"))
        if not failed_step or not failed_tool:
            continue
        item = {
            "kind": "repair",
            "phase": _text(event.get("phase")) or "execution",
            "failed_step_id": failed_step,
            "failed_tool": failed_tool,
            "replacement_step_count": min(
                len(event.get("replanned_step_ids") or [])
                if isinstance(event.get("replanned_step_ids"), list)
                else 0,
                24,
            ),
        }
        for key in ("plan_quality_before", "plan_quality_after"):
            item[key] = project_plan_quality_evidence(event.get(key))
        events.append(item)

    lifecycle = project_action_lifecycle(source)
    lifecycle_event = {
        "kind": "lifecycle",
        "state": _text(lifecycle.get("state")) or "failed",
        "phase": _text(lifecycle.get("phase")) or "unknown",
    }
    actions = lifecycle.get("allowed_actions")
    if isinstance(actions, list):
        safe_actions = [
            _text(item)
            for item in actions
            if _text(item) in LIFECYCLE_ACTIONS
        ][:8]
        if safe_actions:
            lifecycle_event["allowed_actions"] = safe_actions
    if lifecycle.get("reason_code"):
        lifecycle_event["reason_code"] = _text(lifecycle.get("reason_code"))
    events.append(lifecycle_event)

    action_event = _action_event(source, result)
    if action_event is not None:
        events.append(action_event)
    events = events[:_MAX_EVENTS]
    return {
        "schema_version": EXECUTION_TIMELINE_SCHEMA_VERSION,
        "available": bool(events),
        "event_count": len(events),
        "events": events,
    }


def normalize_execution_timeline(
    value: Any,
    *,
    include_action_events: bool = True,
) -> dict[str, Any]:
    """Validate a persisted timeline and degrade unknown shapes safely."""

    if not isinstance(value, Mapping):
        return _unavailable("execution_timeline_missing")
    if value.get("schema_version") != EXECUTION_TIMELINE_SCHEMA_VERSION:
        return _unavailable("execution_timeline_unknown_schema")
    events = value.get("events")
    if not isinstance(events, list):
        return _unavailable("execution_timeline_events_invalid")
    safe_events = []
    for event in events[:_MAX_EVENTS]:
        if not isinstance(event, Mapping):
            continue
        if not include_action_events and event.get("kind") == "action":
            continue
        safe_events.append(event)
    return {
        "schema_version": EXECUTION_TIMELINE_SCHEMA_VERSION,
        "available": bool(value.get("available")) and bool(safe_events),
        "event_count": len(safe_events),
        "events": [_normalize_event(event) for event in safe_events],
    }


def _normalize_event(value: Mapping[str, Any]) -> dict[str, Any]:
    kind = _text(value.get("kind")) or "unknown"
    result = {"kind": kind}
    if kind == "action":
        result["action_linkage"] = _normalize_action_linkage(
            value.get("action_linkage")
        )
    for key in (
        "state", "phase", "reason_code", "template_id", "id", "tool",
        "status", "error_category", "error_code", "failed_step_id", "failed_tool",
        "allowed_actions",
    ):
        if value.get(key) is not None:
            item = value.get(key)
            result[key] = (
                [
                    _text(entry)
                    for entry in item[:8]
                    if _text(entry) in LIFECYCLE_ACTIONS
                ]
                if key == "allowed_actions" and isinstance(item, list)
                else _text(item)
            )
    for key in ("attempts", "replacement_step_count"):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool):
            result[key] = max(0, min(item, 128))
    for key in ("plan_quality_before", "plan_quality_after"):
        if isinstance(value.get(key), Mapping):
            result[key] = project_plan_quality_evidence(value[key])
    return result


def _action_event(
    source: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Project one Action Receipt as transition evidence.

    Action Receipt fields such as idempotency keys and source IDs remain out
    of the timeline event.  They belong to the separate Action Receipt
    contract; the timeline only carries stable action semantics plus the
    versioned linkage to the run identities.
    """

    receipt = source.get("action_receipt")
    if not isinstance(receipt, Mapping):
        receipt = result.get("action_receipt")
    if not isinstance(receipt, Mapping):
        return None

    # Keep these imports lazy.  recovery_action and action_identity both sit
    # on the lifecycle/evidence import path used during process startup.
    from .action_identity import (
        normalize_action_receipt_identity_linkage,
        normalize_action_transition_identity,
    )
    from .transition_evidence import normalize_transition_evidence
    from .action_precondition import (
        normalize_action_preconditions,
        project_action_preconditions,
    )
    from .action_lineage import normalize_action_lineage
    from .action_effect import normalize_action_effect
    from .recovery_action import normalize_action_receipt

    normalized = normalize_action_receipt(receipt)
    identity = normalize_action_receipt_identity_linkage(
        normalized.get("identity_linkage")
    )
    if identity is None:
        identity = {
            "schema_version": "spatial-agent.action-receipt-linkage.v1",
            "available": False,
        }
    transition_identity = normalize_action_transition_identity(
        normalized.get("transition_identity")
    )
    transition_evidence = normalize_transition_evidence(
        normalized.get("transition_evidence")
    )
    subject = normalized.get("subject")
    subject = subject if isinstance(subject, Mapping) else {}
    result_ref = normalized.get("result_ref")
    result_ref = result_ref if isinstance(result_ref, Mapping) else {}
    if "preconditions" in normalized:
        preconditions = normalize_action_preconditions(
            normalized.get("preconditions")
        )
    else:
        # Compatibility path for receipts written before M185.  New receipts
        # always carry the canonical projection above.
        preconditions = project_action_preconditions(
            {**source, "result": result},
            action=normalized.get("action_id"),
        )
    return {
        "kind": "action",
        "action_linkage": {
            "schema_version": ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION,
            "available": True,
            "action_id": _text(normalized.get("action_id")) or "unknown",
            "action_kind": _text(normalized.get("action_kind")) or "unknown",
            "status": _text(normalized.get("status")) or "UNKNOWN",
            "subject_kind": _text(subject.get("kind")) or None,
            "result_kind": _text(result_ref.get("kind")) or None,
            "identity_linkage": identity,
            "transition_identity": transition_identity,
            "transition_evidence": transition_evidence,
            "preconditions": preconditions,
            "transition_lineage": normalize_action_lineage(
                normalized.get("transition_lineage")
            ),
            "effect": normalize_action_effect(normalized.get("effect")),
        },
    }


def _normalize_action_linkage(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "schema_version": ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION,
            "available": False,
            "reason_code": "action_timeline_linkage_missing",
        }
    if value.get("schema_version") != ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION:
        return {
            "schema_version": ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION,
            "available": False,
            "reason_code": "action_timeline_linkage_unknown_schema",
        }
    from .action_identity import normalize_action_receipt_identity_linkage
    from .action_identity import normalize_action_transition_identity
    from .transition_evidence import normalize_transition_evidence
    from .action_precondition import normalize_action_preconditions
    from .action_lineage import normalize_action_lineage
    from .action_effect import normalize_action_effect

    identity = normalize_action_receipt_identity_linkage(
        value.get("identity_linkage")
    )
    if identity is None:
        identity = {
            "schema_version": "spatial-agent.action-receipt-linkage.v1",
            "available": False,
        }
    transition_identity = normalize_action_transition_identity(
        value.get("transition_identity")
    )
    transition_evidence = normalize_transition_evidence(
        value.get("transition_evidence")
    )
    result = {
        "schema_version": ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "action_id": _text(value.get("action_id")) or "unknown",
        "action_kind": _text(value.get("action_kind")) or "unknown",
        "status": _text(value.get("status")) or "UNKNOWN",
        "subject_kind": _text(value.get("subject_kind")) or None,
        "result_kind": _text(value.get("result_kind")) or None,
        "identity_linkage": identity,
        "transition_identity": transition_identity,
        "transition_evidence": transition_evidence,
        "preconditions": normalize_action_preconditions(
            value.get("preconditions")
        ),
        "transition_lineage": normalize_action_lineage(
            value.get("transition_lineage")
        ),
        "effect": normalize_action_effect(value.get("effect")),
    }
    return result


def attach_action_receipt_timeline(
    payload: Mapping[str, Any] | None,
    action_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Refresh the bounded timeline after a receipt is completed.

    Action completion happens after the original run result is built.  This
    seam updates the top-level response and its nested result together, so
    Service, Artifact and replay readers do not each reconstruct the event.
    """

    source = dict(payload) if isinstance(payload, Mapping) else {}
    from .recovery_action import normalize_action_receipt

    normalized_receipt = normalize_action_receipt(action_receipt)
    source["action_receipt"] = dict(normalized_receipt)
    if "preconditions" in normalized_receipt:
        from .action_precondition import normalize_action_preconditions

        canonical = normalize_action_preconditions(
            normalized_receipt.get("preconditions")
        )
        source["action_preconditions"] = canonical
    if "effect" in normalized_receipt:
        from .action_effect import normalize_action_effect

        effect = normalize_action_effect(normalized_receipt.get("effect"))
        source["action_effect"] = effect
    nested = source.get("result")
    if isinstance(nested, Mapping):
        nested_result = dict(nested)
        nested_result["action_receipt"] = dict(normalized_receipt)
        if "preconditions" in normalized_receipt:
            nested_result["action_preconditions"] = canonical
        if "effect" in normalized_receipt:
            nested_result["action_effect"] = effect
        source["result"] = nested_result
    timeline = build_execution_timeline(source)
    source["execution_timeline"] = timeline
    if isinstance(source.get("result"), Mapping):
        source["result"] = {
            **source["result"],
            "execution_timeline": timeline,
        }
    return source


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": EXECUTION_TIMELINE_SCHEMA_VERSION,
        "available": False,
        "event_count": 0,
        "events": [],
        "reason_code": _text(reason_code),
    }


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


__all__ = [
    "ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION",
    "EXECUTION_TIMELINE_SCHEMA_VERSION",
    "attach_action_receipt_timeline",
    "build_execution_timeline",
    "normalize_execution_timeline",
]
