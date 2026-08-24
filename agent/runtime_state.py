"""In-memory runtime state adapters.

The Runtime orchestrator depends on these small state interfaces, while
SQLite supplies the durable Service-level state.  Keeping the development
adapters here prevents the orchestration module from owning storage details.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional

from .models import AgentRunResult


class InMemoryStateStore:
    """Thread-safe run and cancellation state for the memory adapter."""

    def __init__(self):
        self._runs: Dict[str, AgentRunResult] = {}
        self._cancelled: set[str] = set()
        self._lock = Lock()

    def save(self, result: AgentRunResult) -> None:
        with self._lock:
            self._runs[result.run_id] = result

    def get(self, run_id: str) -> Optional[AgentRunResult]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, limit: int = 20, session_id: Optional[str] = None):
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            values = list(self._runs.values())
        if session_id:
            values = [item for item in values if item.session_id == session_id]
        values = list(reversed(values[-limit:]))
        return [
            {
                "run_id": item.run_id,
                "session_id": item.session_id,
                "status": item.status.value,
                "request": item.request,
                "answer": item.answer,
                "error": item.error,
                "planner_metrics": item.planner_metrics,
            }
            for item in values
        ]

    def clear_session_runs(self, session_id: str) -> int:
        with self._lock:
            run_ids = [
                run_id
                for run_id, item in self._runs.items()
                if item.session_id == session_id
            ]
            for run_id in run_ids:
                self._runs.pop(run_id, None)
                self._cancelled.discard(run_id)
        return len(run_ids)

    def request_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.add(run_id)

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancelled

    def clear_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.discard(run_id)


@dataclass(frozen=True)
class PendingClarification:
    request: str
    error: str


class InMemoryConversationStore:
    """Bounded clarification and last-request state for one Runtime."""

    def __init__(self):
        self._pending: Dict[str, PendingClarification] = {}
        self._last_requests: Dict[str, str] = {}

    def get_pending(self, session_id: str) -> Optional[PendingClarification]:
        return self._pending.get(session_id)

    def save_pending(self, session_id: str, request: str, error: str) -> None:
        self._pending[session_id] = PendingClarification(request=request, error=error)

    def clear_pending(self, session_id: str) -> None:
        self._pending.pop(session_id, None)

    def save_completed(self, session_id: str, request: str) -> None:
        self._last_requests[session_id] = request

    def get_last_request(self, session_id: str) -> Optional[str]:
        return self._last_requests.get(session_id)
