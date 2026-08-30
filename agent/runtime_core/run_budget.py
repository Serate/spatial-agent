"""Domain-neutral wall-clock budgets for one Agent Run.

The budget is deliberately separate from provider configuration and tool
governance.  A caller can ask this module for the remaining time for a phase
or a child call without knowing whether the implementation is a model client,
a GIS adapter, or a sandbox process.  Its public receipt contains timing and
state only; prompts, response text, URLs and credentials never cross here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from time import perf_counter
from typing import Any, Callable, Mapping, Optional

from agent.errors import RunTimedOut


RUN_BUDGET_SCHEMA_VERSION = "spatial-agent.run-budget.v1"

RUN_BUDGET_PHASES = frozenset(
    {"resolve", "clarify", "plan", "validate", "execute", "answer", "evidence"}
)
RUN_BUDGET_STATES = frozenset({"active", "warning", "exhausted", "completed"})

RUN_TIMEOUT_ENV = "SPATIAL_AGENT_RUN_TIMEOUT_SECONDS"
PLANNING_TIMEOUT_ENV = "SPATIAL_AGENT_PLANNING_TIMEOUT_SECONDS"
PLANNING_ATTEMPT_TIMEOUT_ENV = "SPATIAL_AGENT_PLANNING_ATTEMPT_TIMEOUT_SECONDS"
EXECUTION_TIMEOUT_ENV = "SPATIAL_AGENT_EXECUTION_TIMEOUT_SECONDS"
ANSWER_TIMEOUT_ENV = "SPATIAL_AGENT_ANSWER_TIMEOUT_SECONDS"
PROVIDER_ATTEMPT_TIMEOUT_ENV = "SPATIAL_AGENT_PROVIDER_ATTEMPT_TIMEOUT_SECONDS"

DEFAULT_PLANNING_TIMEOUT_SECONDS = 60.0
DEFAULT_PLANNING_ATTEMPT_TIMEOUT_SECONDS = 30.0
# A complex run may spend tens of seconds in planning/tools before the final
# answer call.  Keep the answer bounded, but do not make the default shorter
# than the provider's normal first-token latency observed in live acceptance.
DEFAULT_ANSWER_TIMEOUT_SECONDS = 60.0
DEFAULT_PROVIDER_ATTEMPT_TIMEOUT_SECONDS = 60.0

_MAX_BUDGET_SECONDS = 86_400.0
_MAX_RECEIPT_PHASES = 8


class RunBudgetError(ValueError):
    """Raised when a budget cannot cross the Runtime configuration seam."""


@dataclass
class RunBudget:
    """Track one Run's total and phase budgets using a monotonic clock.

    ``total_seconds=None`` preserves the low-level Runtime's historical
    unlimited total deadline.  Product and asynchronous entry points can
    provide a finite total budget.  Phase limits remain independent: a child
    timeout is always bounded by both the phase and total remaining time.
    """

    total_seconds: Optional[float] = None
    phase_seconds: Mapping[str, Optional[float]] = field(default_factory=dict)
    provider_attempt_seconds: Optional[float] = DEFAULT_PROVIDER_ATTEMPT_TIMEOUT_SECONDS
    planning_attempt_seconds: Optional[float] = DEFAULT_PLANNING_ATTEMPT_TIMEOUT_SECONDS
    source: str = "runtime"
    warning_seconds: float = 5.0
    clock: Callable[[], float] = perf_counter

    def __post_init__(self) -> None:
        self.total_seconds = _optional_seconds(self.total_seconds, "total_seconds")
        self.provider_attempt_seconds = _optional_seconds(
            self.provider_attempt_seconds, "provider_attempt_seconds"
        )
        self.planning_attempt_seconds = _optional_seconds(
            self.planning_attempt_seconds, "planning_attempt_seconds"
        )
        self.warning_seconds = _bounded_seconds(
            self.warning_seconds, "warning_seconds", minimum=0.0
        )
        normalized: dict[str, Optional[float]] = {}
        for phase, value in dict(self.phase_seconds or {}).items():
            phase_name = str(phase or "").strip().lower()
            if phase_name not in RUN_BUDGET_PHASES:
                raise RunBudgetError("unsupported budget phase: " + phase_name)
            normalized[phase_name] = _optional_seconds(value, phase_name)
        self.phase_seconds = normalized
        self._started_at = self.clock()
        self._phase_started_at: Optional[float] = None
        self._phase: Optional[str] = None
        self._phase_attempt = 0
        self._retry_count = 0
        self._heartbeat_count = 0
        self._closed = False

    @classmethod
    def from_values(
        cls,
        *,
        total_seconds: Optional[float] = None,
        planning_seconds: Optional[float] = DEFAULT_PLANNING_TIMEOUT_SECONDS,
        execution_seconds: Optional[float] = None,
        answer_seconds: Optional[float] = DEFAULT_ANSWER_TIMEOUT_SECONDS,
        provider_attempt_seconds: Optional[float] = DEFAULT_PROVIDER_ATTEMPT_TIMEOUT_SECONDS,
        planning_attempt_seconds: Optional[float] = DEFAULT_PLANNING_ATTEMPT_TIMEOUT_SECONDS,
        source: str = "runtime",
        warning_seconds: float = 5.0,
        clock: Callable[[], float] = perf_counter,
    ) -> "RunBudget":
        """Create a budget with the product's phase defaults.

        ``None`` means that the phase uses only the total Run budget.  The
        method intentionally does not read environment variables; adapters
        should resolve configuration once and pass explicit values here.
        """

        return cls(
            total_seconds=total_seconds,
            phase_seconds={
                "plan": planning_seconds,
                "execute": execution_seconds,
                "answer": answer_seconds,
            },
            provider_attempt_seconds=provider_attempt_seconds,
            planning_attempt_seconds=planning_attempt_seconds,
            source=source,
            warning_seconds=warning_seconds,
            clock=clock,
        )

    @classmethod
    def from_environment(
        cls,
        *,
        total_seconds: Optional[float] = None,
        source: str = "runtime",
        warning_seconds: float = 5.0,
        clock: Callable[[], float] = perf_counter,
    ) -> "RunBudget":
        """Create product defaults from the bounded runtime environment.

        ``from_values`` remains a deterministic low-level constructor and
        intentionally does not read process state.  Runtime entry points use
        this adapter so the public ``SPATIAL_AGENT_*_TIMEOUT_SECONDS`` knobs
        actually control the phase deadlines shown in evidence.
        """

        configured_total = (
            total_seconds
            if total_seconds is not None
            else _environment_seconds(RUN_TIMEOUT_ENV, None)
        )
        return cls.from_values(
            total_seconds=configured_total,
            planning_seconds=_environment_seconds(
                PLANNING_TIMEOUT_ENV, DEFAULT_PLANNING_TIMEOUT_SECONDS
            ),
            execution_seconds=_environment_seconds(EXECUTION_TIMEOUT_ENV, None),
            answer_seconds=_environment_seconds(
                ANSWER_TIMEOUT_ENV, DEFAULT_ANSWER_TIMEOUT_SECONDS
            ),
            provider_attempt_seconds=_environment_seconds(
                PROVIDER_ATTEMPT_TIMEOUT_ENV,
                DEFAULT_PROVIDER_ATTEMPT_TIMEOUT_SECONDS,
            ),
            planning_attempt_seconds=_environment_seconds(
                PLANNING_ATTEMPT_TIMEOUT_ENV,
                DEFAULT_PLANNING_ATTEMPT_TIMEOUT_SECONDS,
            ),
            source=source,
            warning_seconds=warning_seconds,
            clock=clock,
        )

    @property
    def phase(self) -> Optional[str]:
        return self._phase

    @property
    def attempt(self) -> int:
        return self._phase_attempt

    @property
    def retry_count(self) -> int:
        return self._retry_count

    def start_phase(self, phase: str) -> None:
        """Enter a phase and preserve its elapsed time across retries."""

        normalized = str(phase or "").strip().lower()
        if normalized not in RUN_BUDGET_PHASES:
            raise RunBudgetError("unsupported budget phase: " + normalized)
        if self._phase != normalized:
            self._phase = normalized
            self._phase_started_at = self.clock()
            self._phase_attempt = 0
        self.check()

    def finish_phase(self) -> None:
        """Mark the current phase complete without closing the Run."""

        self.check()
        self._phase_attempt = 0

    def close(self) -> None:
        self._closed = True

    def begin_attempt(self, *, retry: bool = False) -> int:
        """Record a provider/tool attempt after the caller entered a phase."""

        self.check()
        self._phase_attempt += 1
        if retry:
            self._retry_count += 1
        return self._phase_attempt

    def record_heartbeat(self) -> None:
        self._heartbeat_count += 1

    def remaining_seconds(self, phase: Optional[str] = None) -> Optional[float]:
        """Return the smallest remaining total/phase budget."""

        now = self.clock()
        values: list[float] = []
        if self.total_seconds is not None:
            values.append(max(0.0, self.total_seconds - (now - self._started_at)))
        selected = str(phase or self._phase or "").strip().lower()
        phase_limit = self.phase_seconds.get(selected) if selected else None
        if phase_limit is not None and self._phase_started_at is not None:
            values.append(max(0.0, phase_limit - (now - self._phase_started_at)))
        return min(values) if values else None

    def elapsed_seconds(self, phase: Optional[str] = None) -> float:
        now = self.clock()
        if phase is not None and str(phase).strip().lower() == self._phase:
            started = self._phase_started_at
            if started is not None:
                return max(0.0, now - started)
        return max(0.0, now - self._started_at)

    def child_timeout(
        self,
        configured_seconds: Optional[float] = None,
        *,
        kind: str = "provider",
    ) -> Optional[float]:
        """Return a child timeout bounded by phase and total remaining time."""

        configured = _optional_seconds(configured_seconds, "configured_seconds")
        if configured is None:
            configured = (
                self.planning_attempt_seconds
                if kind == "planning"
                else self.provider_attempt_seconds
                if kind == "provider"
                else None
            )
        remaining = self.remaining_seconds()
        values = [value for value in (configured, remaining) if value is not None]
        if not values:
            return None
        timeout = min(values)
        if timeout <= 0:
            self.check()
        return max(0.001, timeout)

    def child_deadline(
        self,
        configured_seconds: Optional[float] = None,
        *,
        kind: str = "provider",
    ) -> Optional[float]:
        """Return a monotonic deadline for one bounded child call.

        The deadline is derived at the last possible moment so a structured
        recovery call cannot accidentally reuse the original call's full
        timeout.  ``perf_counter`` is also used by the provider adapter and
        therefore remains monotonic without exposing wall-clock timestamps.
        """

        timeout = self.child_timeout(configured_seconds, kind=kind)
        return self.clock() + timeout if timeout is not None else None

    def check(self) -> None:
        """Raise a classified timeout once the active budget is exhausted."""

        remaining = self.remaining_seconds()
        if remaining is None or remaining > 0:
            return
        phase = self._phase or "run"
        code = {
            "plan": "planner_timeout",
            "execute": "execution_timeout",
            "answer": "answer_timeout",
        }.get(phase, "run_timeout")
        error = RunTimedOut("run budget exceeded")
        error.phase = phase
        error.code = code
        error.retryable = phase in {"plan", "execute", "answer"}
        error.budget = self.receipt()
        raise error

    def state(self) -> str:
        remaining = self.remaining_seconds()
        if remaining is not None and remaining <= 0:
            return "exhausted"
        if self._closed:
            return "completed"
        if remaining is not None and remaining <= self.warning_seconds:
            return "warning"
        return "active"

    def receipt(self) -> dict[str, Any]:
        """Return the bounded public evidence for the current budget state."""

        remaining = self.remaining_seconds()
        phase = self._phase
        phase_limit = self.phase_seconds.get(phase) if phase else None
        result: dict[str, Any] = {
            "schema_version": RUN_BUDGET_SCHEMA_VERSION,
            "state": self.state(),
            "source": _safe_text(self.source, 64) or "runtime",
            "phase": phase or "",
            "attempt": self._phase_attempt,
            "retry_count": self._retry_count,
            "heartbeat_count": self._heartbeat_count,
            "elapsed_ms": _milliseconds(self.elapsed_seconds()),
            "phase_elapsed_ms": _milliseconds(self.elapsed_seconds(phase)),
        }
        if self.total_seconds is not None:
            result["total_budget_ms"] = _milliseconds(self.total_seconds)
            result["run_remaining_ms"] = _milliseconds(remaining)
        if phase_limit is not None:
            result["phase_budget_ms"] = _milliseconds(phase_limit)
            result["phase_remaining_ms"] = _milliseconds(
                self.remaining_seconds(phase)
            )
        return result


def project_run_budget(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize persisted budget evidence without trusting extra fields."""

    source = value if isinstance(value, Mapping) else {}
    state = str(source.get("state") or "active").strip().lower()
    if state not in RUN_BUDGET_STATES:
        state = "active"
    phase = str(source.get("phase") or "").strip().lower()
    if phase not in RUN_BUDGET_PHASES:
        phase = ""
    result: dict[str, Any] = {
        "schema_version": RUN_BUDGET_SCHEMA_VERSION,
        "state": state,
        "source": _safe_text(source.get("source"), 64) or "runtime",
        "phase": phase,
        "attempt": _bounded_int(source.get("attempt"), 0, 128),
        "retry_count": _bounded_int(source.get("retry_count"), 0, 128),
        "heartbeat_count": _bounded_int(source.get("heartbeat_count"), 0, 100_000),
    }
    for key in (
        "elapsed_ms",
        "phase_elapsed_ms",
        "total_budget_ms",
        "run_remaining_ms",
        "phase_budget_ms",
        "phase_remaining_ms",
    ):
        number = _bounded_int(source.get(key), 0, int(_MAX_BUDGET_SECONDS * 1000))
        if number is not None:
            result[key] = number
    return result


def _optional_seconds(value: Any, name: str) -> Optional[float]:
    if value is None or value == "":
        return None
    # A zero-length budget is a valid internal boundary (the caller still
    # rejects a public ``timeout_seconds <= 0``). Async/recovery tests and
    # reapers use tiny positive values to request an immediate, structured
    # timeout rather than a generic worker failure.
    return _bounded_seconds(value, name, minimum=0.0)


def _environment_seconds(name: str, default: Optional[float]) -> Optional[float]:
    """Read one optional bounded timeout without accepting invalid config."""

    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return _bounded_seconds(raw, name, minimum=0.0)


def _bounded_seconds(value: Any, name: str, *, minimum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RunBudgetError(name + " must be a finite number") from exc
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        raise RunBudgetError(name + " must be a finite number")
    if parsed < minimum or parsed > _MAX_BUDGET_SECONDS:
        raise RunBudgetError(name + " is outside the supported range")
    return parsed


def _milliseconds(value: Optional[float]) -> int:
    if value is None:
        return 0
    return max(0, min(int(round(value * 1000)), int(_MAX_BUDGET_SECONDS * 1000)))


def _bounded_int(value: Any, minimum: int, maximum: int) -> Optional[int]:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", " ").strip()[:limit]


__all__ = [
    "ANSWER_TIMEOUT_ENV",
    "DEFAULT_ANSWER_TIMEOUT_SECONDS",
    "DEFAULT_PLANNING_ATTEMPT_TIMEOUT_SECONDS",
    "DEFAULT_PLANNING_TIMEOUT_SECONDS",
    "DEFAULT_PROVIDER_ATTEMPT_TIMEOUT_SECONDS",
    "EXECUTION_TIMEOUT_ENV",
    "PLANNING_ATTEMPT_TIMEOUT_ENV",
    "PLANNING_TIMEOUT_ENV",
    "PROVIDER_ATTEMPT_TIMEOUT_ENV",
    "RUN_BUDGET_PHASES",
    "RUN_BUDGET_SCHEMA_VERSION",
    "RUN_BUDGET_STATES",
    "RUN_TIMEOUT_ENV",
    "RunBudget",
    "RunBudgetError",
    "project_run_budget",
]
