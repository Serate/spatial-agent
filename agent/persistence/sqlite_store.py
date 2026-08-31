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
from .sqlite_common import (
    _connect_sqlite,
    _ROUTING_INTERACTION_RECEIPT_SELECT,
    _routing_interaction_receipt_from_row,
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


_ASYNC_JOB_SELECT = """
    SELECT idempotency_key, run_id, payload, status, owner_pid, updated_at,
           created_at, started_at, finished_at, queue_wait_ms,
           run_duration_ms, failure_category, recovery_count,
           cancel_requested_at, last_event
    FROM async_jobs
"""

_INTERACTION_RECEIPT_SELECT = """
    SELECT domain_id, run_id, action, idempotency_key, input_fingerprint,
           status, result_run_id, response_payload, error_code,
           created_at, updated_at
    FROM interaction_receipts
"""


_DOMAIN_KEY_PREFIX = "spatial-agent-domain-key.v1:"
_TERMINAL_ASYNC_STATUSES = frozenset(
    {
        "COMPLETED",
        "NEEDS_CLARIFICATION",
        "WAITING_FOR_DECISION",
        "REJECTED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
    }
)


def _domain_scoped_key(domain_id: str, key: str) -> str:
    return _DOMAIN_KEY_PREFIX + str(domain_id) + ":" + str(key)


def _public_domain_key(domain_id: str, key: str) -> str:
    prefix = _DOMAIN_KEY_PREFIX + str(domain_id) + ":"
    return key[len(prefix):] if str(key).startswith(prefix) else key




class SQLiteStateStore:
    """Persist run snapshots so retry and lookup survive worker restarts."""

    def __init__(self, path: str = "outputs/spatial-agent.db", *, legacy_domain_id: str = "gis"):
        self._path = Path(path)
        normalized_domain = str(legacy_domain_id or "").strip()
        if not normalized_domain or len(normalized_domain) > 80:
            raise ValueError("legacy_domain_id must be a non-empty bounded value")
        self._legacy_domain_id = normalized_domain
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _payload_domain(self, payload: Dict[str, Any]) -> str:
        value = payload.get("domain_id")
        normalized = str(value or "").strip()
        return normalized[:80] if normalized else self._legacy_domain_id

    @_retry_sqlite_write
    def save(self, result: AgentRunResult) -> bool:
        payload = json.dumps(result.to_dict(), ensure_ascii=True)
        with self._connection() as connection:
            async_row = connection.execute(
                "SELECT status FROM async_jobs WHERE run_id = ?",
                (result.run_id,),
            ).fetchone()
            if (
                async_row is not None
                and str(async_row[0] or "").upper() in _TERMINAL_ASYNC_STATUSES
                and str(result.status.value) != str(async_row[0]).upper()
            ):
                # A reaper-written terminal job is a durable fence. A late
                # worker may finish locally, but cannot replace that result.
                return False
            connection.execute(
                """
                INSERT INTO agent_runs (run_id, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (result.run_id, payload),
            )
        return True

    @_retry_sqlite_write
    def ensure_run_snapshot(self, result: AgentRunResult) -> None:
        """Create the initial snapshot without overwriting a concurrent result."""
        payload = json.dumps(result.to_dict(), ensure_ascii=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO agent_runs (run_id, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (result.run_id, payload),
            )

    def get(self, run_id: str, domain_id: Optional[str] = None) -> Optional[AgentRunResult]:
        with self._connection() as connection:
            if domain_id:
                row = connection.execute(
                    """
                    SELECT payload FROM agent_runs
                    WHERE run_id = ?
                      AND COALESCE(json_extract(payload, '$.domain_id'), ?) = ?
                    """,
                    (run_id, self._legacy_domain_id, domain_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload FROM agent_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
        if row is None:
            return None
        return _result_from_dict(
            json.loads(row[0]), legacy_domain_id=self._legacy_domain_id
        )

    @_retry_sqlite_write
    def create_async_submission(
        self,
        idempotency_key: str,
        run_id: str,
        payload: Dict[str, Any],
        snapshot: AgentRunResult,
    ) -> Dict[str, Any]:
        """Atomically create an async job and its initial run snapshot."""
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        snapshot_payload = json.dumps(snapshot.to_dict(), ensure_ascii=True)
        created_at = time.time()
        domain_id = self._payload_domain(payload)
        storage_key = _domain_scoped_key(domain_id, idempotency_key)
        with self._connection() as connection:
            legacy_row = connection.execute(
                _ASYNC_JOB_SELECT + " WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if legacy_row is not None:
                legacy_payload = json.loads(legacy_row[2])
                if self._payload_domain(legacy_payload) == domain_id:
                    result = _async_job_from_row(
                        legacy_row, legacy_domain_id=self._legacy_domain_id
                    )
                    result["created"] = False
                    return result
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO async_jobs
                    (idempotency_key, run_id, payload, status, owner_pid, updated_at,
                     created_at, recovery_count, last_event)
                VALUES (?, ?, ?, 'QUEUED', NULL, CURRENT_TIMESTAMP, ?, 0, 'submitted')
                """,
                (storage_key, run_id, serialized, created_at),
            )
            row = connection.execute(
                _ASYNC_JOB_SELECT + " WHERE idempotency_key = ?", (storage_key,)
            ).fetchone()
            if row is None:
                row = connection.execute(
                    _ASYNC_JOB_SELECT + " WHERE run_id = ?", (run_id,)
                ).fetchone()
            created = cursor.rowcount == 1
            if created:
                connection.execute(
                    "INSERT OR IGNORE INTO agent_runs (run_id, payload, updated_at) "
                    "VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (run_id, snapshot_payload),
                )
        result = _async_job_from_row(row, legacy_domain_id=self._legacy_domain_id)
        result["created"] = created
        return result

    @_retry_sqlite_write
    def create_async_job(
        self, idempotency_key: str, run_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Atomically register an async submission and return the canonical job."""
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        created_at = time.time()
        domain_id = self._payload_domain(payload)
        storage_key = _domain_scoped_key(domain_id, idempotency_key)
        with self._connection() as connection:
            # A pre-M224 row used the public key directly. It remains a valid
            # replay only for the Domain recorded by that row's payload.
            legacy_row = connection.execute(
                _ASYNC_JOB_SELECT + " WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if legacy_row is not None:
                legacy_payload = json.loads(legacy_row[2])
                if self._payload_domain(legacy_payload) == domain_id:
                    result = _async_job_from_row(
                        legacy_row, legacy_domain_id=self._legacy_domain_id
                    )
                    result["created"] = False
                    return result
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO async_jobs
                    (idempotency_key, run_id, payload, status, owner_pid, updated_at,
                     created_at, recovery_count, last_event)
                VALUES (?, ?, ?, 'QUEUED', NULL, CURRENT_TIMESTAMP, ?, 0, 'submitted')
                """,
                (storage_key, run_id, serialized, created_at),
            )
            row = connection.execute(
                _ASYNC_JOB_SELECT + " WHERE idempotency_key = ?", (storage_key,)
            ).fetchone()
            if row is None:
                row = connection.execute(_ASYNC_JOB_SELECT + " WHERE run_id = ?", (run_id,)).fetchone()
        result = _async_job_from_row(row, legacy_domain_id=self._legacy_domain_id)
        result["created"] = cursor.rowcount == 1
        return result

    @_retry_sqlite_write
    def reserve_interaction(
        self,
        *,
        domain_id: str,
        run_id: str,
        action: str,
        idempotency_key: str,
        input_fingerprint: str,
    ) -> Dict[str, Any]:
        """Atomically reserve one interaction against a source run.

        The source-run/action primary key is the CAS boundary: a browser
        double click or two workers cannot apply different choices to the same
        clarification run. The idempotency key is a second unique boundary so
        a caller can safely replay a request after a transport failure.
        """
        now = time.time()
        storage_key = _domain_scoped_key(domain_id, idempotency_key)
        with self._connection() as connection:
            created = False
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO interaction_receipts
                        (domain_id, run_id, action, idempotency_key,
                         input_fingerprint, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'IN_PROGRESS', ?, ?)
                    """,
                    (
                        domain_id,
                        run_id,
                        action,
                        storage_key,
                        input_fingerprint,
                        now,
                        now,
                    ),
                )
                created = cursor.rowcount == 1
            except sqlite3.IntegrityError:
                created = False
            row = connection.execute(
                _INTERACTION_RECEIPT_SELECT
                + " WHERE domain_id = ? AND run_id = ? AND action = ?",
                (domain_id, run_id, action),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    _INTERACTION_RECEIPT_SELECT
                    + " WHERE idempotency_key = ?",
                    (storage_key,),
                ).fetchone()
        result = _interaction_receipt_from_row(row)
        result["created"] = created
        return result

    @_retry_sqlite_write
    def complete_interaction(
        self,
        *,
        domain_id: str,
        run_id: str,
        action: str,
        input_fingerprint: str,
        status: str,
        result_run_id: Optional[str] = None,
        response_payload: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
    ) -> bool:
        """Complete a receipt only if its original input still owns it."""
        serialized = (
            json.dumps(response_payload, ensure_ascii=True)
            if isinstance(response_payload, dict)
            else None
        )
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE interaction_receipts
                   SET status = ?, result_run_id = ?, response_payload = ?,
                       error_code = ?, updated_at = ?
                 WHERE domain_id = ? AND run_id = ? AND action = ?
                   AND input_fingerprint = ?
                   AND status = 'IN_PROGRESS'
                """,
                (
                    str(status)[:32],
                    result_run_id,
                    serialized,
                    str(error_code)[:96] if error_code else None,
                    time.time(),
                    domain_id,
                    run_id,
                    action,
                    input_fingerprint,
                ),
            )
        return cursor.rowcount == 1

    @_retry_sqlite_write
    def reopen_interaction(
        self,
        *,
        domain_id: str,
        run_id: str,
        action: str,
        idempotency_key: str,
        input_fingerprint: str,
    ) -> Dict[str, Any]:
        """Replace a failed retry attempt while preserving the CAS row."""
        storage_key = _domain_scoped_key(domain_id, idempotency_key)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE interaction_receipts
                   SET idempotency_key = ?, input_fingerprint = ?,
                       status = 'IN_PROGRESS', result_run_id = NULL,
                       response_payload = NULL, error_code = NULL,
                       updated_at = ?
                 WHERE domain_id = ? AND run_id = ? AND action = ?
                   AND status = 'FAILED'
                """,
                (
                    storage_key,
                    input_fingerprint,
                    time.time(),
                    domain_id,
                    run_id,
                    action,
                ),
            )
            row = connection.execute(
                _INTERACTION_RECEIPT_SELECT
                + " WHERE domain_id = ? AND run_id = ? AND action = ?",
                (domain_id, run_id, action),
            ).fetchone()
        result = _interaction_receipt_from_row(row)
        result["reopened"] = cursor.rowcount == 1
        result["created"] = cursor.rowcount == 1
        return result

    def get_async_job(
        self, run_id: str, domain_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            suffix = " WHERE run_id = ?"
            parameters: tuple[Any, ...] = (run_id,)
            if domain_id:
                suffix += " AND COALESCE(json_extract(payload, '$.domain_id'), ?) = ?"
                parameters += (self._legacy_domain_id, domain_id)
            row = connection.execute(
                _ASYNC_JOB_SELECT + suffix, parameters
            ).fetchone()
        return (
            _async_job_from_row(row, legacy_domain_id=self._legacy_domain_id)
            if row
            else None
        )

    @_retry_sqlite_write
    def claim_async_job(
        self,
        run_id: str,
        owner_pid: int,
        recover: bool = False,
        previous_owner_pid: Optional[int] = None,
    ) -> bool:
        """Claim a queued job, or reclaim one owned by a dead process."""
        now = time.time()
        recovery_increment = 1 if recover else 0
        event = "recovered" if recover else "started"
        if recover:
            if previous_owner_pid is None:
                owner_clause = "owner_pid IS NULL OR owner_pid != ?"
                expected_owner = owner_pid
            else:
                owner_clause = "owner_pid IS NULL OR owner_pid = ?"
                expected_owner = previous_owner_pid
            parameters = (owner_pid, run_id, expected_owner)
        else:
            owner_clause = "owner_pid IS NULL"
            parameters = (owner_pid, run_id)
        with self._connection() as connection:
            cursor = connection.execute(
                f"""
                UPDATE async_jobs
                   SET owner_pid = ?,
                       status = CASE WHEN status = 'CANCEL_REQUESTED'
                                     THEN 'CANCEL_REQUESTED' ELSE 'RUNNING' END,
                       updated_at = CURRENT_TIMESTAMP,
                       started_at = COALESCE(started_at, ?),
                       queue_wait_ms = COALESCE(queue_wait_ms,
                           MAX(0, (? - COALESCE(created_at, ?)) * 1000)),
                       recovery_count = recovery_count + ?,
                       last_event = ?
                 WHERE run_id = ?
                    AND status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')
                    AND ({owner_clause})
                """,
                (owner_pid, now, now, now, recovery_increment, event) + parameters[1:],
            )
        return cursor.rowcount == 1

    def list_recoverable_async_jobs(
        self, owner_pid: int, domain_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return jobs left by another process or never claimed after a crash."""
        domain_clause = ""
        parameters: tuple[Any, ...] = (owner_pid,)
        if domain_id:
            domain_clause = (
                " AND COALESCE(json_extract(payload, '$.domain_id'), ?) = ?"
            )
            parameters += (self._legacy_domain_id, domain_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT idempotency_key, run_id, payload, status, owner_pid, updated_at,
                       created_at, started_at, finished_at, queue_wait_ms,
                       run_duration_ms, failure_category, recovery_count,
                       cancel_requested_at, last_event
                FROM async_jobs
                WHERE status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')
                  AND (owner_pid IS NULL OR owner_pid != ?)
                """ + domain_clause + " ORDER BY updated_at, run_id",
                parameters,
            ).fetchall()
        return [
            _async_job_from_row(row, legacy_domain_id=self._legacy_domain_id)
            for row in rows
        ]

    def list_active_async_jobs(self, domain_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return every non-terminal job for the wall-clock timeout reaper."""
        domain_clause = ""
        parameters: tuple[Any, ...] = ()
        if domain_id:
            domain_clause = (
                " AND COALESCE(json_extract(payload, '$.domain_id'), ?) = ?"
            )
            parameters = (self._legacy_domain_id, domain_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT idempotency_key, run_id, payload, status, owner_pid, updated_at,
                       created_at, started_at, finished_at, queue_wait_ms,
                       run_duration_ms, failure_category, recovery_count,
                       cancel_requested_at, last_event
                FROM async_jobs
                WHERE status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')
                """ + domain_clause + " ORDER BY created_at, run_id",
                parameters,
            ).fetchall()
        return [
            _async_job_from_row(row, legacy_domain_id=self._legacy_domain_id)
            for row in rows
        ]

    @_retry_sqlite_write
    def expire_async_job(
        self, run_id: str, failure_category: str = "timeout"
    ) -> Optional[Dict[str, Any]]:
        """Atomically fence one active job as timed out and request cancel."""
        finished_at = time.time()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE async_jobs
                   SET status = 'TIMED_OUT', updated_at = CURRENT_TIMESTAMP,
                       finished_at = ?,
                       run_duration_ms = CASE
                           WHEN started_at IS NULL THEN NULL
                           ELSE MAX(0, (? - started_at) * 1000)
                       END,
                       failure_category = ?,
                       cancel_requested_at = COALESCE(cancel_requested_at, ?),
                       last_event = 'timed_out'
                 WHERE run_id = ?
                   AND status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')
                """,
                (finished_at, finished_at, failure_category, finished_at, run_id),
            )
            if cursor.rowcount != 1:
                return None
            connection.execute(
                """
                INSERT INTO run_controls (run_id, cancel_requested)
                VALUES (?, 1)
                ON CONFLICT(run_id) DO UPDATE SET cancel_requested=1
                """,
                (run_id,),
            )
            row = connection.execute(
                _ASYNC_JOB_SELECT + " WHERE run_id = ?", (run_id,)
            ).fetchone()
        return _async_job_from_row(row, legacy_domain_id=self._legacy_domain_id)

    @_retry_sqlite_write
    def finish_async_job(
        self,
        run_id: str,
        status: str,
        owner_pid: int,
        failure_category: Optional[str] = None,
    ) -> bool:
        finished_at = time.time()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE async_jobs
                   SET status = ?, updated_at = CURRENT_TIMESTAMP,
                       finished_at = ?,
                       run_duration_ms = CASE
                           WHEN started_at IS NULL THEN NULL
                           ELSE MAX(0, (? - started_at) * 1000)
                       END,
                       failure_category = ?,
                       last_event = CASE
                           WHEN ? = 'COMPLETED' THEN 'completed'
                           WHEN ? = 'CANCELLED' THEN 'cancelled'
                           WHEN ? = 'TIMED_OUT' THEN 'timed_out'
                           WHEN ? = 'FAILED' THEN 'failed'
                           ELSE 'finished'
                       END
                 WHERE run_id = ? AND owner_pid = ?
                   AND status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')
                """,
                (
                    status, finished_at, finished_at, failure_category,
                    status, status, status, status, run_id, owner_pid,
                ),
            )
        return cursor.rowcount == 1

    @_retry_sqlite_write
    def finish_async_job_by_run_id(
        self,
        run_id: str,
        status: str,
        failure_category: Optional[str] = None,
    ) -> bool:
        """Mark a job terminal regardless of owner (used by the timeout reaper).

        A job that was never claimed has owner_pid NULL, so the owner-scoped
        update would silently no-op. The reaper must still expose a terminal
        status to pollers.
        """
        finished_at = time.time()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE async_jobs
                   SET status = ?, updated_at = CURRENT_TIMESTAMP,
                       finished_at = ?,
                       run_duration_ms = CASE
                           WHEN started_at IS NULL THEN NULL
                           ELSE MAX(0, (? - started_at) * 1000)
                       END,
                       failure_category = ?,
                       last_event = CASE
                           WHEN ? = 'COMPLETED' THEN 'completed'
                           WHEN ? = 'CANCELLED' THEN 'cancelled'
                           WHEN ? = 'TIMED_OUT' THEN 'timed_out'
                           WHEN ? = 'FAILED' THEN 'failed'
                           ELSE 'finished'
                       END
                 WHERE run_id = ?
                   AND status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')
                """,
                (
                    status, finished_at, finished_at, failure_category,
                    status, status, status, status, run_id,
                ),
            )
        return cursor.rowcount == 1

    @_retry_sqlite_write
    def request_cancel(self, run_id: str) -> None:
        requested_at = time.time()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO run_controls (run_id, cancel_requested)
                VALUES (?, 1)
                ON CONFLICT(run_id) DO UPDATE SET cancel_requested=1
                """,
                (run_id,),
            )
            connection.execute(
                """
                UPDATE async_jobs
                   SET status = CASE
                           WHEN status IN ('QUEUED', 'RUNNING') THEN 'CANCEL_REQUESTED'
                           ELSE status
                       END,
                       cancel_requested_at = COALESCE(cancel_requested_at, ?),
                       last_event = CASE WHEN status IN ('QUEUED', 'RUNNING')
                                         THEN 'cancel_requested' ELSE last_event END,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE run_id = ?
                """,
                (requested_at, run_id),
            )

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM run_controls WHERE run_id = ?", (run_id,)
            ).fetchone()
        return bool(row and row[0])

    @_retry_sqlite_write
    def clear_cancel(self, run_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM run_controls WHERE run_id = ?", (run_id,))

    def list_runs(
        self,
        limit: int = 20,
        session_id: Optional[str] = None,
        domain_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        domain_clause = ""
        domain_parameters: tuple[Any, ...] = ()
        if domain_id:
            domain_clause = (
                " AND COALESCE(json_extract(payload, '$.domain_id'), ?) = ?"
            )
            domain_parameters = (self._legacy_domain_id, domain_id)
        with self._connection() as connection:
            if session_id:
                rows = connection.execute(
                    "SELECT payload, updated_at FROM agent_runs "
                    "WHERE json_extract(payload, '$.session_id') = ?"
                    + domain_clause
                    + " ORDER BY updated_at DESC LIMIT ?",
                    (session_id,) + domain_parameters + (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload, updated_at FROM agent_runs WHERE 1=1"
                    + domain_clause
                    + " ORDER BY updated_at DESC LIMIT ?",
                    domain_parameters + (limit,),
                ).fetchall()
        records = []
        for payload, updated_at in rows:
            item = json.loads(payload)
            record = {
                "run_id": item.get("run_id"),
                "domain_id": self._payload_domain(item),
                "session_id": item.get("session_id"),
                "status": item.get("status"),
                "request": item.get("request"),
                "answer": item.get("answer"),
                "error": item.get("error"),
                "evidence_registry": normalize_evidence_registry(
                    item.get("evidence_registry")
                    or ((item.get("result") or {}).get("evidence_registry")
                        if isinstance(item.get("result"), dict) else None)
                ),
                "execution_timeline": normalize_execution_timeline(
                    item.get("execution_timeline")
                    or ((item.get("result") or {}).get("execution_timeline")
                        if isinstance(item.get("result"), dict) else None)
                ),
                "planner_metrics": item.get("planner_metrics"),
                "modified_at": updated_at,
            }
            action_receipt = item.get("action_receipt")
            if action_receipt is None:
                action_receipt = self.interaction_receipt_for_result_run(
                    item.get("run_id"), domain_id=domain_id
                )
            if action_receipt:
                record["action_receipt"] = normalize_action_receipt(action_receipt)
            records.append(record)
        return records

    def interaction_receipt_for_result_run(
        self, result_run_id: Optional[str], domain_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return the bounded interaction record that produced one child run."""
        if not result_run_id:
            return {}
        clause = " WHERE result_run_id = ?"
        parameters: tuple[Any, ...] = (str(result_run_id),)
        if domain_id:
            clause += " AND domain_id = ?"
            parameters += (str(domain_id),)
        with self._connection() as connection:
            row = connection.execute(
                _INTERACTION_RECEIPT_SELECT + clause + " ORDER BY updated_at DESC LIMIT 1",
                parameters,
            ).fetchone()
        return _interaction_receipt_from_row(row)

    @_retry_sqlite_write
    def clear_session_runs(
        self, session_id: str, domain_id: Optional[str] = None
    ) -> int:
        domain_clause = ""
        domain_parameters: tuple[Any, ...] = ()
        if domain_id:
            domain_clause = (
                " AND COALESCE(json_extract(payload, '$.domain_id'), ?) = ?"
            )
            domain_parameters = (self._legacy_domain_id, domain_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id FROM agent_runs WHERE json_extract(payload, '$.session_id') = ?"
                + domain_clause,
                (session_id,) + domain_parameters,
            ).fetchall()
            if rows:
                run_ids = tuple(row[0] for row in rows)
                placeholders = ",".join("?" for _ in run_ids)
                connection.execute(
                    "DELETE FROM run_controls WHERE run_id IN (" + placeholders + ")",
                    run_ids,
                )
                connection.execute(
                    "DELETE FROM run_events WHERE run_id IN (" + placeholders + ")",
                    run_ids,
                )
                connection.execute(
                    "DELETE FROM agent_runs WHERE run_id IN (" + placeholders + ")",
                    run_ids,
                )
                connection.execute(
                    "DELETE FROM async_jobs WHERE run_id IN (" + placeholders + ")",
                    run_ids,
                )
            async_domain_clause = ""
            async_parameters: tuple[Any, ...] = ()
            if domain_id:
                async_domain_clause = (
                    " AND COALESCE(json_extract(payload, '$.domain_id'), ?) = ?"
                )
                async_parameters = (self._legacy_domain_id, domain_id)
            connection.execute(
                "DELETE FROM async_jobs WHERE json_extract(payload, '$.session_id') = ?"
                + async_domain_clause,
                (session_id,) + async_parameters,
            )
        return len(rows)

    @_retry_sqlite_write
    def append_run_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Append one idempotent event and assign a run-local sequence."""
        normalized = normalize_run_event(event)
        with self._connection() as connection:
            # Sequence allocation and the terminal-fence check must share one
            # write transaction. A reaper and a late worker can otherwise
            # both observe the same MAX(sequence) and race into the unique
            # (run_id, sequence) constraint.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT payload FROM run_events WHERE event_id = ?",
                (normalized["event_id"],),
            ).fetchone()
            if existing is not None:
                return json.loads(existing[0])
            terminal = connection.execute(
                """
                SELECT payload FROM run_events
                 WHERE run_id = ?
                   AND json_extract(payload, '$.terminal') = 1
                 ORDER BY sequence DESC
                 LIMIT 1
                """,
                (normalized["run_id"],),
            ).fetchone()
            if terminal is not None:
                # A terminal event is a durable event fence. Late worker
                # progress is ignored while the append seam stays idempotent.
                return json.loads(terminal[0])
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM run_events WHERE run_id = ?",
                (normalized["run_id"],),
            ).fetchone()
            normalized["sequence"] = int(row[0] or 0) + 1
            payload = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
            connection.execute(
                """
                INSERT INTO run_events
                    (event_id, run_id, sequence, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    normalized["event_id"],
                    normalized["run_id"],
                    normalized["sequence"],
                    normalized["created_at"],
                    payload,
                ),
            )
        return normalized

    def list_run_events(
        self,
        run_id: str,
        *,
        after: Any = 0,
        limit: Any = 100,
        domain_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Read a bounded, ordered event window after a run-local cursor."""
        cursor = validate_event_cursor(after)
        count = validate_event_limit(limit)
        domain_clause = ""
        parameters: tuple[Any, ...] = (str(run_id), cursor, count)
        if domain_id:
            domain_clause = """
                   AND EXISTS (
                       SELECT 1 FROM agent_runs AS runs
                        WHERE runs.run_id = run_events.run_id
                          AND COALESCE(json_extract(runs.payload, '$.domain_id'), ?) = ?
                   )
            """
            parameters = (
                str(run_id),
                cursor,
                self._legacy_domain_id,
                str(domain_id),
                count,
            )
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM run_events
                 WHERE run_id = ? AND sequence > ?
                """ + domain_clause + """
                 ORDER BY sequence ASC
                 LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [normalize_run_event(json.loads(row[0]), expected_run_id=str(run_id)) for row in rows]

    def metrics(self, domain_id: Optional[str] = None) -> Dict[str, Any]:
        records = self.list_runs(limit=1000000, domain_id=domain_id)
        status_counts: Dict[str, int] = {}
        total_tokens = 0
        for record in records:
            status = record.get("status") or "UNKNOWN"
            status_counts[status] = status_counts.get(status, 0) + 1
            usage = ((record.get("planner_metrics") or {}).get("usage") or {})
            total_tokens += int(usage.get("total_tokens") or 0)
        return {
            "run_count": len(records),
            "status_counts": status_counts,
            "total_tokens": total_tokens,
            "async_jobs": self.async_metrics(domain_id=domain_id),
        }

    def async_metrics(self, domain_id: Optional[str] = None) -> Dict[str, Any]:
        """Return aggregate async lifecycle metrics without request payloads."""
        domain_clause = ""
        parameters: tuple[Any, ...] = ()
        if domain_id:
            domain_clause = (
                " WHERE COALESCE(json_extract(payload, '$.domain_id'), ?) = ?"
            )
            parameters = (self._legacy_domain_id, domain_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT status, created_at, started_at, finished_at,
                       queue_wait_ms, run_duration_ms, failure_category,
                       recovery_count
                FROM async_jobs
                """ + domain_clause,
                parameters,
            ).fetchall()
        now = time.time()
        status_counts: Dict[str, int] = {}
        failure_categories: Dict[str, int] = {}
        queue_waits = []
        run_durations = []
        recovered_jobs = 0
        for row in rows:
            status, created_at, started_at, finished_at, queue_wait, duration, category, recovery_count = row
            status_counts[status] = status_counts.get(status, 0) + 1
            if category:
                failure_categories[category] = failure_categories.get(category, 0) + 1
            if queue_wait is None and created_at is not None and started_at is None:
                queue_wait = max(0, (now - created_at) * 1000)
            if queue_wait is not None:
                queue_waits.append(float(queue_wait))
            if duration is None and started_at is not None and finished_at is None:
                duration = max(0, (now - started_at) * 1000)
            if duration is not None:
                run_durations.append(float(duration))
            if int(recovery_count or 0) > 0:
                recovered_jobs += 1
        return {
            "count": len(rows),
            "status_counts": status_counts,
            "failure_categories": failure_categories,
            "recovered_jobs": recovered_jobs,
            "queue_wait_ms": _duration_summary(queue_waits),
            "run_duration_ms": _duration_summary(run_durations),
        }

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE (run_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_run_events_run_sequence
                    ON run_events(run_id, sequence);
                CREATE TABLE IF NOT EXISTS run_controls (
                    run_id TEXT PRIMARY KEY,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS async_jobs (
                    idempotency_key TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner_pid INTEGER,
                    updated_at TEXT NOT NULL,
                    created_at REAL,
                    started_at REAL,
                    finished_at REAL,
                    queue_wait_ms REAL,
                    run_duration_ms REAL,
                    failure_category TEXT,
                    recovery_count INTEGER NOT NULL DEFAULT 0,
                    cancel_requested_at REAL,
                    last_event TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_async_jobs_status
                    ON async_jobs(status, owner_pid);
                CREATE TABLE IF NOT EXISTS interaction_receipts (
                    domain_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    input_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_run_id TEXT,
                    response_payload TEXT,
                    error_code TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (domain_id, run_id, action)
                );
                CREATE INDEX IF NOT EXISTS idx_interaction_receipts_run
                    ON interaction_receipts(domain_id, run_id, action);
                """
            )
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(async_jobs)").fetchall()
            }
            migrations = {
                "created_at": "ALTER TABLE async_jobs ADD COLUMN created_at REAL",
                "started_at": "ALTER TABLE async_jobs ADD COLUMN started_at REAL",
                "finished_at": "ALTER TABLE async_jobs ADD COLUMN finished_at REAL",
                "queue_wait_ms": "ALTER TABLE async_jobs ADD COLUMN queue_wait_ms REAL",
                "run_duration_ms": "ALTER TABLE async_jobs ADD COLUMN run_duration_ms REAL",
                "failure_category": "ALTER TABLE async_jobs ADD COLUMN failure_category TEXT",
                "recovery_count": "ALTER TABLE async_jobs ADD COLUMN recovery_count INTEGER NOT NULL DEFAULT 0",
                "cancel_requested_at": "ALTER TABLE async_jobs ADD COLUMN cancel_requested_at REAL",
                "last_event": "ALTER TABLE async_jobs ADD COLUMN last_event TEXT",
            }
            for name, statement in migrations.items():
                if name not in existing_columns:
                    connection.execute(statement)
            connection.execute(
                "UPDATE async_jobs SET last_event = COALESCE(last_event, 'legacy')"
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






def _async_job_from_row(row, *, legacy_domain_id: str = "gis") -> Dict[str, Any]:
    if row is None:
        return {}
    values = list(row) + [None] * max(0, 15 - len(row))
    (
        key,
        run_id,
        payload,
        status,
        owner_pid,
        updated_at,
        created_at,
        started_at,
        finished_at,
        queue_wait_ms,
        run_duration_ms,
        failure_category,
        recovery_count,
        cancel_requested_at,
        last_event,
    ) = values[:15]
    decoded_payload = json.loads(payload)
    if isinstance(decoded_payload, dict):
        decoded_payload.setdefault("domain_id", legacy_domain_id)
    domain_id = (
        str(decoded_payload.get("domain_id") or legacy_domain_id)
        if isinstance(decoded_payload, dict)
        else legacy_domain_id
    )
    return {
        "idempotency_key": _public_domain_key(domain_id, key),
        "run_id": run_id,
        "payload": decoded_payload,
        "status": status,
        "owner_pid": owner_pid,
        "updated_at": updated_at,
        "created_at": created_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "queue_wait_ms": queue_wait_ms,
        "run_duration_ms": run_duration_ms,
        "failure_category": failure_category,
        "recovery_count": int(recovery_count or 0),
        "cancel_requested_at": cancel_requested_at,
        "last_event": last_event,
    }


def _interaction_receipt_from_row(row) -> Dict[str, Any]:
    if row is None:
        return {}
    response_payload = None
    if row[7]:
        try:
            value = json.loads(row[7])
            response_payload = value if isinstance(value, dict) else None
        except (TypeError, ValueError):
            response_payload = None
    return {
        "domain_id": row[0],
        "run_id": row[1],
        "action": row[2],
        "idempotency_key": _public_domain_key(str(row[0]), row[3]),
        "input_fingerprint": row[4],
        "status": row[5],
        "result_run_id": row[6],
        "response_payload": response_payload,
        "error_code": row[8],
        "created_at": row[9],
        "updated_at": row[10],
    }


def _duration_summary(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0, "total_ms": 0.0, "average_ms": None, "max_ms": None}
    total = sum(values)
    return {
        "count": len(values),
        "total_ms": round(total, 3),
        "average_ms": round(total / len(values), 3),
        "max_ms": round(max(values), 3),
    }


def _result_from_dict(
    payload: dict[str, Any], *, legacy_domain_id: str = "gis"
) -> AgentRunResult:
    plan_payload = payload.get("plan")
    plan = None
    if isinstance(plan_payload, dict):
        plan = TaskPlan(
            goal=plan_payload["goal"],
            steps=[
                PlanStep(
                    id=step["id"],
                    tool=step["tool"],
                    args=step.get("args", {}),
                    depends_on=list(step.get("depends_on", [])),
                )
                for step in plan_payload.get("steps", [])
            ],
            output=plan_payload.get("output", {}),
            assumptions=list(plan_payload.get("assumptions", [])),
        )
    steps = [
        StepRun(
            id=step["id"],
            tool=step["tool"],
            args=step.get("args", {}),
            depends_on=list(step.get("depends_on", [])),
            status=step.get("status", "PENDING"),
            attempts=step.get("attempts", 0),
            result=step.get("result"),
            error=step.get("error"),
            error_category=step.get("error_category"),
            error_code=step.get("error_code"),
            retryable=step.get("retryable"),
            governance=step.get("governance"),
            started_at=step.get("started_at"),
            finished_at=step.get("finished_at"),
            latency_ms=step.get("latency_ms"),
        )
        for step in payload.get("steps", [])
    ]
    return AgentRunResult(
        run_id=payload["run_id"],
        status=RunStatus(payload["status"]),
        request=payload["request"],
        session_id=payload.get("session_id"),
        conversation_turn=(
            normalize_conversation_turn(payload.get("conversation_turn"))
            if payload.get("conversation_turn") is not None
            else None
        ),
        request_mode=(
            normalize_request_mode(payload.get("request_mode"))
            if payload.get("request_mode") is not None
            else None
        ),
        # Older snapshots omitted domain_id. The adapter's configured legacy
        # domain owns that compatibility decision; the public Runtime must
        # not assume GIS when a Text/future Domain is restoring data.
        domain_id=payload.get("domain_id") or legacy_domain_id,
        domain_routing_evidence=normalize_domain_routing_evidence_contract(
            payload.get("domain_routing_evidence"),
            expected_domain_id=payload.get("domain_id") or legacy_domain_id,
        ),
        runtime_context=normalize_runtime_context(payload.get("runtime_context")),
        spatial_context=payload.get("spatial_context"),
        resolved_request=payload.get("resolved_request"),
        request_facts=payload.get("request_facts"),
        plan=plan,
        planner_metrics=payload.get("planner_metrics"),
        budget_evidence=payload.get("budget_evidence"),
        react_evidence=payload.get("react_evidence"),
        answer_generation_evidence=payload.get("answer_generation_evidence"),
        steps=steps,
        result=payload.get("result"),
        answer=payload.get("answer"),
        error=payload.get("error"),
        error_category=payload.get("error_category"),
        error_code=payload.get("error_code"),
        failure=payload.get("failure"),
        clarification=payload.get("clarification"),
        workflow=payload.get("workflow"),
        artifact_ref=payload.get("artifact_ref"),
        geojson_ref=payload.get("geojson_ref"),
        geometry_evidence=payload.get("geometry_evidence"),
        context_evidence=payload.get("context_evidence"),
        plan_evidence=payload.get("plan_evidence"),
        replan_events=payload.get("replan_events") or [],
        decision_evidence=payload.get("decision_evidence"),
        action_receipt=payload.get("action_receipt"),
    )

from .sqlite_conversation_store import SQLiteConversationStore  # noqa: E402,F401
