"""Converged mutable state for AgentService.

AgentService used to own three in-memory state surfaces directly (runtime
cache, memory sessions, memory async jobs) plus the SQLite dual-mode stores,
with ``if self._state_store is None`` branches scattered across its methods.
This module converges those surfaces into one ``ServiceState`` object and adds
two missing production capabilities that were tracked as M78 debt:

1. job-level wall-clock timeout (QUEUED + RUNNING total elapsed), and
2. a periodic reaper that marks expired jobs as TIMED_OUT and requests cancel.

The service facade keeps the ThreadPoolExecutor and worker submission; this
module only owns state, the timeout policy, and the reaper loop.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, Optional

from agent.cost_governance import TokenBudget
from agent.memory import FactMemory
from agent.observability import ObservabilityEmitter
from agent.sqlite_store import SQLiteConversationStore, SQLiteStateStore
from agent.service_sessions import runtime_key as _runtime_key

_MEMORY_JOB_FIELDS = (
    "run_id",
    "payload",
    "status",
    "created_at",
    "started_at",
    "finished_at",
    "queue_wait_ms",
    "run_duration_ms",
    "failure_category",
    "recovery_count",
    "cancel_requested_at",
    "last_event",
)


def _env_timeout(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def async_timeout_seconds() -> float:
    """Job-level wall-clock timeout (QUEUED + RUNNING)."""
    return _env_timeout("SPATIAL_AGENT_ASYNC_TIMEOUT_SECONDS", 300.0)


def reaper_interval_seconds() -> float:
    return _env_timeout("SPATIAL_AGENT_REAPER_INTERVAL_SECONDS", 5.0)


class ServiceState:
    """Owns all mutable service state and the job timeout/reaper policy.

    The SQLite stores stay owned here so every reader and writer goes through
    one object; memory sessions and memory async jobs are dicts guarded by the
    same locks the facade used before. Runtime caching is delegated to a
    factory so the facade never rebuilds runtimes by itself.
    """

    def __init__(
        self,
        state_db_path: Optional[str] = None,
        runtime_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._state_db_path = state_db_path
        self._state_store = (
            SQLiteStateStore(state_db_path) if state_db_path else None
        )
        self._conversation_store = (
            SQLiteConversationStore(state_db_path) if state_db_path else None
        )
        self._memory = FactMemory(sqlite_conversation_store=self._conversation_store)
        self._observability = ObservabilityEmitter()
        self._cost = TokenBudget()
        self._runtime_factory = runtime_factory
        self._runtimes: Dict[str, Any] = {}
        self._runtime_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._timeout_seconds = async_timeout_seconds()
        self._reaper_interval = reaper_interval_seconds()
        self._reaper_stop = threading.Event()
        self._reaper_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Stores
    # ------------------------------------------------------------------ #

    @property
    def state_store(self) -> Optional[SQLiteStateStore]:
        return self._state_store

    @property
    def conversation_store(self) -> Optional[SQLiteConversationStore]:
        return self._conversation_store

    @property
    def persistent(self) -> bool:
        return self._state_store is not None

    @property
    def memory(self) -> FactMemory:
        return self._memory

    @property
    def observability(self) -> ObservabilityEmitter:
        return self._observability

    @property
    def cost(self) -> TokenBudget:
        return self._cost

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    # ------------------------------------------------------------------ #
    # Runtime cache
    # ------------------------------------------------------------------ #

    def runtime(self, planner: str, backend: str) -> Any:
        key = _runtime_key(planner, backend)
        with self._runtime_lock:
            cached = self._runtimes.get(key)
            if cached is not None:
                return cached
            if self._runtime_factory is None:
                raise RuntimeError("runtime_factory is required to build runtimes")
            runtime = self._runtime_factory(
                planner,
                backend,
                state_store=self._state_store,
                conversation_store=self._conversation_store,
                memory=self._memory,
                observability=self._observability,
            )
            self._runtimes[key] = runtime
            return runtime

    def runtimes(self) -> Dict[str, Any]:
        with self._runtime_lock:
            return dict(self._runtimes)

    # ------------------------------------------------------------------ #
    # Memory sessions (persistent store wins when present)
    # ------------------------------------------------------------------ #

    def ensure_session(self, session_id: str, display_name: str = None) -> None:
        if self._conversation_store is not None:
            self._conversation_store.ensure_session(session_id)
            return
        with self._session_lock:
            if session_id in self._sessions:
                return
            self._sessions[session_id] = {
                "session_id": session_id,
                "display_name": display_name or session_id,
            }

    def create_session(self) -> Dict[str, Any]:
        if self._conversation_store is not None:
            return self._conversation_store.create_session()
        with self._session_lock:
            number = 1
            while "conversation-{}".format(number) in self._sessions:
                number += 1
            session_id = "conversation-{}".format(number)
            session = {
                "session_id": session_id,
                "display_name": "对话{}".format(number),
            }
            self._sessions[session_id] = session
            return dict(session)

    def list_sessions(self, limit: int = 50) -> list:
        if self._conversation_store is not None:
            return self._conversation_store.list_sessions(limit=limit)
        with self._session_lock:
            sessions = list(self._sessions.values())
        return sessions[-limit:][::-1]

    # Live views for the legacy facade accessors. The facade keeps using the
    # same locks, so direct dict mutation stays correct.
    @property
    def sessions_view(self) -> Dict[str, Dict[str, Any]]:
        return self._sessions

    @property
    def jobs_view(self) -> Dict[str, Dict[str, Any]]:
        return self._jobs

    @property
    def session_lock(self) -> threading.Lock:
        return self._session_lock

    @property
    def jobs_lock(self) -> threading.Lock:
        return self._jobs_lock

    def clear_session_runs(self, session_id: str) -> int:
        if self._state_store is not None:
            return self._state_store.clear_session_runs(session_id)
        return 0

    # ------------------------------------------------------------------ #
    # Memory async jobs (persistent store wins when present)
    # ------------------------------------------------------------------ #

    def submit_memory_job(self, idempotency_key: str, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Register a memory-mode job; returns the prior job when duplicated."""
        with self._jobs_lock:
            previous = self._jobs.get(idempotency_key)
            if previous is not None:
                return dict(previous)
            normalized = {field: job.get(field) for field in _MEMORY_JOB_FIELDS}
            normalized["created_at"] = normalized.get("created_at") or time.time()
            self._jobs[idempotency_key] = normalized
            return None

    def memory_job_by_run_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._jobs_lock:
            job = next(
                (item for item in self._jobs.values() if item.get("run_id") == run_id),
                None,
            )
            return dict(job) if job is not None else None

    def async_job(self, run_id: str) -> Optional[Dict[str, Any]]:
        if self._state_store is not None:
            return self._state_store.get_async_job(run_id)
        return self.memory_job_by_run_id(run_id)

    def recover_async_jobs(self, owner_pid: int) -> list:
        if self._state_store is None:
            return []
        return self._state_store.list_recoverable_async_jobs(owner_pid)

    # ------------------------------------------------------------------ #
    # Run snapshots and async job persistence (SQLite mode)
    # ------------------------------------------------------------------ #
    # These thin methods keep the persistent-store read/write paths inside
    # ServiceState so the facade never branches on ``_state_store is None``
    # itself. Memory-mode behavior is unchanged: callers decide fallbacks.

    def save_run(self, result: Any) -> None:
        if self._state_store is not None:
            self._state_store.save(result)

    def get_run(self, run_id: str) -> Optional[Any]:
        if self._state_store is None:
            return None
        return self._state_store.get(run_id)

    def create_async_job(self, idempotency_key: str, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._state_store is None:
            return {"created": False}
        return self._state_store.create_async_job(idempotency_key, run_id, payload)

    def claim_async_job(
        self,
        run_id: str,
        owner_pid: int,
        recover: bool = False,
        previous_owner_pid: Optional[int] = None,
    ) -> bool:
        if self._state_store is None:
            return False
        if recover:
            return self._state_store.claim_async_job(
                run_id,
                owner_pid,
                recover=True,
                previous_owner_pid=previous_owner_pid,
            )
        return self._state_store.claim_async_job(run_id, owner_pid)

    def finish_async_job(
        self, run_id: str, status: str, owner_pid: int, failure_category: str = None
    ) -> None:
        if self._state_store is not None:
            self._state_store.finish_async_job(run_id, status, owner_pid, failure_category)

    def ensure_run_snapshot(self, result: Any) -> None:
        if self._state_store is not None:
            self._state_store.ensure_run_snapshot(result)

    def list_runs(self, limit: int = 20, session_id: str = None) -> list:
        if self._state_store is None:
            return []
        if session_id is None:
            return self._state_store.list_runs(limit=limit)
        return self._state_store.list_runs(limit=limit, session_id=session_id)

    def store_metrics(self) -> Optional[Dict[str, Any]]:
        if self._state_store is None:
            return None
        return self._state_store.metrics()

    # ------------------------------------------------------------------ #
    # Wall-clock timeout + reaper
    # ------------------------------------------------------------------ #

    def expired_run_ids(self, now: float = None) -> list:
        """Return run_ids of jobs whose wall-clock age exceeds the timeout."""
        now = time.time() if now is None else now
        limit = now - self._timeout_seconds
        expired = []
        if self._state_store is not None:
            for job in self._state_store.list_active_async_jobs():
                if job.get("status") in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
                    created = _as_float(job.get("created_at"))
                    if created is not None and created <= limit:
                        expired.append(job["run_id"])
            return expired
        with self._jobs_lock:
            for job in self._jobs.values():
                if job.get("status") not in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
                    continue
                created = _as_float(job.get("created_at"))
                if created is not None and created <= limit:
                    expired.append(job["run_id"])
        return expired

    def expire_job(self, run_id: str) -> None:
        """Mark a job TIMED_OUT and persist the cancel request so the worker
        stops at its next cooperative checkpoint."""
        if self._state_store is not None:
            self._state_store.request_cancel(run_id)
            job = self._state_store.get_async_job(run_id)
            if job is not None:
                self._state_store.finish_async_job_by_run_id(
                    run_id, "TIMED_OUT", failure_category="timeout",
                )
            return
        with self._jobs_lock:
            for job in self._jobs.values():
                if job.get("run_id") != run_id:
                    continue
                job["status"] = "TIMED_OUT"
                job["finished_at"] = time.time()
                job["failure_category"] = "timeout"
                job["last_event"] = "timed_out"
                return

    def start_reaper(self) -> None:
        if self._reaper_thread is not None and self._reaper_thread.is_alive():
            return
        self._reaper_stop.clear()
        self._reaper_thread = threading.Thread(
            target=self._reaper_loop,
            name="spatial-agent-reaper",
            daemon=True,
        )
        self._reaper_thread.start()

    def stop_reaper(self) -> None:
        self._reaper_stop.set()
        thread = self._reaper_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._reaper_interval + 1.0)
        self._reaper_thread = None

    def _reaper_loop(self) -> None:
        while not self._reaper_stop.is_set():
            try:
                for run_id in self.expired_run_ids():
                    self.expire_job(run_id)
            except Exception:
                # A reaper failure must never kill the service; retry next tick.
                pass
            self._reaper_stop.wait(self._reaper_interval)


def _as_float(value) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
