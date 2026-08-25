"""Synchronous Runtime run lifecycle behind a small compatibility seam.

The public Runtime still exposes one ``run`` method, but the implementation
is deliberately organized as explicit lifecycle stages.  The private context
keeps the stages coupled through one state object instead of growing a second
set of public methods or implicit module globals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, Mapping, Optional, Set

from ..conversation_turn import build_conversation_turn, resolve_turn_mode
from ..decision_lifecycle import DecisionRequest
from ..domain_contract import (
    clarification_details as resolve_clarification_details,
    extract_request_facts,
)
from ..evidence_revalidation import (
    build_evidence_binding,
    build_evidence_revalidation_gate,
)
from ..errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from ..models import AgentRunResult, RunStatus, StepRun, TaskPlan


@dataclass
class _LifecycleContext:
    """Private state shared by the stages of one synchronous run.

    This is intentionally not part of the persisted/public contract.  It
    prevents each stage from receiving a growing list of loosely related
    arguments while keeping state ownership with the Runtime adapter.
    """

    request: str
    session_id: str
    timeout_seconds: Optional[float]
    run_id: Optional[str]
    workflow: Optional[Mapping[str, Any]]
    validated_plan: Optional[TaskPlan]
    expected_plan_fingerprint: Optional[str]
    expected_evidence_fingerprint: Optional[str]
    require_confirmation: bool
    decision_evidence: Optional[Dict[str, Any]]
    decision_id: Optional[str]
    decision_version: Optional[int]
    decision_input: Optional[Mapping[str, Any]]
    decision_ttl_seconds: Optional[float]
    resolved_request_override: Optional[str]
    deadline: Optional[float] = None
    pending: Any = None
    turn_advice: Mapping[str, Any] = field(default_factory=dict)
    resolved_request: str = ""
    request_facts: Any = None
    resolved_run_id: str = ""
    result: Optional[AgentRunResult] = None
    context_packet: Any = None
    candidate_plan: Optional[TaskPlan] = None
    repair_event: Optional[Dict[str, Any]] = None
    decision_result: Optional[AgentRunResult] = None
    completed: Set[str] = field(default_factory=set)
    completed_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    replan_count: int = 0


class RuntimeRunLifecycle:
    """Own one synchronous run lifecycle for an injected Runtime adapter."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def run(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        run_id: Optional[str] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        validated_plan: Optional[TaskPlan] = None,
        expected_plan_fingerprint: Optional[str] = None,
        expected_evidence_fingerprint: Optional[str] = None,
        require_confirmation: bool = False,
        decision_evidence: Optional[Dict[str, Any]] = None,
        decision_id: Optional[str] = None,
        decision_version: Optional[int] = None,
        decision_input: Optional[Mapping[str, Any]] = None,
        decision_ttl_seconds: Optional[float] = 1800.0,
        resolved_request_override: Optional[str] = None,
    ) -> AgentRunResult:
        """Run the explicit resolve → clarify → plan → execute lifecycle."""

        context = self._resolve(
            request=request,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
            workflow=workflow,
            validated_plan=validated_plan,
            expected_plan_fingerprint=expected_plan_fingerprint,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            require_confirmation=require_confirmation,
            decision_evidence=decision_evidence,
            decision_id=decision_id,
            decision_version=decision_version,
            decision_input=decision_input,
            decision_ttl_seconds=decision_ttl_seconds,
            resolved_request_override=resolved_request_override,
        )
        if context.decision_result is not None:
            return context.decision_result

        self._clarify(context)
        try:
            self._plan(context)
            self._validate_and_repair(context)
            if self._await_confirmation(context):
                return self._evidence_and_finalize(context)
            if self._answer_directly(context):
                return self._evidence_and_finalize(context)
            self._execute(context)
            self._answer(context)
        except ClarificationNeeded as exc:
            self._handle_failure(context, exc)
        except RequestRejected as exc:
            self._handle_failure(context, exc)
        except RunCancelled as exc:
            self._handle_failure(context, exc)
        except RunTimedOut as exc:
            self._handle_failure(context, exc)
        except Exception as exc:
            self._handle_failure(context, exc)
        return self._evidence_and_finalize(context)

    # ------------------------------------------------------------------
    # Resolve and clarify
    # ------------------------------------------------------------------

    def _resolve(self, **values: Any) -> _LifecycleContext:
        """Resolve the conversational turn before creating a Result."""

        runtime = self._runtime
        context = _LifecycleContext(**values)
        if context.timeout_seconds is not None and context.timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        if context.decision_ttl_seconds is not None and context.decision_ttl_seconds <= 0:
            raise ToolError("decision_ttl_seconds must be positive")

        context.deadline = (
            perf_counter() + context.timeout_seconds
            if context.timeout_seconds is not None
            else None
        )
        context.pending = runtime._conversation_store.get_pending(context.session_id)
        context.turn_advice = resolve_turn_mode(
            runtime._domain_pack,
            context.request,
            pending_request=(
                context.pending.request if context.pending is not None else None
            ),
            pending_error=(
                context.pending.error if context.pending is not None else None
            ),
        )
        if context.resolved_request_override is not None:
            if (
                not isinstance(context.resolved_request_override, str)
                or not context.resolved_request_override.strip()
            ):
                raise ToolError("resolved_request_override must be a non-empty string")
            context.resolved_request = context.resolved_request_override.strip()
        else:
            context.resolved_request = runtime._resolve_request(
                context.request,
                context.session_id,
                pending=context.pending,
                turn_advice=context.turn_advice,
            )
        context.request_facts = extract_request_facts(
            runtime._domain_pack, context.resolved_request
        )
        context.resolved_run_id = context.run_id or str(uuid.uuid4())
        if context.decision_id is not None:
            existing = runtime._state_store.get(context.resolved_run_id)
            if existing is None:
                raise ToolError(
                    "decision subject run not found: " + context.resolved_run_id
                )
            context.decision_result = runtime._resume_decision(
                existing,
                decision_id=str(context.decision_id),
                decision_version=context.decision_version,
                timeout_seconds=context.timeout_seconds,
            )
        return context

    def _clarify(self, context: _LifecycleContext) -> None:
        """Create and persist the initial planning Result/context snapshot."""

        runtime = self._runtime
        run_span_id = uuid.uuid4().hex[:16]
        runtime._run_span_ids[context.resolved_run_id] = run_span_id
        pending = context.pending
        advice = context.turn_advice
        context.result = AgentRunResult(
            run_id=context.resolved_run_id,
            status=RunStatus.PLANNING,
            request=context.request,
            session_id=context.session_id,
            conversation_turn=build_conversation_turn(
                context.request,
                context.resolved_request,
                session_id=context.session_id,
                mode=str(advice.get("mode") or "unknown"),
                source=str(advice.get("source") or "runtime"),
                pending_request=(
                    pending.request
                    if context.resolved_request_override is None
                    and pending is not None
                    and str(advice.get("mode"))
                    in {"clarification_reply", "follow_up", "decision_reply"}
                    else None
                ),
                pending_available=pending is not None,
                reason_code=advice.get("reason_code"),
            ),
            domain_id=runtime.domain_id,
            runtime_context=runtime.runtime_context(),
            resolved_request=context.resolved_request,
            request_facts=context.request_facts.as_context_dict(),
            workflow=dict(context.workflow) if context.workflow is not None else None,
            decision_evidence=(
                dict(context.decision_evidence) if context.decision_evidence else None
            ),
        )
        context.context_packet = runtime._build_context_packet(
            context.request,
            context.resolved_request,
            context.session_id,
            context.workflow,
            request_facts=context.request_facts,
        )
        context.result.context_evidence = context.context_packet.evidence
        runtime._state_store.save(context.result)

    # ------------------------------------------------------------------
    # Plan and validate/repair
    # ------------------------------------------------------------------

    def _plan(self, context: _LifecycleContext) -> None:
        runtime = self._runtime
        result = self._result(context)
        runtime._check_control(result.run_id, context.deadline)
        if context.validated_plan is not None:
            if not isinstance(context.validated_plan, TaskPlan):
                raise ToolError("validated execution plan is invalid")
            # This is the execution-binding seam: planner selection has
            # already crossed the Composite gates, so no Domain Planner is
            # invoked again for this component.
            context.candidate_plan = context.validated_plan
        else:
            runtime._require_workflow_selection(context.context_packet, context.workflow)
            context.candidate_plan = runtime._plan(
                context.resolved_request,
                context.workflow,
                context.context_packet,
            )
        result.plan = context.candidate_plan
        runtime._check_control(result.run_id, context.deadline)

    def _validate_and_repair(self, context: _LifecycleContext) -> None:
        """Validate the candidate and build the same plan/evidence gates."""

        runtime = self._runtime
        result = self._result(context)
        if context.candidate_plan is None:
            raise ToolError("planner returned no plan")
        plan, context.repair_event = runtime._validate_or_repair_plan(
            context.candidate_plan,
            context.resolved_request,
            context.workflow,
            deadline=context.deadline,
            result=result,
            run_id=result.run_id,
            context_packet=context.context_packet,
        )
        result.plan = plan
        from .. import runtime as _runtime_module

        result.plan_evidence = _runtime_module._build_plan_evidence(
            plan,
            context.workflow,
            context.context_packet,
            planner_kind=type(runtime._planner).__name__,
        )
        result.plan_evidence["plan_policy"] = runtime._plan_policy_evidence(
            plan,
            context.workflow,
            state="accepted",
            reason_code="accepted",
            repair_lineage=result.replan_events,
        )
        result.plan_evidence["execution_policy"] = runtime._execution_policy_evidence(plan)
        result.plan_evidence["evidence_binding"] = build_evidence_binding(
            context.context_packet.payload
        )
        self._validate_fingerprints(context)
        result.planner_metrics = runtime._planner_metrics()

    def _validate_fingerprints(self, context: _LifecycleContext) -> None:
        result = self._result(context)
        if context.expected_plan_fingerprint is not None:
            actual_fingerprint = (result.plan_evidence.get("plan_identity") or {}).get(
                "fingerprint"
            )
            result.plan_evidence["expected_plan_fingerprint"] = str(
                context.expected_plan_fingerprint
            )
            result.plan_evidence["plan_fingerprint_match"] = (
                str(context.expected_plan_fingerprint) == str(actual_fingerprint)
            )
            if not result.plan_evidence["plan_fingerprint_match"]:
                raise ToolError("preview plan fingerprint mismatch")
        if context.expected_evidence_fingerprint is not None:
            current_binding = result.plan_evidence["evidence_binding"]
            revalidation = build_evidence_revalidation_gate(
                context.expected_evidence_fingerprint,
                current_binding,
            )
            result.plan_evidence["expected_evidence_fingerprint"] = str(
                context.expected_evidence_fingerprint
            )[:96]
            result.plan_evidence["evidence_fingerprint_match"] = (
                revalidation["state"] == "current"
            )
            result.plan_evidence["evidence_revalidation"] = revalidation
            if not result.plan_evidence["evidence_fingerprint_match"]:
                raise ToolError(
                    "preview evidence fingerprint mismatch",
                    category="evidence",
                    code=(
                        "preview_evidence_changed"
                        if revalidation["state"] == "changed"
                        else "preview_evidence_unavailable"
                    ),
                    retryable=False,
                )

    def _await_confirmation(self, context: _LifecycleContext) -> bool:
        if not context.require_confirmation:
            return False
        runtime = self._runtime
        result = self._result(context)
        if runtime._decision_store is None:
            raise ToolError("decision store is unavailable")
        fingerprint = str(
            (result.plan_evidence.get("plan_identity") or {}).get("fingerprint", "")
        )
        if not fingerprint:
            raise ToolError("plan fingerprint is unavailable for confirmation")
        if result.plan is None:
            raise ToolError("validated plan is unavailable for confirmation")
        result.steps = [
            StepRun(step.id, step.tool, step.args, list(step.depends_on))
            for step in result.plan.steps
        ]
        record = runtime._decision_store.create(
            DecisionRequest(
                subject_kind="run",
                subject_id=result.run_id,
                domain_id=runtime.domain_id,
                session_id=context.session_id,
                decision_kind="plan_confirmation",
                prompt="是否批准执行当前计划？",
                options=("approve", "reject"),
                subject_fingerprint=fingerprint,
                input_data=dict(context.decision_input or {}),
                expires_at=(
                    datetime.now(timezone.utc).timestamp()
                    + float(context.decision_ttl_seconds)
                    if context.decision_ttl_seconds is not None
                    else None
                ),
            )
        )
        result.status = RunStatus.WAITING_FOR_DECISION
        result.decision_evidence = record.evidence()
        return True

    # ------------------------------------------------------------------
    # Execute and answer
    # ------------------------------------------------------------------

    def _execute(self, context: _LifecycleContext) -> None:
        runtime = self._runtime
        result = self._result(context)
        if result.plan is None:
            raise ToolError("validated plan is unavailable for execution")
        result.status = RunStatus.EXECUTING
        result.steps = [
            StepRun(step.id, step.tool, step.args, list(step.depends_on))
            for step in result.plan.steps
        ]
        context.replan_count = 1 if context.repair_event is not None else 0
        index = 0
        while index < len(result.steps):
            step_run = result.steps[index]
            step = result.plan.steps[index]
            try:
                runtime._check_control(result.run_id, context.deadline)
                runtime._execute_step(
                    result.run_id,
                    context.deadline,
                    step_run,
                    step,
                    context.completed,
                    context.completed_results,
                )
                context.completed.add(step.id)
                if step_run.result is not None:
                    context.completed_results[step.id] = step_run.result
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
                    context.resolved_request,
                    index,
                    step_run,
                    step,
                    exc,
                    context.completed,
                    context.completed_results,
                    context.replan_count,
                    context.deadline,
                ):
                    runtime._block_remaining_steps(
                        result.steps, index + 1, step.id, str(exc)
                    )
                    raise
                context.replan_count += 1
                index += 1

    def _answer_directly(self, context: _LifecycleContext) -> bool:
        result = self._result(context)
        if result.plan is None or result.plan.output.get("type") != "direct_answer":
            return False
        runtime = self._runtime
        result.status = RunStatus.COMPLETED
        result.answer = str(result.plan.output.get("message", ""))
        runtime._conversation_store.clear_pending(context.session_id)
        runtime._conversation_store.save_completed(
            context.session_id, context.resolved_request
        )
        runtime._remember(result)
        return True

    def _answer(self, context: _LifecycleContext) -> None:
        runtime = self._runtime
        result = self._result(context)
        result.status = RunStatus.COMPLETED
        result.answer = runtime._compose_answer(result)
        runtime._remember(result)
        runtime._conversation_store.clear_pending(context.session_id)
        runtime._conversation_store.save_completed(
            context.session_id, context.resolved_request
        )

    # ------------------------------------------------------------------
    # Failure and evidence/finalize
    # ------------------------------------------------------------------

    def _handle_failure(self, context: _LifecycleContext, exc: Exception) -> None:
        runtime = self._runtime
        result = self._result(context)
        from .. import runtime as _runtime_module

        if isinstance(exc, ClarificationNeeded):
            result.status = RunStatus.NEEDS_CLARIFICATION
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=context.candidate_plan,
                    workflow=context.workflow,
                    state="clarification",
                    reason_code="clarification_required",
                    context_packet=context.context_packet,
                    repair_lineage=result.replan_events,
                )
            result.clarification = exc.details or resolve_clarification_details(
                runtime._domain_pack, context.resolved_request
            ) or None
            _runtime_module._record_run_failure(result, exc, phase="planning")
            runtime._conversation_store.save_pending(
                context.session_id, context.resolved_request, result.error
            )
            return
        if isinstance(exc, RequestRejected):
            result.status = RunStatus.REJECTED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=context.candidate_plan,
                    workflow=context.workflow,
                    state="rejected",
                    reason_code="request_rejected",
                    context_packet=context.context_packet,
                    repair_lineage=result.replan_events,
                )
            _runtime_module._record_run_failure(result, exc, phase="planning")
            runtime._conversation_store.clear_pending(context.session_id)
            return
        if isinstance(exc, RunCancelled):
            result.status = RunStatus.CANCELLED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=context.candidate_plan,
                    workflow=context.workflow,
                    state="unavailable",
                    reason_code="run_cancelled_before_plan_evidence",
                    context_packet=context.context_packet,
                    repair_lineage=result.replan_events,
                )
            _runtime_module._record_run_failure(result, exc, phase="control")
            return
        if isinstance(exc, RunTimedOut):
            result.status = RunStatus.TIMED_OUT
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=context.candidate_plan,
                    workflow=context.workflow,
                    state="unavailable",
                    reason_code="run_timeout_before_plan_evidence",
                    context_packet=context.context_packet,
                    repair_lineage=result.replan_events,
                )
            _runtime_module._record_run_failure(result, exc, phase="control")
            return

        result.status = RunStatus.FAILED
        result.error = str(exc)
        if result.plan_evidence is None:
            result.plan_evidence = runtime._failure_plan_evidence(
                plan=context.candidate_plan,
                workflow=context.workflow,
                state=(
                    "rejected" if context.candidate_plan is not None else "unavailable"
                ),
                reason_code=(
                    "plan_validation_rejected"
                    if context.candidate_plan is not None
                    else "planner_failed"
                ),
                context_packet=context.context_packet,
                repair_lineage=result.replan_events,
            )
        _runtime_module._record_run_failure(
            result,
            exc,
            phase="planning" if context.candidate_plan is None else None,
        )
        result.answer = runtime._answer_composer.compose_failure(result)

    def _evidence_and_finalize(self, context: _LifecycleContext) -> AgentRunResult:
        """Complete the evidence/state/event boundary exactly once."""

        runtime = self._runtime
        result = self._result(context)
        if result.planner_metrics is None:
            result.planner_metrics = runtime._planner_metrics()
        runtime._state_store.save(result)
        runtime._emit_run_event(result)
        return result

    @staticmethod
    def _result(context: _LifecycleContext) -> AgentRunResult:
        if context.result is None:
            raise RuntimeError("lifecycle result has not been initialized")
        return context.result
