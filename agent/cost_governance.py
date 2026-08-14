"""Cost governance and concurrency quota (M81.1).

Three independent, environment-configurable governors, all off by default
(0 = unlimited) so existing behavior is unchanged:

- session token budget:  SPATIAL_AGENT_TOKEN_BUDGET
  Cumulative planner tokens per session; once exceeded, further runs in that
  session are rejected before any provider call.
- per-run token cap:     SPATIAL_AGENT_RUN_TOKEN_CAP
  A single run that burns more than the cap is marked budget_exceeded and
  stops (completed step evidence is kept).
- concurrency quota:     SPATIAL_AGENT_MAX_CONCURRENT
  Synchronous run() calls are limited by a semaphore; over-quota calls raise
  ConcurrencyLimited instead of queueing.
"""

from __future__ import annotations

import os
import threading
from typing import Dict, Optional

_TOKEN_BUDGET_ENV = "SPATIAL_AGENT_TOKEN_BUDGET"
_RUN_TOKEN_CAP_ENV = "SPATIAL_AGENT_RUN_TOKEN_CAP"
_MAX_CONCURRENT_ENV = "SPATIAL_AGENT_MAX_CONCURRENT"


class BudgetExceeded(Exception):
    """Session token budget exhausted; the run must not touch the provider."""

    def __init__(self, session_id: str, spent: int, limit: int) -> None:
        super().__init__(
            "token budget exceeded for session {} (spent {}, limit {})".format(
                session_id, spent, limit
            )
        )
        self.session_id = session_id
        self.spent = spent
        self.limit = limit


class RunTokenCapExceeded(Exception):
    """A single run exceeded its token cap."""

    def __init__(self, spent: int, cap: int) -> None:
        super().__init__(
            "run token cap exceeded (spent {}, cap {})".format(spent, cap)
        )
        self.spent = spent
        self.cap = cap


class ConcurrencyLimited(Exception):
    """Too many concurrent runs; the caller should surface a 429."""

    def __init__(self, active: int, limit: int) -> None:
        super().__init__(
            "concurrency limit reached (active {}, limit {})".format(active, limit)
        )
        self.active = active
        self.limit = limit


def _env_nonneg_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("{} must be a non-negative integer".format(name)) from exc
    if value < 0:
        raise ValueError("{} must be a non-negative integer".format(name))
    return value


def token_budget_limit() -> int:
    return _env_nonneg_int(_TOKEN_BUDGET_ENV, 0)


def run_token_cap() -> int:
    return _env_nonneg_int(_RUN_TOKEN_CAP_ENV, 0)


def max_concurrent_runs() -> int:
    return _env_nonneg_int(_MAX_CONCURRENT_ENV, 0)


class TokenBudget:
    """Session-scoped cumulative token accounting with a soft concurrency gate."""

    def __init__(
        self,
        budget_limit: Optional[int] = None,
        run_cap: Optional[int] = None,
        concurrency_limit: Optional[int] = None,
    ) -> None:
        self._budget_limit = token_budget_limit() if budget_limit is None else budget_limit
        self._run_cap = run_token_cap() if run_cap is None else run_cap
        self._concurrency_limit = (
            max_concurrent_runs() if concurrency_limit is None else concurrency_limit
        )
        self._lock = threading.Lock()
        self._session_spent: Dict[str, int] = {}
        self._semaphore = (
            threading.BoundedSemaphore(self._concurrency_limit)
            if self._concurrency_limit > 0
            else None
        )
        self._active = 0

    @property
    def budget_limit(self) -> int:
        return self._budget_limit

    @property
    def run_cap(self) -> int:
        return self._run_cap

    @property
    def concurrency_limit(self) -> int:
        return self._concurrency_limit

    def session_spent(self, session_id: str) -> int:
        with self._lock:
            return int(self._session_spent.get(session_id, 0))

    def check_budget(self, session_id: str) -> None:
        """Raise BudgetExceeded when the session has exhausted its budget."""
        if self._budget_limit <= 0:
            return
        spent = self.session_spent(session_id)
        if spent >= self._budget_limit:
            raise BudgetExceeded(session_id, spent, self._budget_limit)

    def charge(self, session_id: str, tokens: int) -> None:
        """Add planner tokens to the session ledger (rule planner charges 0)."""
        if tokens <= 0:
            return
        with self._lock:
            self._session_spent[session_id] = (
                self._session_spent.get(session_id, 0) + int(tokens)
            )

    def check_run_cap(self, run_tokens: int) -> None:
        """Raise RunTokenCapExceeded when a single run exceeded the cap."""
        if self._run_cap <= 0:
            return
        if run_tokens > self._run_cap:
            raise RunTokenCapExceeded(run_tokens, self._run_cap)

    def acquire_concurrency(self) -> None:
        """Enter the concurrency gate; raises ConcurrencyLimited when full."""
        if self._semaphore is None:
            return
        if not self._semaphore.acquire(blocking=False):
            with self._lock:
                active = self._active
            raise ConcurrencyLimited(active, self._concurrency_limit)
        with self._lock:
            self._active += 1

    def release_concurrency(self) -> None:
        if self._semaphore is not None:
            self._semaphore.release()
        with self._lock:
            if self._active > 0:
                self._active -= 1

    def summary(self) -> Dict[str, any]:
        return {
            "budget_limit": self._budget_limit,
            "run_token_cap": self._run_cap,
            "concurrency_limit": self._concurrency_limit,
            "active_runs": self._active,
            "session_count": len(self._session_spent),
            "sessions": {
                session: spent
                for session, spent in sorted(
                    self._session_spent.items(), key=lambda item: item[1], reverse=True
                )[:20]
            },
        }


def extract_tokens(planner_metrics: Optional[Dict]) -> int:
    """Pull total_tokens from planner metrics (rule planner has none -> 0)."""
    if not isinstance(planner_metrics, Dict):
        return 0
    usage = planner_metrics.get("usage")
    if not isinstance(usage, Dict):
        return 0
    try:
        return int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        return 0
