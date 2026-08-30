"""Runtime cancel and retry recovery seam.

This module owns active-run cancellation, waiting-decision rejection, and
retry-from-failed-step mechanics. It delegates execution and control to the
injected Runtime adapter.
"""

from __future__ import annotations

from typing import Any, Dict, Set

from ..decision_lifecycle import DecisionLifecycleError
from ..errors import RunCancelled, ToolError
from ..models import AgentRunResult, RunStatus


class RuntimeRecoverySurface:
    """Own recoverable cancel and retry transitions for a Runtime."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def cancel(self, run_id: str) -> AgentRunResult:
        runtime = self._runtime
        result = runtime._state_store.get(run_id)
        if result is None:
            raise ToolError("run not found: " + run_id)
        if result.status == RunStatus.WAITING_FOR_DECISION:
            evidence = result.decision_evidence or {}
            decision_id = evidence.get("decision_id")
            version = evidence.get("version")
            if runtime._decision_store is None or not decision_id:
                raise ToolError("waiting run has no cancellable decision")
            try:
                record = runtime._decision_store.resolve(
                    decision_id,
                    choice="reject",
                    expected_version=version,
                    domain_id=runtime.domain_id,
                )
            except DecisionLifecycleError as exc:
                raise ToolError(str(exc)) from exc
            result.status = RunStatus.CANCELLED
            result.error = "用户取消了待确认计划。"
            result.decision_evidence = record.evidence()
            runtime._state_store.save(result)
            runtime._emit_run_event(result)
            return result
        if result.status not in (RunStatus.PLANNING, RunStatus.EXECUTING):
            raise ToolError("run is not active: " + run_id)
        runtime._control.request_cancel(run_id)
        return result

    def retry_failed(self, run_id: str) -> AgentRunResult:
        runtime = self._runtime
        """Retry a failed run from its first failed step without replanning."""
        result = runtime._state_store.get(run_id)
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
        result.retry_count = int(getattr(result, "retry_count", 0) or 0) + 1
        runtime._control.clear_cancel(run_id)
        try:
            for index in range(failed_index, len(result.steps)):
                step_run = result.steps[index]
                step = result.plan.steps[index]
                try:
                    runtime._check_control(run_id, None)
                    runtime._execute_step(
                        run_id,
                        None,
                        step_run,
                        step,
                        completed,
                        completed_results,
                        result_projector=lambda tool, value: runtime._project_transient_tool_result(
                            result, tool, value
                        ),
                        source_request=result.resolved_request or result.request,
                    )
                except RunCancelled as exc:
                    runtime._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except Exception as exc:
                    runtime._block_remaining_steps(result.steps, index + 1, step.id, str(exc))
                    raise
                completed.add(step.id)
                if step_run.result is not None:
                    completed_results[step.id] = step_run.result
            result.status = RunStatus.COMPLETED
            result.answer = runtime._compose_answer(result)
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
            result.answer = runtime._answer_composer.compose_failure(result)
        runtime._state_store.save(result)
        return result
