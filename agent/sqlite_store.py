"""SQLite-backed state and conversation stores for the production demo."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .runtime_context import normalize_runtime_context
from .runtime import PendingClarification
from .evidence_registry import normalize_evidence_registry
from .recovery_action import normalize_action_receipt


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
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO async_jobs
                    (idempotency_key, run_id, payload, status, owner_pid, updated_at,
                     created_at, recovery_count, last_event)
                VALUES (?, ?, ?, 'QUEUED', NULL, CURRENT_TIMESTAMP, ?, 0, 'submitted')
                """,
                (idempotency_key, run_id, serialized, created_at),
            )
            row = connection.execute(_ASYNC_JOB_SELECT + " WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
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
                        idempotency_key,
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
                    (idempotency_key,),
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

    def clear_session_runs(self, session_id: str) -> int:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id FROM agent_runs WHERE json_extract(payload, '$.session_id') = ?",
                (session_id,),
            ).fetchall()
            if rows:
                connection.execute(
                    "DELETE FROM run_controls WHERE run_id IN (SELECT run_id FROM agent_runs WHERE json_extract(payload, '$.session_id') = ?)",
                    (session_id,),
                )
                connection.execute(
                    "DELETE FROM agent_runs WHERE json_extract(payload, '$.session_id') = ?",
                    (session_id,),
                )
            connection.execute(
                "DELETE FROM async_jobs WHERE json_extract(payload, '$.session_id') = ?",
                (session_id,),
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

    def __init__(self, path: str = "outputs/spatial-agent.db"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get_pending(self, session_id: str) -> Optional[PendingClarification]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT request, error FROM pending_clarifications WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return PendingClarification(request=row[0], error=row[1]) if row else None

    def ensure_session(self, session_id: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        with self._connection() as connection:
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
                "SELECT COUNT(*) FROM conversation_sessions WHERE session_id LIKE 'conversation-%'"
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
        return {"session_id": session_id, "display_name": display_name}

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT session_id, display_name, created_at, updated_at FROM conversation_sessions WHERE session_id LIKE 'conversation-%' ORDER BY updated_at DESC, created_at ASC LIMIT ?",
                (limit,),
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
            connection.execute(
                "DELETE FROM pending_clarifications WHERE session_id = ?", (session_id,)
            )

    def clear_session(self, session_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM pending_clarifications WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM completed_sessions WHERE session_id = ?", (session_id,))
            connection.execute(
                "UPDATE conversation_sessions SET updated_at=CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,),
            )

    def delete_session(self, session_id: str) -> bool:
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversation_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            connection.execute("DELETE FROM pending_clarifications WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM completed_sessions WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM conversation_sessions WHERE session_id = ?", (session_id,))
        return bool(exists)

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
            row = connection.execute(
                "SELECT request FROM completed_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row[0] if row else None

    def insert_memory_fact(self, fact: Dict[str, Any]) -> None:
        """Persist one bounded memory fact (M80.2)."""
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
                    "SELECT run_id, session_id, result_type, admin_names, summary, facts, created_at "
                    "FROM memory_facts ORDER BY created_at DESC, run_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
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
                """
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
    return {
        "idempotency_key": key,
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
        "idempotency_key": row[3],
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
        # Older snapshots omitted domain_id. The adapter's configured legacy
        # domain owns that compatibility decision; the public Runtime must
        # not assume GIS when a Text/future Domain is restoring data.
        domain_id=payload.get("domain_id") or legacy_domain_id,
        runtime_context=normalize_runtime_context(payload.get("runtime_context")),
        spatial_context=payload.get("spatial_context"),
        resolved_request=payload.get("resolved_request"),
        request_facts=payload.get("request_facts"),
        plan=plan,
        planner_metrics=payload.get("planner_metrics"),
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
