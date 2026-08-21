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
    events = events[:_MAX_EVENTS]
    return {
        "schema_version": EXECUTION_TIMELINE_SCHEMA_VERSION,
        "available": bool(events),
        "event_count": len(events),
        "events": events,
    }


def normalize_execution_timeline(value: Any) -> dict[str, Any]:
    """Validate a persisted timeline and degrade unknown shapes safely."""

    if not isinstance(value, Mapping):
        return _unavailable("execution_timeline_missing")
    if value.get("schema_version") != EXECUTION_TIMELINE_SCHEMA_VERSION:
        return _unavailable("execution_timeline_unknown_schema")
    events = value.get("events")
    if not isinstance(events, list):
        return _unavailable("execution_timeline_events_invalid")
    safe_events = [event for event in events[:_MAX_EVENTS] if isinstance(event, Mapping)]
    return {
        "schema_version": EXECUTION_TIMELINE_SCHEMA_VERSION,
        "available": bool(value.get("available")) and bool(safe_events),
        "event_count": len(safe_events),
        "events": [_normalize_event(event) for event in safe_events],
    }


def _normalize_event(value: Mapping[str, Any]) -> dict[str, Any]:
    kind = _text(value.get("kind")) or "unknown"
    result = {"kind": kind}
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
    "EXECUTION_TIMELINE_SCHEMA_VERSION",
    "build_execution_timeline",
    "normalize_execution_timeline",
]
