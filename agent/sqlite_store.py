"""SQLite-backed state and conversation stores for the production demo."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

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

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
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

    def save_pending(self, session_id: str, request: str, error: str) -> None:
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

    def save_completed(self, session_id: str, request: str) -> None:
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
        resolved_request=payload.get("resolved_request"),
        plan=plan,
        planner_metrics=payload.get("planner_metrics"),
        steps=steps,
        answer=payload.get("answer"),
        error=payload.get("error"),
    )
