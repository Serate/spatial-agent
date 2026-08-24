"""SQLite-backed state and conversation stores for the production demo."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .conversation_turn import normalize_conversation_turn
from .domain_registry import DomainRegistry, DomainSelectionError, domain_registry
from .domain_selector import resolve_domain_routing_decision
from .runtime_context import normalize_runtime_context
from .runtime import PendingClarification
from .evidence_registry import normalize_evidence_registry
from .recovery_action import normalize_action_receipt
from .execution_timeline import normalize_execution_timeline
from .nested_schema import normalize_domain_routing_evidence_contract
from .interaction_contract import InteractionContractError


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

_ROUTING_INTERACTION_RECEIPT_SELECT = """
    SELECT subject_decision_id, action, idempotency_key, input_fingerprint,
           status, result_decision_id, error_code, created_at, updated_at
      FROM domain_routing_interaction_receipts
"""


_DOMAIN_KEY_PREFIX = "spatial-agent-domain-key.v1:"


def _domain_scoped_key(domain_id: str, key: str) -> str:
    return _DOMAIN_KEY_PREFIX + str(domain_id) + ":" + str(key)


def _public_domain_key(domain_id: str, key: str) -> str:
    prefix = _DOMAIN_KEY_PREFIX + str(domain_id) + ":"
    return key[len(prefix):] if str(key).startswith(prefix) else key


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    """Open SQLite with a retry for concurrent WAL mode initialization."""
    for attempt in range(6):
        connection = sqlite3.connect(str(path), timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except sqlite3.OperationalError as exc:
            connection.close()
            if "locked" not in str(exc).lower() or attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise RuntimeError("SQLite connection retry exhausted")


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

    def save(self, result: AgentRunResult) -> None:
        payload = json.dumps(result.to_dict(), ensure_ascii=True)
        with self._connection() as connection:
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

    def finish_async_job(
        self,
        run_id: str,
        status: str,
        owner_pid: int,
        failure_category: Optional[str] = None,
    ) -> None:
        finished_at = time.time()
        with self._connection() as connection:
            connection.execute(
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
                """,
                (
                    status, finished_at, finished_at, failure_category,
                    status, status, status, status, run_id, owner_pid,
                ),
            )

    def finish_async_job_by_run_id(
        self,
        run_id: str,
        status: str,
        failure_category: Optional[str] = None,
    ) -> None:
        """Mark a job terminal regardless of owner (used by the timeout reaper).

        A job that was never claimed has owner_pid NULL, so the owner-scoped
        update would silently no-op. The reaper must still expose a terminal
        status to pollers.
        """
        finished_at = time.time()
        with self._connection() as connection:
            connection.execute(
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
                """,
                (
                    status, finished_at, finished_at, failure_category,
                    status, status, status, status, run_id,
                ),
            )

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

    def clear_pending(self, session_id: str) -> None:
        with self._connection() as connection:
            if not self._session_binding(connection, session_id, create=False):
                return
            connection.execute(
                "DELETE FROM pending_clarifications WHERE session_id = ?", (session_id,)
            )

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


def _routing_interaction_receipt_from_row(
    row: Any,
    *,
    reused: bool,
) -> Dict[str, Any]:
    if row is None:
        raise ValueError("routing interaction receipt is missing")
    return normalize_action_receipt(
        {
            "status": row[4],
            "action_id": row[1],
            "subject": {"kind": "routing_decision", "id": row[0]},
            "result_ref": {"kind": "routing_decision", "id": row[5]},
            "idempotency_key": row[2],
            "input_fingerprint": row[3],
            "error_code": row[6],
            "reused": reused,
        }
    )


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
        answer_generation_evidence=payload.get("answer_generation_evidence"),
        steps=steps,
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
