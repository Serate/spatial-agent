import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Dict, Optional, Set

from .errors import ClarificationNeeded, RequestRejected, ToolError
from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .planner import Planner
from .tools import ToolRegistry


class InMemoryStateStore:
    def __init__(self):
        self._runs: Dict[str, AgentRunResult] = {}

    def save(self, result: AgentRunResult) -> None:
        self._runs[result.run_id] = result

    def get(self, run_id: str) -> Optional[AgentRunResult]:
        return self._runs.get(run_id)


class AgentRuntime:
    """The orchestration seam for planning, validation, execution, and tracing."""

    def __init__(
        self,
        planner: Planner,
        registry: ToolRegistry,
        state_store: Optional[InMemoryStateStore] = None,
        max_steps: int = 12,
        max_retries: int = 2,
    ):
        self._planner = planner
        self._registry = registry
        self._state_store = state_store or InMemoryStateStore()
        self._max_steps = max_steps
        self._max_retries = max_retries

    def run(self, request: str) -> AgentRunResult:
        result = AgentRunResult(
            run_id=str(uuid.uuid4()),
            status=RunStatus.PLANNING,
            request=request,
        )
        self._state_store.save(result)
        try:
            plan = self._planner.plan(request)
            self._validate_plan(plan)
            result.plan = plan
            result.status = RunStatus.EXECUTING
            result.steps = [StepRun(step.id, step.tool, step.args) for step in plan.steps]
            completed: Set[str] = set()
            for step_run, step in zip(result.steps, plan.steps):
                self._execute_step(step_run, step, completed)
                completed.add(step.id)
            result.status = RunStatus.COMPLETED
            result.answer = self._summarize(result)
        except ClarificationNeeded as exc:
            result.status = RunStatus.NEEDS_CLARIFICATION
            result.error = str(exc)
        except RequestRejected as exc:
            result.status = RunStatus.REJECTED
            result.error = str(exc)
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
        self._state_store.save(result)
        return result

    def get_run(self, run_id: str) -> Optional[AgentRunResult]:
        return self._state_store.get(run_id)

    def _validate_plan(self, plan: TaskPlan) -> None:
        if len(plan.steps) == 0:
            raise ClarificationNeeded("planner did not produce executable steps")
        if len(plan.steps) > self._max_steps:
            raise ToolError("Plan exceeds the maximum step limit.")
        known = {step.id for step in plan.steps}
        for step in plan.steps:
            if step.tool not in self._registry.names:
                raise ToolError("Plan selected an unregistered tool: " + step.tool)
            missing = [dependency for dependency in step.depends_on if dependency not in known]
            if missing:
                raise ToolError("Plan has unknown dependencies: " + ", ".join(missing))

    def _execute_step(self, step_run: StepRun, step: PlanStep, completed: Set[str]) -> None:
        missing = [dependency for dependency in step.depends_on if dependency not in completed]
        if missing:
            raise ToolError("Step dependencies are not complete: " + ", ".join(missing))
        step_run.status = "RUNNING"
        step_run.started_at = _utc_now()
        started = perf_counter()
        for attempt in range(1, self._max_retries + 2):
            step_run.attempts = attempt
            try:
                step_run.result = self._registry.invoke(step.tool, step.args)
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

    @staticmethod
    def _summarize(result: AgentRunResult) -> str:
        refs = [
            step.result["result_ref"]
            for step in result.steps
            if step.result and "result_ref" in step.result
        ]
        return "completed {} tool steps; result refs: {}".format(
            len(result.steps), ", ".join(refs) or "none"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
