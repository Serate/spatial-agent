"""SQLite-backed conversation store for the production demo.

Split out of ``sqlite_store``.  Depends only on ``sqlite_common`` (acyclic).
Re-exported by ``sqlite_store`` for compatibility.
"""

"""SQLite-backed state and conversation stores for the production demo."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..errors import PersistenceError
from .sqlite_retry import (
    is_sqlite_contention as _is_sqlite_contention,
    retry_sqlite_write as _retry_sqlite_write,
)
from ..models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from ..conversation_turn import normalize_conversation_turn
from ..domain_registry import DomainRegistry, DomainSelectionError, domain_registry
from ..domain_selector import resolve_domain_routing_decision
from ..runtime_context import normalize_runtime_context
from ..runtime_state import PendingClarification
from ..evidence_registry import normalize_evidence_registry
from ..recovery_action import normalize_action_receipt
from ..execution_timeline import normalize_execution_timeline
from ..nested_schema import normalize_domain_routing_evidence_contract
from ..interaction_contract import InteractionContractError
from ..run_events import normalize_run_event, validate_event_cursor, validate_event_limit
from ..request_mode import normalize_request_mode
from .sqlite_common import _connect_sqlite, _ROUTING_INTERACTION_RECEIPT_SELECT, _routing_interaction_receipt_from_row


class SQLiteConversationStore:
    """Persist pending clarification and last completed request by session."""

    def __init__(
        self,
        path: str = "outputs/spatial-agent.db",
        *,
        domain_id: str = "gis",
        legacy_domain_id: str = "gis",
        routing_registry: Optional[DomainRegistry] = None,
    ):
        self._path = Path(path)
        self._domain_id = self._bounded_domain(domain_id, "domain_id")
        self._legacy_domain_id = self._bounded_domain(
            legacy_domain_id, "legacy_domain_id"
        )
        self._routing_registry = routing_registry or domain_registry()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _bounded_domain(value: str, field: str) -> str:
        normalized = str(value or "").strip()
        if not normalized or len(normalized) > 80:
            raise ValueError(field + " must be a non-empty bounded value")
        return normalized

    def _session_binding(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        *,
        create: bool,
    ) -> bool:
        row = connection.execute(
            "SELECT domain_id FROM session_domains WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            if not create:
                return False
            connection.execute(
                "INSERT INTO session_domains (session_id, domain_id) VALUES (?, ?)",
                (session_id, self._domain_id),
            )
            return True
        if str(row[0]) != self._domain_id:
            raise DomainSelectionError(
                "session belongs to another domain: " + session_id,
                code="session_domain_mismatch",
            )
        return True

    def get_bound_session_domain(self, session_id: str) -> Optional[str]:
        """Read an existing session binding without creating or changing it."""

        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT domain_id FROM session_domains WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def get_pending(self, session_id: str) -> Optional[PendingClarification]:
        with self._connection() as connection:
            if not self._session_binding(connection, session_id, create=False):
                return None
            row = connection.execute(
                "SELECT request, error FROM pending_clarifications WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return PendingClarification(request=row[0], error=row[1]) if row else None

    @_retry_sqlite_write
    def ensure_session(self, session_id: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        with self._connection() as connection:
            self._session_binding(connection, session_id, create=True)
            row = connection.execute(
                "SELECT session_id, display_name FROM conversation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE conversation_sessions SET updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                    (session_id,),
                )
                return {"session_id": row[0], "display_name": row[1]}
            if not display_name:
                count = connection.execute(
                    "SELECT COUNT(*) FROM conversation_sessions WHERE session_id LIKE 'conversation-%'"
                ).fetchone()[0]
                display_name = f"对话{count + 1}"
            connection.execute(
                "INSERT INTO conversation_sessions (session_id, display_name, created_at, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (session_id, display_name),
            )
        return {"session_id": session_id, "display_name": display_name}

    @_retry_sqlite_write
    def create_session(self) -> Dict[str, Any]:
        with self._connection() as connection:
            count = connection.execute(
                """
                SELECT COUNT(*)
                  FROM conversation_sessions AS sessions
                  JOIN session_domains AS domains
                    ON domains.session_id = sessions.session_id
                 WHERE sessions.session_id LIKE 'conversation-%'
                   AND domains.domain_id = ?
                """,
                (self._domain_id,),
            ).fetchone()[0]
            number = count + 1
            session_id = f"conversation-{number}"
            while connection.execute(
                "SELECT 1 FROM conversation_sessions WHERE session_id = ?", (session_id,)
            ).fetchone():
                number += 1
                session_id = f"conversation-{number}"
            display_name = f"对话{number}"
            connection.execute(
                "INSERT INTO conversation_sessions (session_id, display_name, created_at, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (session_id, display_name),
            )
            connection.execute(
                "INSERT INTO session_domains (session_id, domain_id) VALUES (?, ?)",
                (session_id, self._domain_id),
            )
        return {"session_id": session_id, "display_name": display_name}

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT sessions.session_id, sessions.display_name,
                       sessions.created_at, sessions.updated_at
                  FROM conversation_sessions AS sessions
                  JOIN session_domains AS domains
                    ON domains.session_id = sessions.session_id
                 WHERE sessions.session_id LIKE 'conversation-%'
                   AND domains.domain_id = ?
                 ORDER BY sessions.updated_at DESC, sessions.created_at ASC
                 LIMIT ?
                """,
                (self._domain_id, limit),
            ).fetchall()
        return [
            {"session_id": row[0], "display_name": row[1], "created_at": row[2], "updated_at": row[3]}
            for row in rows
        ]

    @_retry_sqlite_write
    def save_pending(self, session_id: str, request: str, error: str) -> None:
        self.ensure_session(session_id)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO pending_clarifications (session_id, request, error)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET request=excluded.request, error=excluded.error
                """,
                (session_id, request, error),
            )

    @_retry_sqlite_write
    def clear_pending(self, session_id: str) -> None:
        with self._connection() as connection:
            if not self._session_binding(connection, session_id, create=False):
                return
            connection.execute(
                "DELETE FROM pending_clarifications WHERE session_id = ?", (session_id,)
            )

    @_retry_sqlite_write
    def clear_session(self, session_id: str) -> None:
        with self._connection() as connection:
            binding = connection.execute(
                "SELECT domain_id FROM session_domains WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if binding is None:
                connection.execute(
                    "DELETE FROM domain_routing_interaction_receipts "
                    "WHERE subject_decision_id IN ("
                    "SELECT decision_id FROM domain_routing_decisions WHERE session_id = ?)",
                    (session_id,),
                )
                connection.execute(
                    "DELETE FROM domain_routing_decisions WHERE session_id = ?",
                    (session_id,),
                )
                return
            if str(binding[0]) != self._domain_id:
                raise DomainSelectionError(
                    "session belongs to another domain: " + session_id,
                    code="session_domain_mismatch",
                )
            connection.execute("DELETE FROM pending_clarifications WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM completed_sessions WHERE session_id = ?", (session_id,))
            connection.execute(
                "DELETE FROM domain_routing_interaction_receipts "
                "WHERE subject_decision_id IN ("
                "SELECT decision_id FROM domain_routing_decisions WHERE session_id = ?)",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM domain_routing_decisions WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "UPDATE conversation_sessions SET updated_at=CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,),
            )

    @_retry_sqlite_write
    def delete_session(self, session_id: str) -> bool:
        with self._connection() as connection:
            binding = connection.execute(
                "SELECT domain_id FROM session_domains WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if binding is not None and str(binding[0]) != self._domain_id:
                raise DomainSelectionError(
                    "session belongs to another domain: " + session_id,
                    code="session_domain_mismatch",
                )
            session_exists = connection.execute(
                "SELECT 1 FROM conversation_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            routing_exists = connection.execute(
                "SELECT 1 FROM domain_routing_decisions WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
            connection.execute("DELETE FROM pending_clarifications WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM completed_sessions WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM memory_facts WHERE session_id = ?", (session_id,))
            connection.execute(
                "DELETE FROM domain_routing_interaction_receipts "
                "WHERE subject_decision_id IN ("
                "SELECT decision_id FROM domain_routing_decisions WHERE session_id = ?)",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM domain_routing_decisions WHERE session_id = ?",
                (session_id,),
            )
            connection.execute("DELETE FROM conversation_sessions WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM session_domains WHERE session_id = ?", (session_id,))
        return bool(session_exists or routing_exists)

    @_retry_sqlite_write
    def save_completed(self, session_id: str, request: str) -> None:
        self.ensure_session(session_id)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO completed_sessions (session_id, request)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE SET request=excluded.request
                """,
                (session_id, request),
            )

    def get_last_request(self, session_id: str) -> Optional[str]:
        with self._connection() as connection:
            if not self._session_binding(connection, session_id, create=False):
                return None
            row = connection.execute(
                "SELECT request FROM completed_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row[0] if row else None

    @_retry_sqlite_write
    def save_domain_routing_decision(
        self, session_id: str, decision: Any
    ) -> Dict[str, Any]:
        """Persist one validated routing decision without re-running selection."""

        resolved = resolve_domain_routing_decision(
            decision,
            registry=self._routing_registry,
        )
        payload = resolved.to_dict()
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        domain_id = resolved.selection.domain_id if resolved.selection else None
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        with self._connection() as connection:
            binding = connection.execute(
                "SELECT domain_id FROM session_domains WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if domain_id and binding is not None and str(binding[0]) != domain_id:
                raise DomainSelectionError(
                    "session belongs to another domain: " + session_id,
                    code="session_domain_mismatch",
                )
            existing = connection.execute(
                """
                SELECT decision_id, session_id, domain_id, parent_decision_id,
                       request_fingerprint, decision_json, created_at
                  FROM domain_routing_decisions
                 WHERE decision_id = ?
                """,
                (resolved.decision_id,),
            ).fetchone()
            if existing is not None:
                if existing[1] != session_id or existing[5] != encoded:
                    raise ValueError("domain routing decision id already exists")
                return self._domain_routing_decision_from_row(existing)

            if resolved.parent_decision_id:
                parent = connection.execute(
                    "SELECT session_id FROM domain_routing_decisions WHERE decision_id = ?",
                    (resolved.parent_decision_id,),
                ).fetchone()
                if parent is None:
                    raise ValueError("parent domain routing decision does not exist")
                if parent[0] != session_id:
                    raise ValueError(
                        "parent domain routing decision belongs to another session"
                    )

            created_at = time.time()
            connection.execute(
                """
                INSERT OR IGNORE INTO domain_routing_decisions (
                    decision_id, session_id, domain_id, parent_decision_id,
                    request_fingerprint, decision_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved.decision_id,
                    session_id,
                    domain_id,
                    resolved.parent_decision_id,
                    resolved.request_fingerprint,
                    encoded,
                    created_at,
                ),
            )
            row = connection.execute(
                """
                SELECT decision_id, session_id, domain_id, parent_decision_id,
                       request_fingerprint, decision_json, created_at
                  FROM domain_routing_decisions
                 WHERE decision_id = ?
                """,
                (resolved.decision_id,),
            ).fetchone()
            if row is None or row[1] != session_id or row[5] != encoded:
                raise ValueError("domain routing decision id already exists")
        return self._domain_routing_decision_from_row(row)

    @_retry_sqlite_write
    def commit_domain_routing_interaction(
        self,
        *,
        session_id: str,
        subject_decision_id: str,
        decision: Any,
        action: str,
        idempotency_key: str,
        input_fingerprint: str,
    ) -> Dict[str, Any]:
        """Atomically commit one immutable routing child and command receipt."""

        resolved = resolve_domain_routing_decision(
            decision,
            registry=self._routing_registry,
        )
        if resolved.parent_decision_id != subject_decision_id:
            raise ValueError("routing interaction child does not match its subject")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        action_id = str(action or "")[:48]
        key = str(idempotency_key or "")[:128]
        fingerprint = str(input_fingerprint or "")[:160]
        if not action_id or not key or not fingerprint:
            raise ValueError("routing interaction receipt identity is incomplete")
        encoded = json.dumps(
            resolved.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        requested_domain = (
            resolved.selection.domain_id if resolved.selection is not None else None
        )
        now = time.time()
        with self._connection() as connection:
            # Writers across Uvicorn workers serialize before checking the
            # parent/action pair, so two commands cannot create sibling
            # decisions from the same interaction revision.
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                "SELECT session_id FROM domain_routing_decisions WHERE decision_id = ?",
                (subject_decision_id,),
            ).fetchone()
            if parent is None or parent[0] != session_id:
                raise ValueError("routing interaction subject was not found")

            receipt_row = connection.execute(
                _ROUTING_INTERACTION_RECEIPT_SELECT
                + " WHERE subject_decision_id = ? AND action = ?",
                (subject_decision_id, action_id),
            ).fetchone()
            if receipt_row is not None:
                if receipt_row[2] != key or receipt_row[3] != fingerprint:
                    raise InteractionContractError(
                        "routing interaction conflicts with an existing command",
                        code="interaction_revision_conflict",
                    )
                child = connection.execute(
                    """
                    SELECT decision_id, session_id, domain_id, parent_decision_id,
                           request_fingerprint, decision_json, created_at
                      FROM domain_routing_decisions
                     WHERE decision_id = ? AND session_id = ?
                    """,
                    (receipt_row[5], session_id),
                ).fetchone()
                if child is None:
                    raise ValueError("routing interaction receipt result is missing")
                return {
                    "created": False,
                    "decision": self._domain_routing_decision_from_row(child),
                    "receipt": _routing_interaction_receipt_from_row(
                        receipt_row, reused=True
                    ),
                }

            child = connection.execute(
                """
                SELECT decision_id, session_id, domain_id, parent_decision_id,
                       request_fingerprint, decision_json, created_at
                  FROM domain_routing_decisions
                 WHERE parent_decision_id = ? AND session_id = ?
                 ORDER BY created_at, decision_id
                 LIMIT 1
                """,
                (subject_decision_id, session_id),
            ).fetchone()
            if child is not None:
                existing = self._domain_routing_decision_from_row(child)
                existing_domain = str(existing.get("domain_id") or "")
                if existing_domain != str(requested_domain or ""):
                    raise InteractionContractError(
                        "routing decision was already resolved with another domain",
                        code="interaction_revision_conflict",
                    )
                result_decision_id = str(existing["decision_id"])
            else:
                result_decision_id = resolved.decision_id
                connection.execute(
                    """
                    INSERT INTO domain_routing_decisions (
                        decision_id, session_id, domain_id, parent_decision_id,
                        request_fingerprint, decision_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result_decision_id,
                        session_id,
                        requested_domain,
                        subject_decision_id,
                        resolved.request_fingerprint,
                        encoded,
                        now,
                    ),
                )
                child = connection.execute(
                    """
                    SELECT decision_id, session_id, domain_id, parent_decision_id,
                           request_fingerprint, decision_json, created_at
                      FROM domain_routing_decisions
                     WHERE decision_id = ?
                    """,
                    (result_decision_id,),
                ).fetchone()

            connection.execute(
                """
                INSERT INTO domain_routing_interaction_receipts (
                    subject_decision_id, action, idempotency_key,
                    input_fingerprint, status, result_decision_id,
                    error_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'COMPLETED', ?, NULL, ?, ?)
                """,
                (
                    subject_decision_id,
                    action_id,
                    key,
                    fingerprint,
                    result_decision_id,
                    now,
                    now,
                ),
            )
            receipt_row = connection.execute(
                _ROUTING_INTERACTION_RECEIPT_SELECT
                + " WHERE subject_decision_id = ? AND action = ?",
                (subject_decision_id, action_id),
            ).fetchone()
        return {
            "created": True,
            "decision": self._domain_routing_decision_from_row(child),
            "receipt": _routing_interaction_receipt_from_row(
                receipt_row, reused=False
            ),
        }

    def get_domain_routing_decision(
        self, decision_id: str, session_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Return the persisted decision; never derive a Domain during reads."""

        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id must be a non-empty string")
        with self._connection() as connection:
            if session_id is not None:
                row = connection.execute(
                    """
                    SELECT decision_id, session_id, domain_id, parent_decision_id,
                           request_fingerprint, decision_json, created_at
                      FROM domain_routing_decisions
                     WHERE decision_id = ? AND session_id = ?
                    """,
                    (decision_id, session_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT decision_id, session_id, domain_id,
                           parent_decision_id, request_fingerprint,
                           decision_json, created_at
                      FROM domain_routing_decisions
                     WHERE decision_id = ?
                    """,
                    (decision_id,),
                ).fetchone()
        return self._domain_routing_decision_from_row(row) if row else None

    def list_domain_routing_decisions(
        self, session_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """List one session's immutable routing lineage, newest first."""

        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT decision_id, session_id, domain_id, parent_decision_id,
                       request_fingerprint, decision_json, created_at
                  FROM domain_routing_decisions
                 WHERE session_id = ?
                 ORDER BY created_at DESC, decision_id DESC
                 LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [self._domain_routing_decision_from_row(row) for row in rows]

    def _domain_routing_decision_from_row(self, row: Any) -> Dict[str, Any]:
        payload = json.loads(row[5])
        if not isinstance(payload, dict):
            raise ValueError("persisted domain routing decision must be an object")
        decision = resolve_domain_routing_decision(
            payload,
            registry=self._routing_registry,
        )
        canonical = decision.to_dict()
        expected_domain = decision.selection.domain_id if decision.selection else None
        if (
            payload != canonical
            or row[0] != decision.decision_id
            or row[2] != expected_domain
            or row[3] != decision.parent_decision_id
            or row[4] != decision.request_fingerprint
        ):
            raise ValueError("persisted domain routing decision columns do not match payload")
        return {
            **canonical,
            "session_id": row[1],
            "domain_id": row[2],
            "created_at": row[6],
        }

    @_retry_sqlite_write
    def insert_memory_fact(self, fact: Dict[str, Any]) -> None:
        """Persist one bounded memory fact (M80.2)."""
        self.ensure_session(str(fact.get("session_id") or "default"))
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO memory_facts (run_id, session_id, result_type, admin_names, summary, facts, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    result_type=excluded.result_type,
                    admin_names=excluded.admin_names,
                    summary=excluded.summary,
                    facts=excluded.facts,
                    created_at=excluded.created_at
                """,
                (
                    fact.get("run_id"),
                    fact.get("session_id"),
                    fact.get("result_type"),
                    json.dumps(list(fact.get("admin_names") or []), ensure_ascii=False),
                    fact.get("summary"),
                    json.dumps(fact.get("facts") or {}, ensure_ascii=False),
                    fact.get("created_at", time.time()),
                ),
            )

    def list_memory_facts(
        self, session_id: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Return memory facts, newest first; session_id=None means global."""
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as connection:
            if session_id is None:
                rows = connection.execute(
                    """
                    SELECT facts.run_id, facts.session_id, facts.result_type,
                           facts.admin_names, facts.summary, facts.facts,
                           facts.created_at
                      FROM memory_facts AS facts
                      JOIN session_domains AS domains
                        ON domains.session_id = facts.session_id
                     WHERE domains.domain_id = ?
                     ORDER BY facts.created_at DESC, facts.run_id DESC
                     LIMIT ?
                    """,
                    (self._domain_id, limit),
                ).fetchall()
            else:
                if not self._session_binding(connection, session_id, create=False):
                    return []
                rows = connection.execute(
                    "SELECT run_id, session_id, result_type, admin_names, summary, facts, created_at "
                    "FROM memory_facts WHERE session_id = ? ORDER BY created_at DESC, run_id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
        return [
            {
                "run_id": row[0],
                "session_id": row[1],
                "result_type": row[2],
                "admin_names": json.loads(row[3] or "[]"),
                "summary": row[4],
                "facts": json.loads(row[5] or "{}"),
                "created_at": row[6],
            }
            for row in rows
        ]

    @_retry_sqlite_write
    def delete_memory_facts(self, session_id: str) -> None:
        with self._connection() as connection:
            if not self._session_binding(connection, session_id, create=False):
                return
            connection.execute(
                "DELETE FROM memory_facts WHERE session_id = ?", (session_id,)
            )

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pending_clarifications (
                    session_id TEXT PRIMARY KEY,
                    request TEXT NOT NULL,
                    error TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS completed_sessions (
                    session_id TEXT PRIMARY KEY,
                    request TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_facts (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    result_type TEXT NOT NULL,
                    admin_names TEXT NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL DEFAULT '',
                    facts TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_facts_session
                    ON memory_facts(session_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS session_domains (
                    session_id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_session_domains_domain
                    ON session_domains(domain_id, session_id);
                CREATE TABLE IF NOT EXISTS domain_routing_decisions (
                    decision_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    domain_id TEXT,
                    parent_decision_id TEXT,
                    request_fingerprint TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_domain_routing_decisions_session
                    ON domain_routing_decisions(session_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS domain_routing_interaction_receipts (
                    subject_decision_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    input_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_decision_id TEXT,
                    error_code TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (subject_decision_id, action)
                );
                CREATE INDEX IF NOT EXISTS idx_domain_routing_receipts_result
                    ON domain_routing_interaction_receipts(result_decision_id);
                """
            )
            # Pre-M224 conversation rows had no Domain identity. A single,
            # deployment-level compatibility policy claims them once; future
            # service instances observe the persisted binding.
            for table in (
                "conversation_sessions",
                "pending_clarifications",
                "completed_sessions",
                "memory_facts",
            ):
                connection.execute(
                    "INSERT OR IGNORE INTO session_domains (session_id, domain_id) "
                    + "SELECT DISTINCT session_id, ? FROM "
                    + table,
                    (self._legacy_domain_id,),
                )

    def _connect(self) -> sqlite3.Connection:
        return _connect_sqlite(self._path)

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()
