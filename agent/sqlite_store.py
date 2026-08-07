"""SQLite-backed state and conversation stores for the production demo."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .runtime import PendingClarification


class SQLiteStateStore:
    """Persist run snapshots so retry and lookup survive worker restarts."""

    def __init__(self, path: str = "outputs/spatial-agent.db"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

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

    def get(self, run_id: str) -> Optional[AgentRunResult]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return _result_from_dict(json.loads(row[0]))

    def request_cancel(self, run_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO run_controls (run_id, cancel_requested)
                VALUES (?, 1)
                ON CONFLICT(run_id) DO UPDATE SET cancel_requested=1
                """,
                (run_id,),
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

    def list_runs(self, limit: int = 20, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as connection:
            if session_id:
                rows = connection.execute(
                    "SELECT payload, updated_at FROM agent_runs WHERE json_extract(payload, '$.session_id') = ? ORDER BY updated_at DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload, updated_at FROM agent_runs ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        records = []
        for payload, updated_at in rows:
            item = json.loads(payload)
            records.append({
                "run_id": item.get("run_id"),
                "session_id": item.get("session_id"),
                "status": item.get("status"),
                "request": item.get("request"),
                "answer": item.get("answer"),
                "error": item.get("error"),
                "planner_metrics": item.get("planner_metrics"),
                "modified_at": updated_at,
            })
        return records

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
        return len(rows)

    def metrics(self) -> Dict[str, Any]:
        records = self.list_runs(limit=1000000)
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
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._path), timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

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
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._path), timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _result_from_dict(payload: dict[str, Any]) -> AgentRunResult:
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
        resolved_request=payload.get("resolved_request"),
        plan=plan,
        planner_metrics=payload.get("planner_metrics"),
        steps=steps,
        answer=payload.get("answer"),
        error=payload.get("error"),
    )
