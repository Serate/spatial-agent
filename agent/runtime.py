import uuid
from threading import Lock
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, Optional, Set

from .errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from .answer_composer import AnswerComposer
from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .planner import Planner
from .tools import ToolRegistry


class InMemoryStateStore:
    def __init__(self):
        self._runs: Dict[str, AgentRunResult] = {}
        self._lock = Lock()

    def save(self, result: AgentRunResult) -> None:
        with self._lock:
            self._runs[result.run_id] = result

    def get(self, run_id: str) -> Optional[AgentRunResult]:
        with self._lock:
            return self._runs.get(run_id)


@dataclass(frozen=True)
class PendingClarification:
    request: str
    error: str


class InMemoryConversationStore:
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


class AgentRuntime:
    """The orchestration seam for planning, validation, execution, and tracing."""

    def __init__(
        self,
        planner: Planner,
        registry: ToolRegistry,
        state_store: Optional[InMemoryStateStore] = None,
        conversation_store: Optional[InMemoryConversationStore] = None,
        answer_composer: Optional[AnswerComposer] = None,
        max_steps: int = 12,
        max_retries: int = 2,
    ):
        self._planner = planner
        self._registry = registry
        self._state_store = state_store or InMemoryStateStore()
        self._conversation_store = conversation_store or InMemoryConversationStore()
        self._answer_composer = answer_composer or AnswerComposer()
        self._max_steps = max_steps
        self._max_retries = max_retries
        self._control_lock = Lock()
        self._cancelled_runs: Set[str] = set()

    def run(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
    ) -> AgentRunResult:
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        deadline = perf_counter() + timeout_seconds if timeout_seconds is not None else None
        resolved_request = self._resolve_request(request, session_id)
        result = AgentRunResult(
            run_id=str(uuid.uuid4()),
            status=RunStatus.PLANNING,
            request=request,
            resolved_request=resolved_request,
        )
        self._state_store.save(result)
        try:
            plan = self._planner.plan(resolved_request)
            result.planner_metrics = self._planner_metrics()
            if plan.output.get("type") == "direct_answer":
                result.plan = plan
                result.status = RunStatus.COMPLETED
                result.answer = str(plan.output.get("message", ""))
                self._conversation_store.clear_pending(session_id)
                self._conversation_store.save_completed(session_id, resolved_request)
                self._state_store.save(result)
                return result
            self._validate_plan(plan)
            result.plan = plan
            result.status = RunStatus.EXECUTING
            result.steps = [
                StepRun(step.id, step.tool, step.args, list(step.depends_on))
                for step in plan.steps
            ]
            completed: Set[str] = set()
            completed_results: Dict[str, Dict[str, Any]] = {}
            for index, (step_run, step) in enumerate(zip(result.steps, plan.steps)):
                try:
                    self._check_control(result.run_id, deadline)
                    self._execute_step(result.run_id, deadline, step_run, step, completed, completed_results)
                except RunCancelled as exc:
                    self._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except RunTimedOut as exc:
                    self._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except Exception as exc:
                    self._block_remaining_steps(result.steps, index + 1, step.id, str(exc))
                    raise
                completed.add(step.id)
                if step_run.result is not None:
                    completed_results[step.id] = step_run.result
            result.status = RunStatus.COMPLETED
            result.answer = self._answer_composer.compose(result)
            self._conversation_store.clear_pending(session_id)
            self._conversation_store.save_completed(session_id, resolved_request)
        except ClarificationNeeded as exc:
            result.status = RunStatus.NEEDS_CLARIFICATION
            result.error = str(exc)
            self._conversation_store.save_pending(session_id, resolved_request, result.error)
        except RequestRejected as exc:
            result.status = RunStatus.REJECTED
            result.error = str(exc)
            self._conversation_store.clear_pending(session_id)
        except RunCancelled as exc:
            result.status = RunStatus.CANCELLED
            result.error = str(exc)
        except RunTimedOut as exc:
            result.status = RunStatus.TIMED_OUT
            result.error = str(exc)
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
        if result.planner_metrics is None:
            result.planner_metrics = self._planner_metrics()
        self._state_store.save(result)
        return result

    def get_run(self, run_id: str) -> Optional[AgentRunResult]:
        return self._state_store.get(run_id)

    def cancel(self, run_id: str) -> AgentRunResult:
        result = self._state_store.get(run_id)
        if result is None:
            raise ToolError("run not found: " + run_id)
        if result.status not in (RunStatus.PLANNING, RunStatus.EXECUTING):
            raise ToolError("run is not active: " + run_id)
        with self._control_lock:
            self._cancelled_runs.add(run_id)
        return result

    def retry_failed(self, run_id: str) -> AgentRunResult:
        """Retry a failed run from its first failed step without replanning."""
        result = self._state_store.get(run_id)
        if result is None:
            raise ToolError("run not found: " + run_id)
        if result.status != RunStatus.FAILED or result.plan is None:
            raise ToolError("only a failed planned run can be retried: " + run_id)

        failed_index = next(
            (index for index, step in enumerate(result.steps) if step.status == "FAILED"),
            None,
        )
        if failed_index is None:
            raise ToolError("failed run has no failed step: " + run_id)

        completed: Set[str] = set()
        completed_results: Dict[str, Dict[str, Any]] = {}
        for step in result.steps[:failed_index]:
            if step.status != "COMPLETED" or step.result is None:
                raise ToolError("completed prerequisite is unavailable: " + step.id)
            completed.add(step.id)
            completed_results[step.id] = step.result

        for step in result.steps[failed_index:]:
            step.status = "PENDING"
            step.attempts = 0
            step.result = None
            step.error = None
            step.started_at = None
            step.finished_at = None
            step.latency_ms = None

        result.status = RunStatus.EXECUTING
        result.error = None
        result.answer = None
        with self._control_lock:
            self._cancelled_runs.discard(run_id)
        try:
            for index in range(failed_index, len(result.steps)):
                step_run = result.steps[index]
                step = result.plan.steps[index]
                try:
                    self._check_control(run_id, None)
                    self._execute_step(run_id, None, step_run, step, completed, completed_results)
                except RunCancelled as exc:
                    self._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except Exception as exc:
                    self._block_remaining_steps(result.steps, index + 1, step.id, str(exc))
                    raise
                completed.add(step.id)
                if step_run.result is not None:
                    completed_results[step.id] = step_run.result
            result.status = RunStatus.COMPLETED
            result.answer = self._answer_composer.compose(result)
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
        self._state_store.save(result)
        return result

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict:
        return self._registry.export_result(result_ref, max_features=max_features)

    def _resolve_request(self, request: str, session_id: str) -> str:
        pending = self._conversation_store.get_pending(session_id)
        if pending is not None:
            return request.strip() + " " + pending.request.strip()
        previous = self._conversation_store.get_last_request(session_id)
        follow_up = ("继续", "刚才", "上面", "这个结果", "该结果", "改成", "调整为", "换成")
        if previous and any(term in request for term in follow_up):
            return request.strip() + "。基于上一轮请求：" + previous.strip()
        return request

    def _planner_metrics(self) -> Optional[Dict]:
        metrics = getattr(self._planner, "metrics", None)
        return metrics() if callable(metrics) else None

    def _validate_plan(self, plan: TaskPlan) -> None:
        if len(plan.steps) == 0:
            raise ClarificationNeeded("planner did not produce executable steps")
        if len(plan.steps) > self._max_steps:
            raise ToolError("Plan exceeds the maximum step limit.")
        known = {step.id for step in plan.steps}
        positions = {step.id: index for index, step in enumerate(plan.steps)}
        for index, step in enumerate(plan.steps):
            if step.tool not in self._registry.names:
                raise ToolError("Plan selected an unregistered tool: " + step.tool)
            missing = [dependency for dependency in step.depends_on if dependency not in known]
            if missing:
                raise ToolError("Plan has unknown dependencies: " + ", ".join(missing))
            future = [dependency for dependency in step.depends_on if positions[dependency] >= index]
            if future:
                raise ToolError(
                    "Plan dependency must refer to an earlier step: "
                    + ", ".join(future)
                )

    def _execute_step(
        self,
        run_id: str,
        deadline: Optional[float],
        step_run: StepRun,
        step: PlanStep,
        completed: Set[str],
        completed_results: Dict[str, Dict[str, Any]],
    ) -> None:
        missing = [dependency for dependency in step.depends_on if dependency not in completed]
        if missing:
            raise ToolError("Step dependencies are not complete: " + ", ".join(missing))
        resolved_args = _resolve_result_references(step.args, completed_results)
        self._check_control(run_id, deadline)
        step_run.args = resolved_args
        step_run.status = "RUNNING"
        step_run.started_at = _utc_now()
        started = perf_counter()
        for attempt in range(1, self._max_retries + 2):
            self._check_control(run_id, deadline)
            step_run.attempts = attempt
            try:
                step_run.result = self._registry.invoke(step.tool, resolved_args)
                step_run.status = "COMPLETED"
                step_run.finished_at = _utc_now()
                step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
                return
            except ToolError as exc:
                step_run.error = str(exc)
                if attempt > self._max_retries:
                    step_run.status = "FAILED"
                    step_run.finished_at = _utc_now()
                    step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
                    raise
        step_run.status = "FAILED"
        step_run.finished_at = _utc_now()
        step_run.latency_ms = round((perf_counter() - started) * 1000, 3)

    def _check_control(self, run_id: str, deadline: Optional[float]) -> None:
        with self._control_lock:
            if run_id in self._cancelled_runs:
                raise RunCancelled("run cancellation requested")
        if deadline is not None and perf_counter() >= deadline:
            raise RunTimedOut("run exceeded timeout_seconds")

    def _block_remaining_steps(
        self, steps, start_index: int, failed_step_id: str, reason: str
    ) -> None:
        for step in steps[start_index:]:
            if step.status == "PENDING":
                step.status = "BLOCKED"
                step.error = "blocked by failed step {}: {}".format(
                    failed_step_id, reason
                )

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_result_references(value: Any, results: Dict[str, Dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$from", "path"}:
            source = value["$from"]
            path = value["path"]
            if source not in results:
                raise ToolError("result reference source is not complete: " + source)
            current: Any = results[source]
            for part in path.split("."):
                if not isinstance(current, dict) or part not in current:
                    raise ToolError(
                        "result reference path not found: " + source + "." + path
                    )
                current = current[part]
            return current
        return {key: _resolve_result_references(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_result_references(item, results) for item in value]
    return value
