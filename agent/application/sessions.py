"""Session catalog and lifecycle application use case."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from agent.application.service_sessions import (
    attach_history_lineage,
    dedupe_run_records,
    validate_session_id,
)


class SessionApplication:
    """Expose one transport-neutral session interface over ServiceState."""

    def __init__(
        self,
        *,
        state: Any,
        domain_id: Callable[[], Optional[str]],
    ) -> None:
        self._state = state
        self._domain_id = domain_id

    def list_runs(self, session_id: str, limit: int = 20) -> Dict[str, Any]:
        validate_session_id(session_id)
        records = self._state.list_session_runs(
            session_id,
            limit=limit,
            domain_id=self._domain_id(),
        )
        if not self._state.persistent:
            records = dedupe_run_records(records)
        return {"runs": attach_history_lineage(records[:limit])}

    def list_sessions(self, limit: int = 50) -> Dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be positive")
        return {"sessions": self._state.list_sessions(limit=limit)}

    def create_session(self) -> Dict[str, Any]:
        return self._state.create_session()

    def clear_session(self, session_id: str) -> Dict[str, Any]:
        validate_session_id(session_id)
        return {
            "session_id": session_id,
            "cleared_runs": self._state.clear_session(session_id),
        }

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        validate_session_id(session_id)
        deleted, cleared_runs = self._state.delete_session(session_id)
        return {
            "session_id": session_id,
            "deleted": deleted,
            "cleared_runs": cleared_runs,
        }
