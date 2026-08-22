"""Domain-neutral identity linkage for Action Receipt evidence.

An Action Receipt describes a lifecycle transition.  Request, plan, result,
and evidence identities describe the run that the transition operated on.
Those concerns must remain separate, but a receipt still needs a bounded
linkage so Service, async polling, Artifact, history, and recovery can prove
which run contract the action belongs to.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contract_versions import RESULT_ENVELOPE_SCHEMA_VERSION
from .evidence_projection import EVIDENCE_PROJECTION_SCHEMA_VERSION, project_evidence_projection
from .plan_identity import normalize_plan_identity
from .request_identity import normalize_request_identity


ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION = "spatial-agent.action-receipt-linkage.v1"
_MAX_TEXT = 96


def build_action_receipt_identity_linkage(value: Any) -> dict[str, Any]:
    """Build a bounded linkage from a run/result-shaped payload.

    This function only copies already-versioned identities.  It never hashes
    an incomplete action response, because doing so would create a plausible
    but false request identity for failures or cancellation responses that do
    not carry a result envelope.
    """

    payload = value if isinstance(value, Mapping) else {}
    envelope = payload.get("result")
    envelope = envelope if isinstance(envelope, Mapping) else payload
    planning = envelope.get("planning")
    if not isinstance(planning, Mapping):
        planning = payload.get("plan_evidence")
    planning = planning if isinstance(planning, Mapping) else {}

    request_identity = normalize_request_identity(
        envelope.get("request_identity") or payload.get("request_identity")
    )
    plan_identity = normalize_plan_identity(
        planning.get("plan_identity")
        or envelope.get("plan_identity")
        or payload.get("plan_identity")
    )

    result_identity = None
    if isinstance(envelope, Mapping) and (
        envelope.get("schema_version") or envelope.get("type")
    ):
        result_identity = {
            "schema_version": _text(
                envelope.get("schema_version"), RESULT_ENVELOPE_SCHEMA_VERSION
            ),
            "type": _text(envelope.get("type") or payload.get("result_type"), "unknown"),
        }

    evidence = project_evidence_projection(payload)
    registry = evidence.get("evidence_registry")
    completeness = evidence.get("evidence_registry_completeness")
    migration = evidence.get("migration")
    evidence_identity = {
        "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
        "registry_schema_version": _optional_text(
            registry.get("schema_version") if isinstance(registry, Mapping) else None
        ),
        "completeness_schema_version": _optional_text(
            completeness.get("schema_version")
            if isinstance(completeness, Mapping)
            else None
        ),
        "completeness_state": _optional_text(
            completeness.get("state") if isinstance(completeness, Mapping) else None
        ),
        "migration_state": _optional_text(
            migration.get("state") if isinstance(migration, Mapping) else None
        ),
    }

    available = bool(
        request_identity
        or plan_identity
        or result_identity
        or evidence.get("available")
    )
    return {
        "schema_version": ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION,
        "available": available,
        "request_identity": request_identity,
        "plan_identity": plan_identity,
        "result_identity": result_identity,
        "evidence_identity": evidence_identity,
    }


def normalize_action_receipt_identity_linkage(value: Any) -> dict[str, Any] | None:
    """Normalize persisted linkage and reject unknown versions safely."""

    if not isinstance(value, Mapping):
        return None
    if value.get("schema_version") != ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION:
        return None

    request_identity = normalize_request_identity(value.get("request_identity"))
    plan_identity = normalize_plan_identity(value.get("plan_identity"))
    raw_result = value.get("result_identity")
    result_identity = None
    if isinstance(raw_result, Mapping):
        if raw_result.get("schema_version") != RESULT_ENVELOPE_SCHEMA_VERSION:
            raw_result = None
    if isinstance(raw_result, Mapping):
        result_identity = {
            "schema_version": RESULT_ENVELOPE_SCHEMA_VERSION,
            "type": _text(raw_result.get("type"), "unknown"),
        }

    raw_evidence = value.get("evidence_identity")
    evidence = raw_evidence if isinstance(raw_evidence, Mapping) else {}
    evidence_identity = {
        "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
        "registry_schema_version": _optional_text(
            evidence.get("registry_schema_version")
        ),
        "completeness_schema_version": _optional_text(
            evidence.get("completeness_schema_version")
        ),
        "completeness_state": _optional_text(evidence.get("completeness_state")),
        "migration_state": _optional_text(evidence.get("migration_state")),
    }
    return {
        "schema_version": ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "request_identity": request_identity,
        "plan_identity": plan_identity,
        "result_identity": result_identity,
        "evidence_identity": evidence_identity,
    }


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return (text or fallback)[:_MAX_TEXT]


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:_MAX_TEXT] if text else None


__all__ = [
    "ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION",
    "build_action_receipt_identity_linkage",
    "normalize_action_receipt_identity_linkage",
]
