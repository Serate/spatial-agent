"""Real-time progress coordination for one Runtime Run.

This module is a deep seam between blocking work and RunEvent consumers.  It
does not know about providers, tools, HTTP or the UI.  A caller supplies one
small event emitter and receives ordered stage events plus periodic, bounded
heartbeats while the caller is blocked in another adapter.
"""

from __future__ import annotations

from threading import Event, Lock, Thread
from typing import Any, Callable, Mapping, Optional

from .run_budget import RunBudget


ProgressEmitter = Callable[[str, str, str, str, str, Mapping[str, Any]], Any]

_MIN_HEARTBEAT_SECONDS = 0.25
_MAX_HEARTBEAT_SECONDS = 10.0


class ProgressCoordinator:
    """Coordinate safe stage events and a single heartbeat worker."""

    def __init__(
        self,
        run_id: str,
        budget: RunBudget,
        *,
        emit: Optional[ProgressEmitter] = None,
        heartbeat_seconds: float = 1.0,
        thread_factory: Callable[..., Thread] = Thread,
    ) -> None:
        self._run_id = str(run_id or "")[:128]
        self._budget = budget
        self._emit = emit
        self._heartbeat_seconds = _bounded_heartbeat(heartbeat_seconds)
        self._thread_factory = thread_factory
        self._lock = Lock()
        self._heartbeat_stop: Optional[Event] = None
        self._heartbeat_thread: Optional[Thread] = None
        self._phase_status = "RUNNING"
        self._closed = False

    @property
    def budget(self) -> RunBudget:
        return self._budget

    @property
    def phase(self) -> Optional[str]:
        return self._budget.phase

    def start_phase(
        self,
        phase: str,
        *,
        status: str,
        message: str,
        data: Optional[Mapping[str, Any]] = None,
        emit_event: bool = True,
    ) -> None:
        """Start a phase, optionally emit its start event, and heartbeat."""

        self._stop_heartbeat()
        with self._lock:
            if self._closed:
                return
            self._budget.start_phase(phase)
            self._phase_status = str(status or "RUNNING")[:40]
            payload = self._timing_data(data)
            if emit_event:
                self._emit_locked("stage_started", self._phase_status, message, payload)
            remaining = self._budget.remaining_seconds()
            if callable(self._emit) and (
                remaining is None or remaining > self._heartbeat_seconds
            ):
                stop = Event()
                thread = self._thread_factory(
                    target=self._heartbeat_loop,
                    args=(stop,),
                    name="agent-heartbeat-" + self._run_id[:24],
                    daemon=True,
                )
                self._heartbeat_stop = stop
                self._heartbeat_thread = thread
                thread.start()

    def begin_attempt(self, *, retry: bool = False) -> int:
        """Record an attempt and expose retry progress without model text."""

        with self._lock:
            if self._closed:
                return self._budget.attempt
            attempt = self._budget.begin_attempt(retry=retry)
            kind = "retry_started" if retry else "stage_progress"
            message = "正在重试当前阶段" if retry else "已开始当前阶段处理"
            self._emit_locked(
                kind,
                self._phase_status,
                message,
                self._timing_data({"attempt": attempt}),
            )
            return attempt

    def progress(
        self,
        message: str,
        *,
        data: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Emit one safe, caller-requested progress update."""

        with self._lock:
            if self._closed or self._budget.phase is None:
                return
            self._emit_locked(
                "stage_progress",
                self._phase_status,
                message,
                self._timing_data(data),
            )

    def heartbeat_once(self) -> None:
        """Emit one heartbeat; exposed for deterministic adapter tests."""

        with self._lock:
            if self._closed or self._budget.phase is None:
                return
            self._budget.record_heartbeat()
            receipt = self._budget.receipt()
            data = self._timing_data(
                {
                    "heartbeat_count": receipt.get("heartbeat_count"),
                    "budget_state": receipt.get("state"),
                }
            )
            self._emit_locked("heartbeat", self._phase_status, "仍在处理中", data)

    def finish_phase(
        self,
        *,
        message: str,
        kind: str = "stage_completed",
        data: Optional[Mapping[str, Any]] = None,
        emit_event: bool = True,
    ) -> None:
        """Stop heartbeats before optionally emitting the phase terminal event."""

        self._stop_heartbeat()
        with self._lock:
            if self._closed or self._budget.phase is None:
                return
            if emit_event:
                self._emit_locked(
                    kind,
                    self._phase_status,
                    message,
                    self._timing_data(data),
                )

    def recovery_started(
        self,
        message: str = "正在恢复运行",
        *,
        data: Optional[Mapping[str, Any]] = None,
    ) -> None:
        with self._lock:
            if self._closed or self._budget.phase is None:
                return
            payload = {"resume_available": True}
            if isinstance(data, Mapping):
                payload.update(data)
            self._emit_locked(
                "recovery_started",
                self._phase_status,
                message,
                self._timing_data(payload),
            )

    def close(self) -> None:
        self._stop_heartbeat()
        with self._lock:
            if not self._closed:
                self._closed = True
                self._budget.close()

    def _heartbeat_loop(self, stop: Event) -> None:
        while not stop.wait(self._heartbeat_seconds):
            self.heartbeat_once()
            if self._budget.state() == "exhausted":
                return

    def _stop_heartbeat(self) -> None:
        with self._lock:
            stop = self._heartbeat_stop
            thread = self._heartbeat_thread
            self._heartbeat_stop = None
            self._heartbeat_thread = None
            if stop is not None:
                stop.set()
        if thread is not None and thread is not threading_current():
            thread.join(timeout=self._heartbeat_seconds + 0.1)

    def _timing_data(self, data: Optional[Mapping[str, Any]]) -> dict[str, Any]:
        receipt = self._budget.receipt()
        result = {
            "elapsed_ms": receipt.get("elapsed_ms"),
            "phase_elapsed_ms": receipt.get("phase_elapsed_ms"),
            "run_elapsed_ms": receipt.get("elapsed_ms"),
            "phase_budget_ms": receipt.get("phase_budget_ms"),
            "run_budget_remaining_ms": receipt.get("run_remaining_ms"),
            "phase_remaining_ms": receipt.get("phase_remaining_ms"),
            "attempt": receipt.get("attempt"),
            "retry_count": receipt.get("retry_count"),
            "heartbeat_count": receipt.get("heartbeat_count"),
            "budget_state": receipt.get("state"),
        }
        if isinstance(data, Mapping):
            for key, value in data.items():
                if key in {
                    "stage_index",
                    "stage_count",
                    "step_id",
                    "tool",
                    "summary",
                    "reason_code",
                    "resume_available",
                    "recovery_action",
                    "recovery_actions",
                    "fallback",
                }:
                    result[key] = value
        return result

    def _emit_locked(
        self,
        kind: str,
        status: str,
        message: str,
        data: Mapping[str, Any],
    ) -> None:
        if callable(self._emit):
            self._emit(
                self._run_id,
                str(self._budget.phase or "evidence"),
                kind,
                status,
                message,
                dict(data),
            )


def _bounded_heartbeat(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        parsed = 1.0
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        parsed = 1.0
    return max(_MIN_HEARTBEAT_SECONDS, min(_MAX_HEARTBEAT_SECONDS, parsed))


def threading_current() -> Any:
    """Lazy wrapper keeps the module's public surface small for tests."""

    from threading import current_thread

    return current_thread()


__all__ = ["ProgressCoordinator", "ProgressEmitter"]
