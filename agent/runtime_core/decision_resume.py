"""Decision-approved Runtime resume lifecycle.

This seam continues the exact persisted plan after an accepted decision. It
reuses the Runtime execution and replan ports while owning decision fencing
and recovery terminal states.
"""

from __future__ import annotations

import uuid
from time import perf_counter
from typing import Any, Dict, Optional, Set

from ..errors import RunCancelled, RunTimedOut, ToolError
from ..models import AgentRunResult, RunStatus


class RuntimeDecisionResume:
    """Resume an approved plan through the injected Runtime adapter."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def resume(
        self,
        result: AgentRunResult,
        *,
        decision_id: str,
        decision_version: Optional[int],
        timeout_seconds: Optional[float],
    ) -> AgentRunResult:
        runtime = self._runtime
        from .. import runtime as _runtime_module
        """Resume the exact persisted plan after an accepted decision.

        The plan is loaded from the waiting run snapshot instead of asking the
        Planner to regenerate it.  This makes approval meaningful even for a
        nondeterministic provider and keeps the fingerprint a real execution
        boundary rather than a best-effort comparison.
        """
        if runtime._decision_store is None:
            raise ToolError("decision store is unavailable")
        if result.status != RunStatus.WAITING_FOR_DECISION or result.plan is None:
            raise ToolError("run is not waiting for a decision: " + result.run_id)
        record = runtime._decision_store.get(decision_id, domain_id=runtime.domain_id)
        if record is None or record.subject_id != result.run_id:
            raise ToolError("decision does not belong to run: " + result.run_id)
        if record.status != "ACCEPTED":
            raise ToolError("decision is not accepted: " + decision_id)
        if decision_version is None or int(decision_version) != record.version:
            raise ToolError("decision version mismatch")
        fingerprint = str(
            (result.plan_evidence or {}).get("plan_identity", {}).get("fingerprint", "")
        )
        if not fingerprint or fingerprint != record.subject_fingerprint:
            raise ToolError("decision plan fingerprint mismatch")
        consumed = runtime._decision_store.consume(
            decision_id,
            expected_version=record.version,
            domain_id=runtime.domain_id,
        )
        result.decision_evidence = consumed.evidence()
        runtime._run_span_ids[result.run_id] = uuid.uuid4().hex[:16]
        clear_cancel = getattr(runtime._state_store, "clear_cancel", None)
        if callable(clear_cancel):
            clear_cancel(result.run_id)
        result.status = RunStatus.EXECUTING
        result.error = None
        result.answer = None
        deadline = (
            perf_counter() + timeout_seconds
            if timeout_seconds is not None
            else None
        )
        completed: Set[str] = set()
        completed_results: Dict[str, Dict[str, Any]] = {}
        for step in result.steps:
            if step.status == "COMPLETED" and step.result is not None:
                completed.add(step.id)
                completed_results[step.id] = step.result
        try:
            if not result.steps and result.plan.output.get("type") == "direct_answer":
                result.status = RunStatus.COMPLETED
                result.answer = str(result.plan.output.get("message", ""))
                runtime._conversation_store.clear_pending(result.session_id or "default")
                runtime._conversation_store.save_completed(
                    result.session_id or "default", result.resolved_request or result.request
                )
                runtime._state_store.save(result)
                runtime._remember(result)
                runtime._emit_run_event(result)
                return result
            index = 0
            replan_count = len(result.replan_events or [])
            while index < len(result.steps):
                step_run = result.steps[index]
                step = result.plan.steps[index]
                if step_run.status == "COMPLETED":
                    index += 1
                    continue
                try:
                    runtime._check_control(result.run_id, deadline)
                    runtime._execute_step(
                        result.run_id,
                        deadline,
                        step_run,
                        step,
                        completed,
                        completed_results,
                    )
                    completed.add(step.id)
                    if step_run.result is not None:
                        completed_results[step.id] = step_run.result
                    index += 1
                except RunCancelled as exc:
                    runtime._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except RunTimedOut as exc:
                    runtime._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except Exception as exc:
                    if not runtime._try_replan(
                        result,
                        result.resolved_request or result.request,
                        index,
                        step_run,
                        step,
                        exc,
                        completed,
                        completed_results,
                        replan_count,
                        deadline,
                    ):
                        runtime._block_remaining_steps(result.steps, index + 1, step.id, str(exc))
                        raise
                    replan_count += 1
                    index += 1
            result.status = RunStatus.COMPLETED
            result.answer = runtime._compose_answer(result)
            runtime._conversation_store.clear_pending(result.session_id or "default")
            runtime._conversation_store.save_completed(
                result.session_id or "default", result.resolved_request or result.request
            )
            runtime._remember(result)
        except RunCancelled as exc:
            result.status = RunStatus.CANCELLED
            result.error = str(exc)
            _runtime_module._record_run_failure(result, exc, phase="control")
        except RunTimedOut as exc:
            result.status = RunStatus.TIMED_OUT
            result.error = str(exc)
            _runtime_module._record_run_failure(result, exc, phase="control")
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
            _runtime_module._record_run_failure(result, exc)
            result.answer = runtime._answer_composer.compose_failure(result)
        runtime._state_store.save(result)
        runtime._emit_run_event(result)
        return result
