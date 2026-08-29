"""Human approval contract for validated tool proposals.

The approval record is deliberately smaller than a proposal.  It contains
identity and validation fingerprints, never source code, example arguments,
prompts, or model output.  A separate volatile publisher may later bind an
approved record to a controlled Registry handler.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import threading
import time
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
import sqlite3
from typing import Any, Protocol


TOOL_APPROVAL_SCHEMA_VERSION = "spatial-agent.tool-approval.v1"
TOOL_APPROVAL_DECISION_SCHEMA_VERSION = "spatial-agent.tool-approval-decision.v1"
TOOL_APPROVAL_VISIBILITY_SCHEMA_VERSION = "spatial-agent.tool-approval-visibility.v1"
TOOL_APPROVAL_STATES = frozenset(
    {"pending", "approved", "rejected", "expired", "revoked", "invalid"}
)
TOOL_APPROVAL_ACTIONS = frozenset({"approve", "reject", "revoke"})

_MAX_TEXT = 160
_MAX_HISTORY = 8


class ToolApprovalError(ValueError):
    """A stable, fail-closed approval lifecycle error."""

    def __init__(self, message: str, *, code: str = "tool_approval_invalid") -> None:
        super().__init__(message)
        self.code = str(code)[:96]


@dataclass(frozen=True)
class ToolApprovalRecord:
    """Versioned, bounded approval state for one validated proposal."""

    schema_version: str
    approval_id: str
    proposal_id: str | None
    tool_name: str | None
    domain_id: str
    receipt_fingerprint: str
    source_hash: str | None
    schema_hash: str | None
    proposal_version: int
    status: str
    version: int
    created_at: float
    updated_at: float
    expires_at: float | None
    reason_code: str | None
    # The waiting run is part of the approval identity boundary.  It is safe
    # to expose as an opaque identifier and lets a later decision resume only
    # the run that created this proposal.
    run_id: str | None = None
    definition: dict[str, Any] | None = None
    decision_receipts: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_receipt(
        cls,
        receipt: Any,
        *,
        domain_id: str,
        run_id: str | None = None,
        expires_at: float | None = None,
        now: float | None = None,
    ) -> "ToolApprovalRecord":
        """Create a pending approval from the safe M322 receipt projection."""

        timestamp = _now(now)
        normalized_domain = _required_text(domain_id, "domain_id")
        safe = _safe_receipt(receipt)
        fingerprint = receipt_fingerprint(safe)
        proposal_id = _optional_text(safe.get("proposal_id"))
        tool_name = _optional_text(safe.get("name"))
        source_hash = _optional_text(safe.get("source_hash"))
        schema_hash = _optional_text(safe.get("schema_hash"))
        definition = _safe_definition(safe.get("definition"))
        valid = (
            safe.get("schema_version") == "spatial-agent.tool-proposal-receipt.v1"
            and safe.get("status") == "validated"
            and bool(proposal_id)
            and bool(tool_name)
            and bool(source_hash)
            and bool(schema_hash)
            and bool(definition)
        )
        identity = json.dumps(
            {"domain_id": normalized_domain, "fingerprint": fingerprint},
            sort_keys=True,
            separators=(",", ":"),
        )
        approval_id = "approval-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        bounded_expiry = _optional_timestamp(expires_at)
        bounded_run_id = _optional_text(run_id)
        return cls(
            schema_version=TOOL_APPROVAL_SCHEMA_VERSION,
            approval_id=approval_id,
            proposal_id=proposal_id,
            tool_name=tool_name,
            domain_id=normalized_domain,
            receipt_fingerprint=fingerprint,
            source_hash=source_hash,
            schema_hash=schema_hash,
            proposal_version=1,
            status="pending" if valid else "invalid",
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
            expires_at=bounded_expiry,
            reason_code=None if valid else "approval_receipt_invalid",
            run_id=bounded_run_id,
            definition=definition,
            decision_receipts=(),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the public approval record; no proposal source crosses it."""

        _validate_record(self)
        value: dict[str, Any] = {
            "schema_version": TOOL_APPROVAL_SCHEMA_VERSION,
            "approval_id": self.approval_id,
            "proposal_id": self.proposal_id,
            "name": self.tool_name,
            "domain_id": self.domain_id,
            "receipt_fingerprint": self.receipt_fingerprint,
            "source_hash": self.source_hash,
            "schema_hash": self.schema_hash,
            "proposal_version": self.proposal_version,
            "status": self.status,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "reason_code": self.reason_code,
            "run_id": self.run_id,
            "allowed_actions": list(self.allowed_actions()),
        }
        if self.definition:
            value["definition"] = _safe_definition(self.definition)
        if self.decision_receipts:
            value["decision_receipt"] = dict(self.decision_receipts[-1])
            value["decision_history"] = [dict(item) for item in self.decision_receipts]
        return value

    def allowed_actions(self) -> tuple[str, ...]:
        if self.status == "pending":
            return ("approve", "reject")
        if self.status == "approved":
            return ("revoke",)
        return ()

    def transition(
        self,
        action: str,
        *,
        actor_id: str = "admin",
        expected_version: int | None = None,
        expected_fingerprint: str | None = None,
        now: float | None = None,
    ) -> "ToolApprovalRecord":
        """Apply one guarded transition and append a bounded decision receipt."""

        current = self.expire(now=now)
        _check_preconditions(current, expected_version, expected_fingerprint)
        normalized = _normalize_action(action)
        idempotent_status = {
            "approve": "approved",
            "reject": "rejected",
            "revoke": "revoked",
        }[normalized]
        if current.status == idempotent_status:
            return current
        next_status = {
            ("pending", "approve"): "approved",
            ("pending", "reject"): "rejected",
            ("approved", "revoke"): "revoked",
        }.get((current.status, normalized))
        if next_status is None:
            raise ToolApprovalError(
                "approval action is not allowed for state: " + current.status,
                code="tool_approval_action_not_allowed",
            )
        timestamp = _now(now)
        receipt = _decision_receipt(
            current,
            action=normalized,
            next_status=next_status,
            actor_id=actor_id,
            expected_version=expected_version,
            timestamp=timestamp,
        )
        history = (*current.decision_receipts, receipt)[-_MAX_HISTORY:]
        return replace(
            current,
            status=next_status,
            version=current.version + 1,
            updated_at=timestamp,
            reason_code="approval_" + next_status,
            decision_receipts=history,
        )

    def expire(self, *, now: float | None = None) -> "ToolApprovalRecord":
        """Return an expired record without creating a second expiry receipt."""

        timestamp = _now(now)
        if self.status != "pending" or self.expires_at is None or self.expires_at > timestamp:
            return self
        receipt = _decision_receipt(
            self,
            action="expire",
            next_status="expired",
            actor_id="system",
            expected_version=self.version,
            timestamp=timestamp,
        )
        return replace(
            self,
            status="expired",
            version=self.version + 1,
            updated_at=timestamp,
            reason_code="approval_expired",
            decision_receipts=(*self.decision_receipts, receipt)[-_MAX_HISTORY:],
        )


def project_tool_approval_visibility(
    record: Any, *, recovery: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return the bounded approval projection intended for the Console.

    The compatibility ``as_dict`` representation may include a bounded tool
    definition. This narrower contract omits that definition and all
    proposal-private fields so UI code cannot accidentally render them.
    """

    value = record.as_dict() if callable(getattr(record, "as_dict", None)) else record
    if not isinstance(value, Mapping):
        raise ToolApprovalError(
            "approval record is invalid", code="tool_approval_record_invalid"
        )
    allowed = value.get("allowed_actions")
    actions = [str(item)[:32] for item in allowed] if isinstance(allowed, list) else []
    recovery_value = recovery if isinstance(recovery, Mapping) else {}
    return {
        "schema_version": TOOL_APPROVAL_VISIBILITY_SCHEMA_VERSION,
        "approval_id": str(value.get("approval_id") or "")[:96],
        "name": str(value.get("name") or "")[:96],
        "domain_id": str(value.get("domain_id") or "")[:80],
        "status": str(value.get("status") or "invalid")[:32],
        "version": _bounded_public_int(value.get("version")),
        "updated_at": _bounded_public_float(value.get("updated_at")),
        "expires_at": _bounded_public_float(value.get("expires_at"), nullable=True),
        "reason_code": str(value.get("reason_code") or "")[:96],
        "receipt_fingerprint": str(value.get("receipt_fingerprint") or "")[:128],
        "run_id": str(value.get("run_id") or "")[:160] or None,
        "allowed_actions": actions[:4],
        "recovery": {
            "state": str(recovery_value.get("state") or "not_loaded")[:32],
            "reason_code": str(recovery_value.get("reason_code") or "")[:96],
        },
    }


class ToolApprovalStore(Protocol):
    def create_from_receipt(
        self,
        receipt: Mapping[str, Any],
        *,
        domain_id: str,
        run_id: str | None = None,
        expires_at: float | None = None,
    ) -> ToolApprovalRecord: ...

    def get(self, approval_id: str, *, domain_id: str) -> ToolApprovalRecord | None: ...

    def list(
        self, *, domain_id: str, limit: int = 50, status: str | None = None
    ) -> list[ToolApprovalRecord]: ...

    def resolve(
        self,
        approval_id: str,
        *,
        action: str,
        domain_id: str,
        actor_id: str = "admin",
        expected_version: int | None = None,
        expected_fingerprint: str | None = None,
    ) -> ToolApprovalRecord: ...


class InMemoryToolApprovalStore:
    """Thread-safe approval adapter for local mode and compact tests."""

    def __init__(self) -> None:
        self._records: dict[str, ToolApprovalRecord] = {}
        self._lock = threading.RLock()

    def create_from_receipt(
        self,
        receipt: Mapping[str, Any],
        *,
        domain_id: str,
        run_id: str | None = None,
        expires_at: float | None = None,
    ) -> ToolApprovalRecord:
        record = ToolApprovalRecord.from_receipt(
            receipt, domain_id=domain_id, run_id=run_id, expires_at=expires_at
        )
        with self._lock:
            existing = self._records.get(record.approval_id)
            if existing is not None:
                if existing.receipt_fingerprint != record.receipt_fingerprint:
                    raise ToolApprovalError(
                        "approval identity fingerprint mismatch",
                        code="tool_approval_fingerprint_mismatch",
                    )
                if record.run_id and existing.run_id and record.run_id != existing.run_id:
                    raise ToolApprovalError(
                        "approval run identity mismatch",
                        code="tool_approval_run_mismatch",
                    )
                return existing.expire()
            self._records[record.approval_id] = record
            return record

    def get(self, approval_id: str, *, domain_id: str) -> ToolApprovalRecord | None:
        with self._lock:
            record = self._records.get(str(approval_id))
            if record is None or record.domain_id != str(domain_id):
                return None
            expired = record.expire()
            if expired != record:
                self._records[record.approval_id] = expired
            return expired

    def list(
        self, *, domain_id: str, limit: int = 50, status: str | None = None
    ) -> list[ToolApprovalRecord]:
        count = _limit(limit)
        normalized_status = _optional_status(status)
        with self._lock:
            records = [
                self.get(record.approval_id, domain_id=domain_id)
                for record in self._records.values()
                if record.domain_id == str(domain_id)
            ]
            records = [item for item in records if item is not None]
        if normalized_status:
            records = [item for item in records if item.status == normalized_status]
        return sorted(records, key=lambda item: item.updated_at, reverse=True)[:count]

    def resolve(
        self,
        approval_id: str,
        *,
        action: str,
        domain_id: str,
        actor_id: str = "admin",
        expected_version: int | None = None,
        expected_fingerprint: str | None = None,
    ) -> ToolApprovalRecord:
        with self._lock:
            record = self.get(approval_id, domain_id=domain_id)
            if record is None:
                raise ToolApprovalError("approval not found", code="tool_approval_not_found")
            updated = record.transition(
                action,
                actor_id=actor_id,
                expected_version=expected_version,
                expected_fingerprint=expected_fingerprint,
            )
            self._records[record.approval_id] = updated
            return updated


class SQLiteToolApprovalStore:
    """SQLite adapter with optimistic version fencing and restart recovery."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_approvals (
                    approval_id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tool_approvals_domain_status "
                "ON tool_approvals(domain_id, status, updated_at)"
            )

    def create_from_receipt(
        self,
        receipt: Mapping[str, Any],
        *,
        domain_id: str,
        run_id: str | None = None,
        expires_at: float | None = None,
    ) -> ToolApprovalRecord:
        record = ToolApprovalRecord.from_receipt(
            receipt, domain_id=domain_id, run_id=run_id, expires_at=expires_at
        )
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT payload FROM tool_approvals WHERE approval_id = ?",
                (record.approval_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO tool_approvals "
                    "(approval_id, domain_id, status, version, payload, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record.approval_id,
                        record.domain_id,
                        record.status,
                        record.version,
                        _encode(record),
                        record.updated_at,
                    ),
                )
                return record
            restored = _record_from_payload(existing[0])
            if restored.domain_id != record.domain_id or restored.receipt_fingerprint != record.receipt_fingerprint:
                raise ToolApprovalError(
                    "approval identity fingerprint mismatch",
                    code="tool_approval_fingerprint_mismatch",
                )
            if record.run_id and restored.run_id and record.run_id != restored.run_id:
                raise ToolApprovalError(
                    "approval run identity mismatch",
                    code="tool_approval_run_mismatch",
                )
        return self.get(record.approval_id, domain_id=domain_id) or record

    def get(self, approval_id: str, *, domain_id: str) -> ToolApprovalRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM tool_approvals WHERE approval_id = ? AND domain_id = ?",
                (str(approval_id), str(domain_id)),
            ).fetchone()
        if row is None:
            return None
        record = _record_from_payload(row[0])
        expired = record.expire()
        if expired == record:
            return record
        self._cas_update(record, expired)
        return expired

    def list(
        self, *, domain_id: str, limit: int = 50, status: str | None = None
    ) -> list[ToolApprovalRecord]:
        count = _limit(limit)
        normalized_status = _optional_status(status)
        if normalized_status == "expired":
            # A pending row may have crossed its deadline since the last
            # read. Include it so the loop below can persist the transition
            # before applying the requested status filter.
            clause = " AND (status = ? OR status = 'pending')"
            parameters: tuple[Any, ...] = (str(domain_id), normalized_status, count)
        elif normalized_status:
            clause = " AND status = ?"
            parameters = (str(domain_id), normalized_status, count)
        else:
            clause = ""
            parameters = (str(domain_id), count)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM tool_approvals WHERE domain_id = ?" + clause
                + " ORDER BY updated_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        records = []
        for row in rows:
            record = _record_from_payload(row[0])
            expired = record.expire()
            if expired != record:
                self._cas_update(record, expired)
                record = expired
            if not normalized_status or record.status == normalized_status:
                records.append(record)
        return records[:count]

    def resolve(
        self,
        approval_id: str,
        *,
        action: str,
        domain_id: str,
        actor_id: str = "admin",
        expected_version: int | None = None,
        expected_fingerprint: str | None = None,
    ) -> ToolApprovalRecord:
        record = self.get(approval_id, domain_id=domain_id)
        if record is None:
            raise ToolApprovalError("approval not found", code="tool_approval_not_found")
        updated = record.transition(
            action,
            actor_id=actor_id,
            expected_version=expected_version,
            expected_fingerprint=expected_fingerprint,
        )
        if updated == record:
            return record
        self._cas_update(record, updated)
        return updated

    def _cas_update(self, old: ToolApprovalRecord, new: ToolApprovalRecord) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tool_approvals
                   SET status = ?, version = ?, payload = ?, updated_at = ?
                 WHERE approval_id = ? AND domain_id = ? AND status = ? AND version = ?
                """,
                (
                    new.status,
                    new.version,
                    _encode(new),
                    new.updated_at,
                    old.approval_id,
                    old.domain_id,
                    old.status,
                    old.version,
                ),
            )
            if cursor.rowcount != 1:
                raise ToolApprovalError(
                    "approval version mismatch", code="tool_approval_version_mismatch"
                )

    def _connection(self):
        connection = sqlite3.connect(str(self._path), timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        return _ConnectionContext(connection)


class _ConnectionContext:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        return self.connection

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()


def receipt_fingerprint(receipt: Any) -> str:
    """Hash only the bounded M322 receipt identity fields."""

    safe = _safe_receipt(receipt)
    identity = {
        key: safe.get(key)
        for key in (
            "schema_version",
            "proposal_id",
            "name",
            "status",
            "source_hash",
            "schema_hash",
            "checks",
            "sandbox_profile",
        )
    }
    payload = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_receipt(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "schema_version",
        "proposal_id",
        "name",
        "status",
        "source_hash",
        "schema_hash",
        "checks",
        "sandbox_profile",
        "definition",
    ):
        value = receipt.get(key)
        if key in {"checks", "sandbox_profile"} and isinstance(value, Mapping):
            result[key] = {
                str(item)[:48]: str(item_value)[:96]
                for item, item_value in list(value.items())[:12]
            }
        elif key == "definition":
            projected = _safe_definition(value)
            if projected:
                result[key] = projected
        elif value is not None:
            result[key] = str(value)[:_MAX_TEXT]
    return result


def _safe_definition(value: Any) -> dict[str, Any] | None:
    """Keep only bounded Registry metadata from a proposal receipt."""

    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {
        "name": str(value.get("name") or "")[:96],
        "description": str(value.get("description") or "")[:400],
        "input_schema": value.get("input_schema")
        if isinstance(value.get("input_schema"), Mapping)
        else {"type": "object"},
        "output_schema": value.get("output_schema")
        if isinstance(value.get("output_schema"), Mapping)
        else {"type": "object"},
        "dynamic": True,
        "requires_approval": True,
        "side_effect": str(value.get("side_effect") or "unknown")[:32],
        "handler_ref": str(value.get("handler_ref") or "")[:160] or None,
    }
    if not result["name"]:
        return None
    try:
        encoded = json.dumps(result, ensure_ascii=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    return result if len(encoded.encode("utf-8")) <= 24 * 1024 else None


def _decision_receipt(
    record: ToolApprovalRecord,
    *,
    action: str,
    next_status: str,
    actor_id: str,
    expected_version: int | None,
    timestamp: float,
) -> dict[str, Any]:
    return {
        "schema_version": TOOL_APPROVAL_DECISION_SCHEMA_VERSION,
        "decision_id": "approval-decision-" + uuid.uuid4().hex[:24],
        "approval_id": record.approval_id,
        "proposal_id": record.proposal_id,
        "action": action,
        "from_status": record.status,
        "to_status": next_status,
        "actor_id": _bounded_actor(actor_id),
        "expected_version": expected_version,
        "version": record.version + 1,
        "receipt_fingerprint": record.receipt_fingerprint,
        "created_at": timestamp,
        "reason_code": "approval_" + next_status,
    }


def _check_preconditions(
    record: ToolApprovalRecord,
    expected_version: int | None,
    expected_fingerprint: str | None,
) -> None:
    if expected_version is None and not expected_fingerprint:
        raise ToolApprovalError(
            "approval precondition requires expected_version or receipt fingerprint",
            code="tool_approval_precondition_required",
        )
    if expected_version is not None:
        if isinstance(expected_version, bool) or not isinstance(expected_version, int):
            raise ToolApprovalError(
                "approval expected_version must be an integer",
                code="tool_approval_version_invalid",
            )
        if expected_version != record.version:
            raise ToolApprovalError(
                "approval version mismatch", code="tool_approval_version_mismatch"
            )
    if expected_fingerprint and str(expected_fingerprint) != record.receipt_fingerprint:
        raise ToolApprovalError(
            "approval receipt fingerprint mismatch",
            code="tool_approval_fingerprint_mismatch",
        )


def _normalize_action(action: Any) -> str:
    value = str(action or "").strip().lower()[:32]
    value = {"accept": "approve", "confirm": "approve", "deny": "reject"}.get(value, value)
    if value not in TOOL_APPROVAL_ACTIONS:
        raise ToolApprovalError(
            "unsupported approval action", code="tool_approval_action_unknown"
        )
    return value


def _validate_record(record: ToolApprovalRecord) -> None:
    if record.schema_version != TOOL_APPROVAL_SCHEMA_VERSION:
        raise ToolApprovalError("approval schema is unsupported", code="tool_approval_schema_invalid")
    if not record.approval_id or not record.domain_id or not record.receipt_fingerprint:
        raise ToolApprovalError("approval identity is incomplete", code="tool_approval_record_invalid")
    if record.status not in TOOL_APPROVAL_STATES:
        raise ToolApprovalError("approval status is unsupported", code="tool_approval_record_invalid")
    if not isinstance(record.version, int) or record.version < 1:
        raise ToolApprovalError("approval version is invalid", code="tool_approval_record_invalid")
    if len(record.decision_receipts) > _MAX_HISTORY:
        raise ToolApprovalError("approval decision history is too large", code="tool_approval_record_invalid")


def _record_from_payload(value: Any) -> ToolApprovalRecord:
    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ToolApprovalError("approval payload is invalid", code="tool_approval_record_invalid") from exc
    if not isinstance(data, Mapping):
        raise ToolApprovalError("approval payload is invalid", code="tool_approval_record_invalid")
    raw_history = data.get("decision_history") or []
    history = tuple(dict(item) for item in raw_history[:_MAX_HISTORY] if isinstance(item, Mapping))
    record = ToolApprovalRecord(
        schema_version=str(data.get("schema_version") or ""),
        approval_id=str(data.get("approval_id") or ""),
        proposal_id=_optional_text(data.get("proposal_id")),
        tool_name=_optional_text(data.get("name")),
        domain_id=str(data.get("domain_id") or "")[:_MAX_TEXT],
        receipt_fingerprint=str(data.get("receipt_fingerprint") or "")[:160],
        source_hash=_optional_text(data.get("source_hash")),
        schema_hash=_optional_text(data.get("schema_hash")),
        proposal_version=int(data.get("proposal_version") or 1),
        status=str(data.get("status") or ""),
        version=int(data.get("version") or 1),
        created_at=float(data.get("created_at") or 0),
        updated_at=float(data.get("updated_at") or 0),
        expires_at=_optional_timestamp(data.get("expires_at")),
        reason_code=_optional_text(data.get("reason_code")),
        run_id=_optional_text(data.get("run_id")),
        definition=_safe_definition(data.get("definition")),
        decision_receipts=history,
    )
    _validate_record(record)
    return record


def _encode(record: ToolApprovalRecord) -> str:
    return json.dumps(record.as_dict(), ensure_ascii=True, separators=(",", ":"))


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()[:_MAX_TEXT]
    if not text:
        raise ToolApprovalError(field + " is required", code="tool_approval_request_invalid")
    return text


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()[:_MAX_TEXT]
    return text or None


def _bounded_actor(value: Any) -> str:
    return _required_text(value or "admin", "actor_id")


def _optional_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    return timestamp if timestamp == timestamp and timestamp > 0 else None


def _bounded_public_int(value: Any) -> int:
    try:
        return max(0, min(2**31 - 1, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _bounded_public_float(value: Any, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None if nullable else 0.0
    if result != result or result in {float("inf"), float("-inf")}:
        return None if nullable else 0.0
    return result


def _now(value: float | None) -> float:
    return float(value) if value is not None else time.time()


def _limit(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 50
    return max(1, min(count, 100))


def _optional_status(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    status = str(value).strip().lower()
    if status not in TOOL_APPROVAL_STATES:
        raise ToolApprovalError("approval status is unsupported", code="tool_approval_status_invalid")
    return status


__all__ = [
    "TOOL_APPROVAL_ACTIONS",
    "TOOL_APPROVAL_DECISION_SCHEMA_VERSION",
    "TOOL_APPROVAL_SCHEMA_VERSION",
    "TOOL_APPROVAL_STATES",
    "TOOL_APPROVAL_VISIBILITY_SCHEMA_VERSION",
    "InMemoryToolApprovalStore",
    "SQLiteToolApprovalStore",
    "ToolApprovalError",
    "ToolApprovalRecord",
    "ToolApprovalStore",
    "project_tool_approval_visibility",
    "receipt_fingerprint",
]
