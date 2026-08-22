"""Domain-neutral, bounded preconditions for lifecycle actions.

Action lifecycle owns *what* a caller may do.  This module projects *whether
the current evidence is sufficient* for that action.  It is read-only and
does not change Runtime state, dispatch tools, or make a GIS-specific
decision.  Domain Packs may provide explicit conditions; common result and
deployment evidence supplies a conservative fallback.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ACTION_PRECONDITION_SCHEMA_VERSION = "spatial-agent.action-precondition.v1"
_MAX_CONDITIONS = 16
_MAX_TEXT = 96
_GATED_ACTIONS = frozenset(
    {"approve", "confirm", "repair", "retry", "recover", "rebuild_from_result"}
)
_STATES = frozenset({"ready", "degraded", "blocked", "unavailable", "unknown"})


def project_action_preconditions(
    value: Any,
    *,
    action: str | None = None,
) -> dict[str, Any]:
    """Build one safe action-precondition projection.

    Explicit ``action_preconditions.conditions`` are preferred.  When absent,
    already structured deployment, degradation, and evidence-recovery fields
    are summarized without reading datasets or exposing their contents.
    Missing conditions are represented as ``not_observed`` and do not block
    legacy actions; a caller that requires enforcement can set ``enforce`` in
    the explicit projection.
    """

    payload = value if isinstance(value, Mapping) else {}
    result = payload.get("result")
    result = result if isinstance(result, Mapping) else {}
    receipt = payload.get("action_receipt")
    if not isinstance(receipt, Mapping):
        receipt = result.get("action_receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    action_id = _text(action or receipt.get("action_id") or receipt.get("action"))

    # A completed Action Receipt is the canonical source.  This is checked
    # before the result/top-level projections because those projections may
    # have been built before the lifecycle action completed.  Older receipts
    # without this field intentionally continue through the fallback path.
    candidates = [
        receipt.get("preconditions"),
        payload.get("action_preconditions"),
        result.get("action_preconditions"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        if "schema_version" not in candidate:
            continue
        normalized = normalize_action_preconditions(candidate)
        if action_id:
            normalized["action_id"] = action_id
        return normalized

    raw = payload.get("action_preconditions")
    if not isinstance(raw, Mapping):
        raw = result.get("action_preconditions")
    raw = raw if isinstance(raw, Mapping) else {}

    explicit = _explicit_conditions(raw.get("conditions"))
    conditions = explicit or _inferred_conditions(payload, result)
    conditions = conditions[:_MAX_CONDITIONS]
    enforce = raw.get("enforce") is True

    if not conditions:
        return {
            "schema_version": ACTION_PRECONDITION_SCHEMA_VERSION,
            "available": False,
            "action_id": action_id or None,
            "state": "unknown",
            "action_allowed": None,
            "enforcement": "enforced" if enforce else "advisory",
            "reason_code": "action_preconditions_not_observed",
            "condition_count": 0,
            "conditions": [],
        }

    state = _aggregate_state(conditions)
    gate = action_id in _GATED_ACTIONS
    blocking = any(
        item["required"] and item["blocking"] for item in conditions
    )
    action_allowed = not blocking
    if state == "unknown" and enforce and gate:
        action_allowed = False
    reason_code = {
        "ready": "action_preconditions_ready",
        "degraded": "action_preconditions_degraded",
        "blocked": "action_preconditions_blocked",
        "unavailable": "action_preconditions_unavailable",
        "unknown": "action_preconditions_unknown",
    }[state]
    return {
        "schema_version": ACTION_PRECONDITION_SCHEMA_VERSION,
        "available": True,
        "action_id": action_id or None,
        "state": state,
        "action_allowed": action_allowed,
        "enforcement": "enforced" if enforce else "advisory",
        "reason_code": reason_code,
        "condition_count": len(conditions),
        "conditions": conditions,
    }


def normalize_action_preconditions(value: Any) -> dict[str, Any]:
    """Normalize persisted preconditions and degrade unknown versions safely."""

    if not isinstance(value, Mapping):
        return _unavailable("action_preconditions_missing")
    if value.get("schema_version") != ACTION_PRECONDITION_SCHEMA_VERSION:
        return _unavailable("action_preconditions_unknown_schema")
    conditions = _explicit_conditions(value.get("conditions"))[:_MAX_CONDITIONS]
    state = _text(value.get("state"))
    if state not in _STATES:
        state = "unknown"
    action_allowed = value.get("action_allowed")
    if not isinstance(action_allowed, bool):
        action_allowed = None
    return {
        "schema_version": ACTION_PRECONDITION_SCHEMA_VERSION,
        "available": bool(value.get("available")) and bool(conditions),
        "action_id": _text(value.get("action_id")) or None,
        "state": state,
        "action_allowed": action_allowed,
        "enforcement": (
            "enforced"
            if value.get("enforcement") == "enforced"
            else "advisory"
        ),
        "reason_code": _text(value.get("reason_code"))
        or "action_preconditions_unknown",
        "condition_count": len(conditions),
        "conditions": conditions,
    }


def _explicit_conditions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        values = [
            {"id": key, **item}
            for key, item in value.items()
            if isinstance(item, Mapping)
        ]
    elif isinstance(value, list):
        values = value
    else:
        return []
    result = []
    for item in values[:_MAX_CONDITIONS]:
        if not isinstance(item, Mapping):
            continue
        condition_id = _text(item.get("id") or item.get("name"))
        if not condition_id:
            continue
        state = _state(item.get("state") or item.get("status"))
        required = item.get("required") is not False
        blocking = item.get("blocking")
        if not isinstance(blocking, bool):
            blocking = state in {"blocked", "unavailable"}
        normalized = {
            "id": condition_id,
            "state": state,
            "required": required,
            "blocking": blocking,
        }
        for key in ("reason_code", "source", "verification_mode"):
            text = _text(item.get(key))
            if text:
                normalized[key] = text
        result.append(normalized)
    return result


def _inferred_conditions(
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    deployment = result.get("deployment_evidence")
    deployment = deployment if isinstance(deployment, Mapping) else {}
    data = deployment.get("data")
    data = data if isinstance(data, Mapping) else {}
    _append_status(
        conditions,
        "data_readiness",
        data.get("runtime_readiness") or payload.get("data_readiness"),
        "result.deployment_evidence.data.runtime_readiness",
    )

    degradation = result.get("degradation")
    degradation = degradation if isinstance(degradation, Mapping) else {}
    degradation_status = degradation.get("status")
    if degradation_status and degradation_status != "none":
        _append_status(
            conditions,
            "result_degradation",
            degradation_status,
            "result.degradation.status",
        )

    recovery = result.get("evidence_recovery")
    recovery = recovery if isinstance(recovery, Mapping) else {}
    migration = recovery.get("migration")
    migration = migration if isinstance(migration, Mapping) else {}
    _append_status(
        conditions,
        "evidence_migration",
        migration.get("state") or recovery.get("state"),
        "result.evidence_recovery.migration.state",
    )
    return conditions


def _append_status(
    target: list[dict[str, Any]],
    condition_id: str,
    raw: Any,
    source: str,
) -> None:
    if raw is None or str(raw).strip().lower() == "not_observed":
        return
    target.extend(
        _explicit_conditions(
            [{"id": condition_id, "status": raw, "source": source}]
        )
    )


def _aggregate_state(conditions: list[dict[str, Any]]) -> str:
    states = {item["state"] for item in conditions if item["required"]}
    for state in ("blocked", "unavailable", "unknown", "degraded"):
        if state in states:
            return state
    return "ready"


def _state(value: Any) -> str:
    text = _text(value).lower()
    if text in {"ready", "passed", "available", "aligned", "current", "complete"}:
        return "ready"
    if text in {"warning", "degraded", "recoverable", "legacy_incomplete"}:
        return "degraded"
    if text in {"blocked", "not_ready", "failed", "rejected"}:
        return "blocked"
    if text in {"unavailable", "missing", "not_observed"}:
        return "unavailable"
    return "unknown"


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": ACTION_PRECONDITION_SCHEMA_VERSION,
        "available": False,
        "action_id": None,
        "state": "unknown",
        "action_allowed": None,
        "enforcement": "advisory",
        "reason_code": reason_code,
        "condition_count": 0,
        "conditions": [],
    }


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


__all__ = [
    "ACTION_PRECONDITION_SCHEMA_VERSION",
    "normalize_action_preconditions",
    "project_action_preconditions",
]
