"""Cooperative run cancellation and deadline control seam."""

from __future__ import annotations

from threading import Lock
from time import perf_counter
from typing import Any, Optional, Set

from agent.errors import RunCancelled, RunTimedOut


class RunControl:
    """Own process-local cancellation plus optional persistent cancellation."""

    def __init__(self, state_store: Any = None) -> None:
        self._state_store = state_store
        self._lock = Lock()
        self._cancelled: Set[str] = set()

    @property
    def cancelled_runs(self) -> Set[str]:
        """Read-only-by-convention compatibility view for diagnostics."""
        return self._cancelled

    def request_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.add(run_id)
        request_cancel = getattr(self._state_store, "request_cancel", None)
        if callable(request_cancel):
            request_cancel(run_id)

    def clear_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.discard(run_id)
        clear_cancel = getattr(self._state_store, "clear_cancel", None)
        if callable(clear_cancel):
            clear_cancel(run_id)

    def check(self, run_id: str, deadline: Optional[float]) -> None:
        with self._lock:
            local_cancelled = run_id in self._cancelled
        persistent_check = getattr(self._state_store, "is_cancel_requested", None)
        if local_cancelled or (
            callable(persistent_check) and persistent_check(run_id)
        ):
            raise RunCancelled("run cancellation requested")
        if deadline is not None and perf_counter() >= deadline:
            raise RunTimedOut("run exceeded timeout_seconds")
