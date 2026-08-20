"""Versioned, domain-neutral metadata for evidence projections.

The payload of runtime/release evidence remains owned by a Domain Pack. This
Module only adds the small, stable envelope that callers need to identify the
kind, owner and status of that projection without understanding GIS fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Protocol


DOMAIN_EVIDENCE_SCHEMA_VERSION = "spatial-agent.domain-evidence.v1"
EVIDENCE_KINDS = frozenset({"runtime", "release"})


class EvidenceProvider(Protocol):
    """Minimal provider seam owned by a Domain Pack."""

    domain_id: str

    def snapshot(
        self,
        kind: str,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Return one bounded runtime or release evidence projection."""


def attach_evidence_contract(
    value: Mapping[str, Any],
    *,
    domain_id: str,
    kind: str,
) -> dict[str, Any]:
    """Return a bounded flat projection plus a versioned evidence contract."""
    normalized_kind = str(kind or "unknown")[:24]
    if normalized_kind not in EVIDENCE_KINDS:
        raise ValueError("unsupported evidence kind: " + normalized_kind)
    payload = dict(value)
    existing = payload.get("evidence_contract")
    if isinstance(existing, Mapping):
        contract = dict(existing)
    else:
        contract = {}
    status = _status_for(payload, normalized_kind)
    updated_at = (
        payload.get("updated_at")
        or payload.get("generated_at")
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    payload["evidence_contract"] = {
        "schema_version": DOMAIN_EVIDENCE_SCHEMA_VERSION,
        "kind": normalized_kind,
        "domain_id": str(domain_id or "unknown")[:80],
        "status": str(contract.get("status") or status)[:32],
        "updated_at": str(contract.get("updated_at") or updated_at)[:64],
    }
    return payload


def _status_for(payload: Mapping[str, Any], kind: str) -> str:
    if kind == "runtime":
        return str(
            payload.get("health_status")
            or payload.get("data_readiness")
            or "unknown"
        )[:32]
    return str(payload.get("status") or payload.get("data_readiness") or "unknown")[:32]


__all__ = [
    "DOMAIN_EVIDENCE_SCHEMA_VERSION",
    "EVIDENCE_KINDS",
    "EvidenceProvider",
    "attach_evidence_contract",
]
