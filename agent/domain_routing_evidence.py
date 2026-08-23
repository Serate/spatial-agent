"""Bounded execution evidence derived from Domain routing decisions.

The full routing decision remains owned by the routing ledger.  This module
projects only the immutable identity, bounded lineage and execution binding
needed by Result, async polling, artifacts and restart recovery.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any

from agent.contract_versions import DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION
from agent.domain_selector import DOMAIN_ROUTING_DECISION_SCHEMA_VERSION


_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_LINEAGE = 8
_MAX_CANDIDATES = 8


class DomainRoutingEvidenceError(ValueError):
    """Stable failure raised when execution routing evidence is invalid."""

    def __init__(self, message: str, *, code: str = "domain_routing_evidence_invalid"):
        self.code = str(code or "domain_routing_evidence_invalid")[:64]
        super().__init__(message)


def build_domain_routing_evidence(
    decision: Any,
    *,
    lineage: Sequence[Any] | None = None,
    selector_latency_ms: float | None = None,
) -> dict[str, Any]:
    """Build one self-contained, request-free evidence snapshot for execution."""

    current = _decision_mapping(decision)
    raw_lineage = [_decision_mapping(item) for item in (lineage or (decision,))]
    if not raw_lineage or raw_lineage[-1].get("decision_id") != current.get("decision_id"):
        raw_lineage.append(current)
    truncated = len(raw_lineage) > _MAX_LINEAGE
    raw_lineage = raw_lineage[-_MAX_LINEAGE:]
    if raw_lineage and raw_lineage[0].get("parent_decision_id"):
        truncated = True
    events = [_decision_event(item) for item in raw_lineage]
    selected_domain_id, selection_source = _selection_identity(current)
    candidates = [
        {"domain_id": domain_id}
        for domain_id in _candidate_domain_ids(current)
    ]
    reason_code = _text(current.get("reason_code"), "reason_code")
    observability: dict[str, Any] = {
        "selector_mode": _selector_mode(current.get("selector_id")),
        "candidate_count": len(candidates),
        "fallback_reason": (
            reason_code.split(":", 1)[1][:96]
            if reason_code.startswith("selector_fallback:") and ":" in reason_code
            else None
        ),
        "clarification_required": current.get("status") != "selected",
    }
    latency = _latency(selector_latency_ms)
    if latency is not None:
        observability["selector_latency_ms"] = latency
    value = {
        "schema_version": DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION,
        "available": True,
        "decision": {
            "schema_version": current.get("schema_version"),
            "decision_id": current.get("decision_id"),
            "parent_decision_id": current.get("parent_decision_id"),
            "status": current.get("status"),
            "reason_code": reason_code,
            "selector_id": current.get("selector_id"),
            "request_fingerprint": current.get("request_fingerprint"),
            "selected_domain_id": selected_domain_id,
            "selection_source": selection_source,
        },
        "candidates": candidates,
        "lineage": {
            "root_decision_id": events[0]["decision_id"],
            "current_decision_id": events[-1]["decision_id"],
            "event_count": len(events),
            "truncated": truncated,
            "events": events,
        },
        "binding": {
            "state": "selected",
            "domain_id": selected_domain_id,
            "run_id": None,
        },
        "observability": observability,
    }
    return normalize_domain_routing_evidence(
        value,
        expected_domain_id=selected_domain_id,
        strict=True,
    )


def bind_domain_routing_evidence(
    value: Any,
    *,
    run_id: str,
    domain_id: str,
) -> dict[str, Any]:
    """Bind validated routing evidence to exactly one accepted execution."""

    normalized = normalize_domain_routing_evidence(
        value,
        expected_domain_id=domain_id,
        strict=True,
    )
    run_identity = _identity(run_id, "run_id")
    binding = normalized["binding"]
    existing = binding.get("run_id")
    if existing and existing != run_identity:
        raise DomainRoutingEvidenceError(
            "domain routing evidence belongs to another run",
            code="domain_routing_evidence_run_conflict",
        )
    normalized["binding"] = {
        "state": "execution_bound",
        "domain_id": _identity(domain_id, "domain_id"),
        "run_id": run_identity,
    }
    return normalized


def normalize_domain_routing_evidence(
    value: Any,
    *,
    expected_domain_id: str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Validate current evidence or return an explicit legacy/unavailable view."""

    try:
        return _normalize(value, expected_domain_id=expected_domain_id)
    except DomainRoutingEvidenceError as exc:
        if strict:
            raise
        return unavailable_domain_routing_evidence(exc.code)


def unavailable_domain_routing_evidence(
    reason_code: str = "domain_routing_evidence_missing",
) -> dict[str, Any]:
    return {
        "schema_version": DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION,
        "available": False,
        "reason_code": str(reason_code or "domain_routing_evidence_missing")[:96],
    }


def routing_evidence_identity(value: Any) -> tuple[str, str, str] | None:
    """Return the stable comparison identity used by idempotency and Harness."""

    normalized = normalize_domain_routing_evidence(value)
    if not normalized.get("available"):
        return None
    decision = normalized["decision"]
    return (
        decision["decision_id"],
        decision["request_fingerprint"],
        decision["selected_domain_id"],
    )


def _normalize(value: Any, *, expected_domain_id: str | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainRoutingEvidenceError(
            "domain routing evidence is missing",
            code="domain_routing_evidence_missing",
        )
    if value.get("schema_version") != DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION:
        raise DomainRoutingEvidenceError(
            "domain routing evidence schema is unsupported",
            code="domain_routing_evidence_unknown_schema",
        )
    if value.get("available") is not True:
        raise DomainRoutingEvidenceError("domain routing evidence is unavailable")
    decision = value.get("decision")
    if not isinstance(decision, Mapping):
        raise DomainRoutingEvidenceError("domain routing decision evidence is missing")
    if decision.get("schema_version") != DOMAIN_ROUTING_DECISION_SCHEMA_VERSION:
        raise DomainRoutingEvidenceError(
            "domain routing decision schema is unsupported",
            code="domain_routing_evidence_unknown_decision_schema",
        )
    decision_id = _identity(decision.get("decision_id"), "decision_id")
    parent_id = _optional_identity(decision.get("parent_decision_id"), "parent_decision_id")
    if parent_id == decision_id:
        raise DomainRoutingEvidenceError("domain routing decision cannot parent itself")
    status = _text(decision.get("status"), "status")
    if status != "selected":
        raise DomainRoutingEvidenceError(
            "only selected routing evidence can execute",
            code="domain_routing_evidence_not_selected",
        )
    selector_id = _identity(decision.get("selector_id"), "selector_id")
    fingerprint = str(decision.get("request_fingerprint") or "")
    if not _HEX_RE.fullmatch(fingerprint):
        raise DomainRoutingEvidenceError("request_fingerprint must be lowercase SHA-256")
    selected_domain_id = _identity(
        decision.get("selected_domain_id"), "selected_domain_id"
    )
    selection_source = _identity(
        decision.get("selection_source"), "selection_source"
    )
    if expected_domain_id and selected_domain_id != _identity(expected_domain_id, "domain_id"):
        raise DomainRoutingEvidenceError(
            "domain routing evidence selected another domain",
            code="domain_routing_evidence_domain_mismatch",
        )

    raw_candidates = value.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) > _MAX_CANDIDATES:
        raise DomainRoutingEvidenceError("domain routing candidates are invalid")
    candidates = []
    for item in raw_candidates:
        if not isinstance(item, Mapping):
            raise DomainRoutingEvidenceError("domain routing candidate is invalid")
        candidates.append({"domain_id": _identity(item.get("domain_id"), "candidate.domain_id")})
    candidate_domain_ids = [item["domain_id"] for item in candidates]
    if len(candidate_domain_ids) != len(set(candidate_domain_ids)):
        raise DomainRoutingEvidenceError("domain routing candidates contain duplicates")
    if selected_domain_id not in candidate_domain_ids:
        raise DomainRoutingEvidenceError(
            "selected domain is absent from routing candidates",
            code="domain_routing_evidence_domain_mismatch",
        )

    raw_lineage = value.get("lineage")
    if not isinstance(raw_lineage, Mapping):
        raise DomainRoutingEvidenceError("domain routing lineage is missing")
    raw_events = raw_lineage.get("events")
    if not isinstance(raw_events, list) or not raw_events or len(raw_events) > _MAX_LINEAGE:
        raise DomainRoutingEvidenceError(
            "domain routing lineage is invalid",
            code="domain_routing_evidence_invalid_lineage",
        )
    events = [_normalize_event(item) for item in raw_events]
    for prior, current in zip(events, events[1:]):
        if current.get("parent_decision_id") != prior["decision_id"]:
            raise DomainRoutingEvidenceError(
                "domain routing lineage is discontinuous",
                code="domain_routing_evidence_invalid_lineage",
            )
    if events[-1]["decision_id"] != decision_id:
        raise DomainRoutingEvidenceError(
            "domain routing lineage does not end at current decision",
            code="domain_routing_evidence_invalid_lineage",
        )
    current_event = events[-1]
    if (
        current_event["status"] != status
        or current_event["reason_code"] != _text(decision.get("reason_code"), "reason_code")
        or current_event["selector_id"] != selector_id
        or current_event["selected_domain_id"] != selected_domain_id
        or current_event["selection_source"] != selection_source
    ):
        raise DomainRoutingEvidenceError(
            "domain routing lineage current event is inconsistent",
            code="domain_routing_evidence_invalid_lineage",
        )
    root_id = _identity(raw_lineage.get("root_decision_id"), "root_decision_id")
    current_id = _identity(raw_lineage.get("current_decision_id"), "current_decision_id")
    if root_id != events[0]["decision_id"] or current_id != decision_id:
        raise DomainRoutingEvidenceError(
            "domain routing lineage identity is inconsistent",
            code="domain_routing_evidence_invalid_lineage",
        )
    declared_count = raw_lineage.get("event_count")
    if isinstance(declared_count, bool) or declared_count != len(events):
        raise DomainRoutingEvidenceError(
            "domain routing lineage count is inconsistent",
            code="domain_routing_evidence_invalid_lineage",
        )

    raw_binding = value.get("binding")
    if not isinstance(raw_binding, Mapping):
        raise DomainRoutingEvidenceError("domain routing binding is missing")
    binding_state = _text(raw_binding.get("state"), "binding.state")
    if binding_state not in {"selected", "execution_bound"}:
        raise DomainRoutingEvidenceError("domain routing binding state is invalid")
    binding_domain = _identity(raw_binding.get("domain_id"), "binding.domain_id")
    if binding_domain != selected_domain_id:
        raise DomainRoutingEvidenceError(
            "domain routing binding selected another domain",
            code="domain_routing_evidence_domain_mismatch",
        )
    binding_run = _optional_identity(raw_binding.get("run_id"), "binding.run_id")
    if (binding_state == "execution_bound") != bool(binding_run):
        raise DomainRoutingEvidenceError("domain routing run binding is invalid")

    raw_observation = value.get("observability")
    if not isinstance(raw_observation, Mapping):
        raise DomainRoutingEvidenceError("domain routing observability is missing")
    candidate_count = raw_observation.get("candidate_count")
    if isinstance(candidate_count, bool) or not isinstance(candidate_count, int):
        raise DomainRoutingEvidenceError("domain routing candidate_count is invalid")
    if candidate_count != len(candidates):
        raise DomainRoutingEvidenceError("domain routing candidate_count is inconsistent")
    observability: dict[str, Any] = {
        "selector_mode": _identity(raw_observation.get("selector_mode"), "selector_mode"),
        "candidate_count": max(0, min(candidate_count, _MAX_CANDIDATES)),
        "fallback_reason": (
            _text(raw_observation.get("fallback_reason"), "fallback_reason")
            if raw_observation.get("fallback_reason")
            else None
        ),
        "clarification_required": bool(raw_observation.get("clarification_required")),
    }
    latency = _latency(raw_observation.get("selector_latency_ms"))
    if latency is not None:
        observability["selector_latency_ms"] = latency
    return {
        "schema_version": DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION,
        "available": True,
        "decision": {
            "schema_version": DOMAIN_ROUTING_DECISION_SCHEMA_VERSION,
            "decision_id": decision_id,
            "parent_decision_id": parent_id,
            "status": status,
            "reason_code": _text(decision.get("reason_code"), "reason_code"),
            "selector_id": selector_id,
            "request_fingerprint": fingerprint,
            "selected_domain_id": selected_domain_id,
            "selection_source": selection_source,
        },
        "candidates": candidates,
        "lineage": {
            "root_decision_id": root_id,
            "current_decision_id": current_id,
            "event_count": len(events),
            "truncated": bool(raw_lineage.get("truncated")),
            "events": events,
        },
        "binding": {
            "state": binding_state,
            "domain_id": binding_domain,
            "run_id": binding_run,
        },
        "observability": observability,
    }


def _decision_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    serializer = getattr(value, "to_dict", None)
    if callable(serializer):
        result = serializer()
        if isinstance(result, Mapping):
            return result
    raise DomainRoutingEvidenceError("domain routing decision must be an object")


def _decision_event(value: Mapping[str, Any]) -> dict[str, Any]:
    selected_domain_id, selection_source = _selection_identity(value, required=False)
    return {
        "decision_id": _identity(value.get("decision_id"), "decision_id"),
        "parent_decision_id": _optional_identity(
            value.get("parent_decision_id"), "parent_decision_id"
        ),
        "status": _text(value.get("status"), "status"),
        "reason_code": _text(value.get("reason_code"), "reason_code"),
        "selector_id": _identity(value.get("selector_id"), "selector_id"),
        "candidate_domain_ids": _candidate_domain_ids(value),
        "selected_domain_id": selected_domain_id,
        "selection_source": selection_source,
    }


def _normalize_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainRoutingEvidenceError("domain routing lineage event is invalid")
    status = _text(value.get("status"), "lineage.status")
    if status not in {"selected", "ambiguous", "unmatched"}:
        raise DomainRoutingEvidenceError("domain routing lineage status is invalid")
    domains = value.get("candidate_domain_ids")
    if not isinstance(domains, list) or len(domains) > _MAX_CANDIDATES:
        raise DomainRoutingEvidenceError("domain routing lineage candidates are invalid")
    selected = _optional_identity(value.get("selected_domain_id"), "selected_domain_id")
    source = _optional_identity(value.get("selection_source"), "selection_source")
    if status == "selected" and (not selected or not source):
        raise DomainRoutingEvidenceError("selected routing lineage event lacks selection")
    if status != "selected" and (selected or source):
        raise DomainRoutingEvidenceError("unselected routing lineage event has selection")
    return {
        "decision_id": _identity(value.get("decision_id"), "decision_id"),
        "parent_decision_id": _optional_identity(
            value.get("parent_decision_id"), "parent_decision_id"
        ),
        "status": status,
        "reason_code": _text(value.get("reason_code"), "reason_code"),
        "selector_id": _identity(value.get("selector_id"), "selector_id"),
        "candidate_domain_ids": [
            _identity(item, "candidate_domain_id") for item in domains
        ],
        "selected_domain_id": selected,
        "selection_source": source,
    }


def _selection_identity(
    value: Mapping[str, Any], *, required: bool = True
) -> tuple[str | None, str | None]:
    selection = value.get("selection")
    if not isinstance(selection, Mapping):
        if required:
            raise DomainRoutingEvidenceError(
                "selected routing decision lacks a selection",
                code="domain_routing_evidence_not_selected",
            )
        return None, None
    domain_id = selection.get("domain_id")
    source = selection.get("source")
    if not domain_id or not source:
        if required:
            raise DomainRoutingEvidenceError("routing selection identity is incomplete")
        return None, None
    return _identity(domain_id, "domain_id"), _identity(source, "selection_source")


def _candidate_domain_ids(value: Mapping[str, Any]) -> list[str]:
    raw = value.get("candidates")
    if not isinstance(raw, (list, tuple)):
        raise DomainRoutingEvidenceError("domain routing candidates are invalid")
    result = []
    for item in list(raw)[:_MAX_CANDIDATES]:
        if not isinstance(item, Mapping):
            raise DomainRoutingEvidenceError("domain routing candidate is invalid")
        domain_id = _identity(item.get("domain_id"), "candidate.domain_id")
        if domain_id not in result:
            result.append(domain_id)
    return result


def _selector_mode(value: Any) -> str:
    selector_id = _identity(value, "selector_id")
    return selector_id.split(".", 1)[0][:32]


def _identity(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _IDENTITY_RE.fullmatch(text):
        raise DomainRoutingEvidenceError(field + " must be a bounded identity")
    return text


def _optional_identity(value: Any, field: str) -> str | None:
    return None if value in (None, "") else _identity(value, field)


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 128 or any(ord(char) < 32 for char in text):
        raise DomainRoutingEvidenceError(field + " must be bounded text")
    return text


def _latency(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DomainRoutingEvidenceError("selector latency is invalid") from exc
    if not math.isfinite(number) or number < 0:
        raise DomainRoutingEvidenceError("selector latency is invalid")
    return round(min(number, 86_400_000.0), 3)


__all__ = [
    "DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION",
    "DomainRoutingEvidenceError",
    "bind_domain_routing_evidence",
    "build_domain_routing_evidence",
    "normalize_domain_routing_evidence",
    "routing_evidence_identity",
    "unavailable_domain_routing_evidence",
]
