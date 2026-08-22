"""Domain-neutral decision lifecycle contract for controlled Agent runs.

The Runtime may still auto-execute by default.  When a caller asks for a
decision boundary, this module gives preview, HTTP, async and Console one
small seam for representing approval, rejection, clarification and recovery.
It intentionally contains no Planner, Domain or transport knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterable, Mapping, Protocol

from .recovery_action import normalize_action_ids, project_available_actions


DECISION_LIFECYCLE_SCHEMA_VERSION = "spatial-agent.decision-lifecycle.v1"

DECISION_STATES = frozenset(
    {
        "not_required",
        "awaiting_confirmation",
        "approved",
        "rejected",
        "clarification_required",
        "repairable",
        "recoverable",
        "executing",
        "completed",
        "failed",
    }
)

DECISION_ACTIONS = frozenset(
    {"approve", "reject", "clarify", "repair", "retry", "recover"}
)

_TRANSITIONS = {
    "awaiting_confirmation": {"approve": "approved", "reject": "rejected"},
    "clarification_required": {"clarify": "clarification_required"},
    "repairable": {"repair": "approved", "reject": "rejected"},
    "recoverable": {"retry": "executing", "recover": "executing"},
}

DECISION_STATUSES = frozenset(
    {"PENDING", "ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED", "CONSUMED"}
)


class DecisionLifecycleError(ValueError):
    """Raised when a decision cannot be applied to the current state."""

    def __init__(self, message: str, *, code: str = "decision_invalid") -> None:
        super().__init__(message)
        self.code = str(code)[:96]


@dataclass(frozen=True)
class DecisionRequest:
    """The bounded input needed to resume one paused subject."""

    subject_kind: str
    subject_id: str
    domain_id: str
    session_id: str | None
    decision_kind: str
    prompt: str
    options: tuple[str, ...]
    subject_fingerprint: str
    input_data: Mapping[str, Any] | None = None
    expires_at: float | None = None


@dataclass(frozen=True)
class DecisionRecord:
    """Durable decision state with optimistic-concurrency versioning."""

    schema_version: str
    decision_id: str
    subject_kind: str
    subject_id: str
    domain_id: str
    session_id: str | None
    decision_kind: str
    status: str
    prompt: str
    options: tuple[str, ...]
    selected_choice: str | None
    input_data: Mapping[str, Any] | None
    subject_fingerprint: str
    version: int
    created_at: float
    resolved_at: float | None = None
    expires_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "subject": {"kind": self.subject_kind, "id": self.subject_id},
            "domain_id": self.domain_id,
            "session_id": self.session_id,
            "decision_kind": self.decision_kind,
            "status": self.status,
            "prompt": self.prompt,
            "options": list(self.options),
            "selected_choice": self.selected_choice,
            "subject_fingerprint": self.subject_fingerprint,
            "version": self.version,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "expires_at": self.expires_at,
        }
        if self.input_data:
            value["input_data"] = _bound_value(self.input_data)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DecisionRecord":
        if not isinstance(value, Mapping):
            raise DecisionLifecycleError(
                "decision record must be an object", code="decision_record_invalid"
            )
        subject = value.get("subject") if isinstance(value.get("subject"), Mapping) else {}
        return cls(
            str(value.get("schema_version") or DECISION_LIFECYCLE_SCHEMA_VERSION),
            str(value.get("decision_id") or ""),
            str(subject.get("kind") or ""),
            str(subject.get("id") or ""),
            str(value.get("domain_id") or ""),
            value.get("session_id"),
            str(value.get("decision_kind") or ""),
            str(value.get("status") or ""),
            str(value.get("prompt") or "")[:320],
            tuple(str(item)[:32] for item in (value.get("options") or [])[:8]),
            value.get("selected_choice"),
            value.get("input_data") if isinstance(value.get("input_data"), Mapping) else None,
            str(value.get("subject_fingerprint") or "")[:160],
            int(value.get("version") or 1),
            float(value.get("created_at") or 0),
            value.get("resolved_at"),
            value.get("expires_at"),
        )

    def evidence(self) -> dict[str, Any]:
        state = {
            "PENDING": "awaiting_confirmation",
            "ACCEPTED": "approved",
            "REJECTED": "rejected",
            "CANCELLED": "rejected",
            "EXPIRED": "rejected",
            "CONSUMED": "completed",
        }.get(self.status, "failed")
        value = build_decision_evidence(
            state,
            allowed_actions=(
                ("approve", "reject")
                if self.status == "PENDING"
                else ()
            ),
            reason_code="decision_" + self.status.lower(),
            plan_fingerprint=self.subject_fingerprint,
            run_id=self.subject_id if self.subject_kind == "run" else None,
        )
        value.update(
            {
                "decision_id": self.decision_id,
                "status": self.status,
                "version": self.version,
                "decision_kind": self.decision_kind,
            }
        )
        return value


class DecisionStore(Protocol):
    def create(self, request: DecisionRequest) -> DecisionRecord: ...

    def get(self, decision_id: str, *, domain_id: str) -> DecisionRecord | None: ...

    def resolve(
        self,
        decision_id: str,
        *,
        choice: str,
        expected_version: int | None = None,
        domain_id: str,
    ) -> DecisionRecord: ...

    def consume(
        self, decision_id: str, *, expected_version: int, domain_id: str
    ) -> DecisionRecord: ...


class InMemoryDecisionStore:
    """Small reference adapter used by memory services and contract tests."""

    def __init__(self) -> None:
        self._records: dict[str, DecisionRecord] = {}
        self._lock = threading.RLock()

    def create(self, request: DecisionRequest) -> DecisionRecord:
        _validate_request(request)
        now = time.time()
        record = DecisionRecord(
            DECISION_LIFECYCLE_SCHEMA_VERSION,
            "decision-" + uuid.uuid4().hex,
            request.subject_kind,
            request.subject_id,
            request.domain_id,
            request.session_id,
            request.decision_kind,
            "PENDING",
            request.prompt[:320],
            tuple(request.options[:8]),
            None,
            _bound_value(request.input_data) if request.input_data else None,
            request.subject_fingerprint[:160],
            1,
            now,
            None,
            request.expires_at,
        )
        with self._lock:
            self._records[record.decision_id] = record
        return record

    def restore(self, record: DecisionRecord) -> DecisionRecord:
        """Restore a bounded artifact record for artifact-only recovery."""
        if not isinstance(record, DecisionRecord):
            raise DecisionLifecycleError(
                "decision record is invalid", code="decision_record_invalid"
            )
        _validate_record(record)
        with self._lock:
            self._records[record.decision_id] = record
        return record

    def get(self, decision_id: str, *, domain_id: str) -> DecisionRecord | None:
        with self._lock:
            record = self._records.get(str(decision_id))
        if record is None or record.domain_id != str(domain_id):
            return None
        return self._expire(record)

    def resolve(
        self,
        decision_id: str,
        *,
        choice: str,
        expected_version: int | None = None,
        domain_id: str,
    ) -> DecisionRecord:
        with self._lock:
            record = self._require(decision_id, domain_id)
            record = self._expire(record)
            if record.status != "PENDING":
                raise DecisionLifecycleError(
                    "decision is not pending", code="decision_not_pending"
                )
            if expected_version is not None and record.version != expected_version:
                raise DecisionLifecycleError(
                    "decision version mismatch", code="decision_version_mismatch"
                )
            normalized = str(choice or "").strip().lower()[:32]
            aliases = {"accept": "approve", "confirm": "approve", "deny": "reject"}
            normalized = aliases.get(normalized, normalized)
            if normalized not in {"approve", "reject"}:
                raise DecisionLifecycleError(
                    "unsupported decision choice", code="decision_choice_unknown"
                )
            status = "ACCEPTED" if normalized == "approve" else "REJECTED"
            updated = DecisionRecord(
                **{
                    **record.__dict__,
                    "status": status,
                    "selected_choice": normalized,
                    "version": record.version + 1,
                    "resolved_at": time.time(),
                }
            )
            self._records[decision_id] = updated
            return updated

    def consume(
        self, decision_id: str, *, expected_version: int, domain_id: str
    ) -> DecisionRecord:
        with self._lock:
            record = self._require(decision_id, domain_id)
            if record.status != "ACCEPTED":
                raise DecisionLifecycleError(
                    "only an accepted decision can be consumed",
                    code="decision_not_accepted",
                )
            if record.version != expected_version:
                raise DecisionLifecycleError(
                    "decision version mismatch", code="decision_version_mismatch"
                )
            updated = DecisionRecord(
                **{
                    **record.__dict__,
                    "status": "CONSUMED",
                    "version": record.version + 1,
                    "resolved_at": time.time(),
                }
            )
            self._records[decision_id] = updated
            return updated

    def _require(self, decision_id: str, domain_id: str) -> DecisionRecord:
        record = self._records.get(str(decision_id))
        if record is None or record.domain_id != str(domain_id):
            raise DecisionLifecycleError("decision not found", code="decision_not_found")
        return record

    def _expire(self, record: DecisionRecord) -> DecisionRecord:
        if record.status == "PENDING":
            expires_at = record.expires_at
            if expires_at and float(expires_at) <= time.time():
                record = DecisionRecord(
                    **{**record.__dict__, "status": "EXPIRED", "version": record.version + 1}
                )
                self._records[record.decision_id] = record
        return record


class SQLiteDecisionStore:
    """Persistent adapter with CAS resolution and Domain filtering."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_decisions (
                    decision_id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def restore(self, record: DecisionRecord) -> DecisionRecord:
        """Restore an artifact decision without overwriting a newer record.

        Artifact-only recovery can start with a fresh SQLite database.  The
        decision must be reinserted before resolve/consume can use the normal
        CAS path; a stale artifact must never replace an existing decision.
        """
        if not isinstance(record, DecisionRecord):
            raise DecisionLifecycleError(
                "decision record is invalid", code="decision_record_invalid"
            )
        _validate_record(record)
        payload = json.dumps(record.as_dict(), ensure_ascii=True)
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT domain_id FROM agent_decisions WHERE decision_id = ?",
                (record.decision_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != record.domain_id:
                    raise DecisionLifecycleError(
                        "decision belongs to another domain",
                        code="decision_domain_mismatch",
                    )
            else:
                connection.execute(
                    "INSERT INTO agent_decisions VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record.decision_id,
                        record.domain_id,
                        record.status,
                        record.version,
                        payload,
                        time.time(),
                    ),
                )
        restored = self.get(record.decision_id, domain_id=record.domain_id)
        if restored is None:
            raise DecisionLifecycleError(
                "decision restore failed", code="decision_restore_failed"
            )
        return restored

    def create(self, request: DecisionRequest) -> DecisionRecord:
        _validate_request(request)
        now = time.time()
        record = DecisionRecord(
            DECISION_LIFECYCLE_SCHEMA_VERSION,
            "decision-" + uuid.uuid4().hex,
            request.subject_kind,
            request.subject_id,
            request.domain_id,
            request.session_id,
            request.decision_kind,
            "PENDING",
            request.prompt[:320],
            tuple(request.options[:8]),
            None,
            _bound_value(request.input_data) if request.input_data else None,
            request.subject_fingerprint[:160],
            1,
            now,
            None,
            request.expires_at,
        )
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO agent_decisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.decision_id,
                    record.domain_id,
                    record.status,
                    record.version,
                    json.dumps(record.as_dict(), ensure_ascii=True),
                    now,
                ),
            )
        return record

    def get(self, decision_id: str, *, domain_id: str) -> DecisionRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM agent_decisions WHERE decision_id = ? AND domain_id = ?",
                (str(decision_id), str(domain_id)),
            ).fetchone()
        record = self._from_payload(row[0]) if row else None
        if record is None or record.status != "PENDING":
            return record
        if record.expires_at is None or float(record.expires_at) > time.time():
            return record
        expired = _updated_record(record, status="EXPIRED")
        try:
            self._cas_update(record, expired)
            return expired
        except DecisionLifecycleError:
            # Another worker may have resolved it while this reader noticed
            # the expiry. Return the latest CAS winner rather than masking it.
            return self._require(decision_id, domain_id)

    def resolve(
        self,
        decision_id: str,
        *,
        choice: str,
        expected_version: int | None = None,
        domain_id: str,
    ) -> DecisionRecord:
        record = self._require(decision_id, domain_id)
        _assert_pending(record, expected_version)
        normalized = _normalize_choice(choice)
        updated = _updated_record(
            record,
            status="ACCEPTED" if normalized == "approve" else "REJECTED",
            selected_choice=normalized,
        )
        self._cas_update(record, updated)
        return updated

    def consume(
        self, decision_id: str, *, expected_version: int, domain_id: str
    ) -> DecisionRecord:
        record = self._require(decision_id, domain_id)
        if record.status != "ACCEPTED":
            raise DecisionLifecycleError(
                "only an accepted decision can be consumed",
                code="decision_not_accepted",
            )
        if record.version != expected_version:
            raise DecisionLifecycleError(
                "decision version mismatch", code="decision_version_mismatch"
            )
        updated = _updated_record(record, status="CONSUMED")
        self._cas_update(record, updated)
        return updated

    def _require(self, decision_id: str, domain_id: str) -> DecisionRecord:
        record = self.get(decision_id, domain_id=domain_id)
        if record is None:
            raise DecisionLifecycleError("decision not found", code="decision_not_found")
        return record

    def _cas_update(self, old: DecisionRecord, new: DecisionRecord) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_decisions
                   SET status = ?, version = ?, payload = ?, updated_at = ?
                 WHERE decision_id = ? AND domain_id = ?
                   AND status = ? AND version = ?
                """,
                (
                    new.status,
                    new.version,
                    json.dumps(new.as_dict(), ensure_ascii=True),
                    time.time(),
                    old.decision_id,
                    old.domain_id,
                    old.status,
                    old.version,
                ),
            )
            if cursor.rowcount != 1:
                raise DecisionLifecycleError(
                    "decision version mismatch", code="decision_version_mismatch"
                )

    @staticmethod
    def _from_payload(value: str) -> DecisionRecord:
        data = json.loads(value)
        subject = data.get("subject") if isinstance(data.get("subject"), Mapping) else {}
        return DecisionRecord(
            data.get("schema_version", DECISION_LIFECYCLE_SCHEMA_VERSION),
            str(data.get("decision_id") or ""),
            str(subject.get("kind") or ""),
            str(subject.get("id") or ""),
            str(data.get("domain_id") or ""),
            data.get("session_id"),
            str(data.get("decision_kind") or ""),
            str(data.get("status") or ""),
            str(data.get("prompt") or "")[:320],
            tuple(str(item)[:32] for item in data.get("options", [])[:8]),
            data.get("selected_choice"),
            data.get("input_data"),
            str(data.get("subject_fingerprint") or "")[:160],
            int(data.get("version") or 1),
            float(data.get("created_at") or 0),
            data.get("resolved_at"),
            data.get("expires_at"),
        )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(str(self._path), timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


@dataclass(frozen=True)
class DecisionLifecycle:
    """Bounded, transport-neutral state and allowed actions for one decision."""

    state: str
    allowed_actions: tuple[str, ...] = ()
    reason_code: str | None = None
    plan_fingerprint: str | None = None
    run_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": DECISION_LIFECYCLE_SCHEMA_VERSION,
            "state": self.state,
            "allowed_actions": list(self.allowed_actions),
            "actions": project_available_actions(
                self.allowed_actions, subject_id=self.run_id
            ),
        }
        for key, item in (
            ("reason_code", self.reason_code),
            ("plan_fingerprint", self.plan_fingerprint),
            ("run_id", self.run_id),
        ):
            if item:
                value[key] = str(item)[:160]
        return value


def build_decision_evidence(
    state: str,
    *,
    allowed_actions: Iterable[str] = (),
    reason_code: str | None = None,
    plan_fingerprint: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build a validated and bounded lifecycle projection."""

    normalized_state = _state(state)
    actions = _actions(allowed_actions)
    invalid = [item for item in actions if item not in DECISION_ACTIONS]
    if invalid:
        raise DecisionLifecycleError(
            "unknown decision action: " + invalid[0],
            code="decision_action_unknown",
        )
    expected = {
        item
        for item in DECISION_ACTIONS
        if item in _TRANSITIONS.get(normalized_state, {})
    }
    if set(actions) - expected:
        raise DecisionLifecycleError(
            "decision action is not allowed for state: " + normalized_state,
            code="decision_action_not_allowed",
        )
    return DecisionLifecycle(
        normalized_state,
        actions,
        _safe_token(reason_code),
        _safe_token(plan_fingerprint),
        _safe_token(run_id),
    ).as_dict()


def transition_decision(
    current: Mapping[str, Any], action: str
) -> dict[str, Any]:
    """Apply one explicit action and return the next lifecycle evidence."""

    if not isinstance(current, Mapping):
        raise DecisionLifecycleError("decision evidence must be an object")
    if current.get("schema_version") != DECISION_LIFECYCLE_SCHEMA_VERSION:
        raise DecisionLifecycleError(
            "unknown decision lifecycle schema",
            code="decision_schema_unknown",
        )
    state = _state(current.get("state"))
    normalized_action = _safe_token(action)
    if normalized_action not in _TRANSITIONS.get(state, {}):
        raise DecisionLifecycleError(
            "decision action is not allowed for state: " + state,
            code="decision_action_not_allowed",
        )
    next_state = _TRANSITIONS[state][normalized_action]
    return build_decision_evidence(
        next_state,
        reason_code="action_" + normalized_action,
        plan_fingerprint=current.get("plan_fingerprint"),
        run_id=current.get("run_id"),
    )


def _state(value: Any) -> str:
    state = str(value or "")[:64]
    if state not in DECISION_STATES:
        raise DecisionLifecycleError(
            "unknown decision state: " + state,
            code="decision_state_unknown",
        )
    return state


def _actions(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(normalize_action_ids(values, allowed=DECISION_ACTIONS)[:8])


def _safe_token(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:160] if text else None


def _validate_request(request: DecisionRequest) -> None:
    for name in ("subject_kind", "subject_id", "domain_id", "decision_kind", "prompt"):
        if not str(getattr(request, name, "") or "").strip():
            raise DecisionLifecycleError(
                "decision request field is missing: " + name,
                code="decision_request_invalid",
            )
    if not request.options:
        raise DecisionLifecycleError(
            "decision request options are empty", code="decision_request_invalid"
        )
    if not request.subject_fingerprint:
        raise DecisionLifecycleError(
            "decision subject fingerprint is missing",
            code="decision_request_invalid",
        )


def _validate_record(record: DecisionRecord) -> None:
    if not record.decision_id or not record.subject_id or not record.domain_id:
        raise DecisionLifecycleError(
            "decision record identity is incomplete", code="decision_record_invalid"
        )
    if record.status not in DECISION_STATUSES:
        raise DecisionLifecycleError(
            "unknown decision record status", code="decision_record_invalid"
        )
    if not record.subject_fingerprint:
        raise DecisionLifecycleError(
            "decision record fingerprint is missing", code="decision_record_invalid"
        )


def _assert_pending(record: DecisionRecord, expected_version: int | None) -> None:
    if record.status != "PENDING":
        raise DecisionLifecycleError(
            "decision is not pending", code="decision_not_pending"
        )
    if expected_version is not None and record.version != expected_version:
        raise DecisionLifecycleError(
            "decision version mismatch", code="decision_version_mismatch"
        )


def _normalize_choice(choice: Any) -> str:
    normalized = str(choice or "").strip().lower()[:32]
    normalized = {
        "accept": "approve",
        "confirm": "approve",
        "deny": "reject",
    }.get(normalized, normalized)
    if normalized not in {"approve", "reject"}:
        raise DecisionLifecycleError(
            "unsupported decision choice", code="decision_choice_unknown"
        )
    return normalized


def _updated_record(record: DecisionRecord, *, status: str, selected_choice: Any = None) -> DecisionRecord:
    return DecisionRecord(
        **{
            **record.__dict__,
            "status": status,
            "selected_choice": selected_choice
            if selected_choice is not None
            else record.selected_choice,
            "version": record.version + 1,
            "resolved_at": time.time(),
        }
    )


def _bound_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if isinstance(value, Mapping):
        return {
            str(key)[:64]: _bound_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
        }
    if isinstance(value, (list, tuple)):
        return [_bound_value(item, depth=depth + 1) for item in list(value)[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:240]
    return str(value)[:240]


__all__ = [
    "DECISION_ACTIONS",
    "DECISION_LIFECYCLE_SCHEMA_VERSION",
    "DECISION_STATES",
    "DecisionLifecycle",
    "DecisionLifecycleError",
    "DecisionRecord",
    "DecisionRequest",
    "DecisionStore",
    "InMemoryDecisionStore",
    "SQLiteDecisionStore",
    "build_decision_evidence",
    "transition_decision",
]
