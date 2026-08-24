"""Synchronous Runtime run lifecycle behind a small compatibility seam.

The lifecycle module owns state transitions and terminal error handling. The
Runtime adapter supplies planning, execution, evidence, storage, and control
ports through the injected owner without changing the public run contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, Mapping, Optional, Set

from ..conversation_turn import build_conversation_turn, resolve_turn_mode
from ..decision_lifecycle import DecisionRequest
from ..domain_contract import clarification_details as resolve_clarification_details, extract_request_facts
from ..evidence_revalidation import build_evidence_binding, build_evidence_revalidation_gate
from ..errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from ..models import AgentRunResult, RunStatus, StepRun, TaskPlan


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
        runtime = self._runtime
        from .. import runtime as _runtime_module
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        if decision_ttl_seconds is not None and decision_ttl_seconds <= 0:
            raise ToolError("decision_ttl_seconds must be positive")
        deadline = perf_counter() + timeout_seconds if timeout_seconds is not None else None
        pending = runtime._conversation_store.get_pending(session_id)
        turn_advice = resolve_turn_mode(
            runtime._domain_pack,
            request,
            pending_request=pending.request if pending is not None else None,
            pending_error=pending.error if pending is not None else None,
        )
        if resolved_request_override is not None:
            if not isinstance(resolved_request_override, str) or not resolved_request_override.strip():
                raise ToolError("resolved_request_override must be a non-empty string")
            resolved_request = resolved_request_override.strip()
        else:
            resolved_request = runtime._resolve_request(
                request,
                session_id,
                pending=pending,
                turn_advice=turn_advice,
            )
        request_facts = extract_request_facts(runtime._domain_pack, resolved_request)
        resolved_run_id = run_id or str(uuid.uuid4())
        if decision_id is not None:
            existing = runtime._state_store.get(resolved_run_id)
            if existing is None:
                raise ToolError("decision subject run not found: " + resolved_run_id)
            return runtime._resume_decision(
                existing,
                decision_id=str(decision_id),
                decision_version=decision_version,
                timeout_seconds=timeout_seconds,
            )
        run_span_id = uuid.uuid4().hex[:16]
        runtime._run_span_ids[resolved_run_id] = run_span_id
        result = AgentRunResult(
            run_id=resolved_run_id,
            status=RunStatus.PLANNING,
            request=request,
            session_id=session_id,
            conversation_turn=build_conversation_turn(
                request,
                resolved_request,
                session_id=session_id,
                mode=str(turn_advice.get("mode") or "unknown"),
                source=str(turn_advice.get("source") or "runtime"),
                pending_request=(
                    pending.request
                    if resolved_request_override is None
                    and pending is not None
                    and str(turn_advice.get("mode"))
                    in {"clarification_reply", "follow_up", "decision_reply"}
                    else None
                ),
                pending_available=pending is not None,
                reason_code=turn_advice.get("reason_code"),
            ),
            domain_id=runtime.domain_id,
            runtime_context=runtime.runtime_context(),
            resolved_request=resolved_request,
            request_facts=request_facts.as_context_dict(),
            workflow=dict(workflow) if workflow is not None else None,
            decision_evidence=dict(decision_evidence) if decision_evidence else None,
        )
        context_packet = runtime._build_context_packet(
            request, resolved_request, session_id, workflow, request_facts=request_facts
        )
        result.context_evidence = context_packet.evidence
        runtime._state_store.save(result)
        candidate_plan: Optional[TaskPlan] = None
        try:
            # Check controls around planning as well as tool dispatch. A
            # direct-answer plan has no step boundary where cancellation or
            # timeout would otherwise be observed.
            runtime._check_control(result.run_id, deadline)
            runtime._require_workflow_selection(context_packet, workflow)
            plan = runtime._plan(resolved_request, workflow, context_packet)
            candidate_plan = plan
            # Preserve the candidate for rejected/clarification evidence even
            # when the plan fails before it becomes executable.
            result.plan = plan
            runtime._check_control(result.run_id, deadline)
            plan, _repair_event = runtime._validate_or_repair_plan(
                plan,
                resolved_request,
                workflow,
                deadline=deadline,
                result=result,
                run_id=result.run_id,
                context_packet=context_packet,
            )
            result.plan = plan
            result.plan_evidence = _runtime_module._build_plan_evidence(
                plan,
                workflow,
                context_packet,
                planner_kind=type(runtime._planner).__name__,
            )
            result.plan_evidence["plan_policy"] = runtime._plan_policy_evidence(
                plan,
                workflow,
                state="accepted",
                reason_code="accepted",
                repair_lineage=result.replan_events,
            )
            result.plan_evidence["execution_policy"] = runtime._execution_policy_evidence(plan)
            result.plan_evidence["evidence_binding"] = build_evidence_binding(
                context_packet.payload
            )
            if expected_plan_fingerprint is not None:
                actual_fingerprint = (result.plan_evidence.get("plan_identity") or {}).get("fingerprint")
                result.plan_evidence["expected_plan_fingerprint"] = str(expected_plan_fingerprint)
                result.plan_evidence["plan_fingerprint_match"] = (
                    str(expected_plan_fingerprint) == str(actual_fingerprint)
                )
                if not result.plan_evidence["plan_fingerprint_match"]:
                    raise ToolError("preview plan fingerprint mismatch")
            if expected_evidence_fingerprint is not None:
                current_binding = result.plan_evidence["evidence_binding"]
                revalidation = build_evidence_revalidation_gate(
                    expected_evidence_fingerprint,
                    current_binding,
                )
                result.plan_evidence["expected_evidence_fingerprint"] = str(
                    expected_evidence_fingerprint
                )[:96]
                result.plan_evidence["evidence_fingerprint_match"] = (
                    revalidation["state"] == "current"
                )
                result.plan_evidence["evidence_revalidation"] = revalidation
                if not result.plan_evidence["evidence_fingerprint_match"]:
                    raise ToolError(
                        "preview evidence fingerprint mismatch",
                        category="evidence",
                        code="preview_evidence_changed"
                        if revalidation["state"] == "changed"
                        else "preview_evidence_unavailable",
                        retryable=False,
                    )
            result.planner_metrics = runtime._planner_metrics()
            if require_confirmation:
                if runtime._decision_store is None:
                    raise ToolError("decision store is unavailable")
                fingerprint = str(
                    (result.plan_evidence.get("plan_identity") or {}).get(
                        "fingerprint", ""
                    )
                )
                if not fingerprint:
                    raise ToolError("plan fingerprint is unavailable for confirmation")
                result.steps = [
                    StepRun(step.id, step.tool, step.args, list(step.depends_on))
                    for step in plan.steps
                ]
                record = runtime._decision_store.create(
                    DecisionRequest(
                        subject_kind="run",
                        subject_id=result.run_id,
                        domain_id=runtime.domain_id,
                        session_id=session_id,
                        decision_kind="plan_confirmation",
                        prompt="是否批准执行当前计划？",
                        options=("approve", "reject"),
                        subject_fingerprint=fingerprint,
                        input_data=dict(decision_input or {}),
                        expires_at=(
                            datetime.now(timezone.utc).timestamp()
                            + float(decision_ttl_seconds)
                            if decision_ttl_seconds is not None
                            else None
                        ),
                    )
                )
                result.status = RunStatus.WAITING_FOR_DECISION
                result.decision_evidence = record.evidence()
                runtime._state_store.save(result)
                runtime._emit_run_event(result)
                return result
            if plan.output.get("type") == "direct_answer":
                result.status = RunStatus.COMPLETED
                result.answer = str(plan.output.get("message", ""))
                runtime._conversation_store.clear_pending(session_id)
                runtime._conversation_store.save_completed(session_id, resolved_request)
                runtime._remember(result)
                runtime._state_store.save(result)
                return result
            result.status = RunStatus.EXECUTING
            result.steps = [
                StepRun(step.id, step.tool, step.args, list(step.depends_on))
                for step in plan.steps
            ]
            completed: Set[str] = set()
            completed_results: Dict[str, Dict[str, Any]] = {}
            # Planning repair and execution replan share one per-run budget.
            replan_count = 1 if _repair_event is not None else 0
            index = 0
            while index < len(result.steps):
                step_run = result.steps[index]
                step = result.plan.steps[index]
                try:
                    runtime._check_control(result.run_id, deadline)
                    runtime._execute_step(result.run_id, deadline, step_run, step, completed, completed_results)
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
                        resolved_request,
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
            runtime._remember(result)
            runtime._conversation_store.clear_pending(session_id)
            runtime._conversation_store.save_completed(session_id, resolved_request)
        except ClarificationNeeded as exc:
            result.status = RunStatus.NEEDS_CLARIFICATION
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="clarification",
                    reason_code="clarification_required",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            result.clarification = exc.details or resolve_clarification_details(
                runtime._domain_pack, resolved_request
            ) or None
            _runtime_module._record_run_failure(result, exc, phase="planning")
            runtime._conversation_store.save_pending(session_id, resolved_request, result.error)
        except RequestRejected as exc:
            result.status = RunStatus.REJECTED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="rejected",
                    reason_code="request_rejected",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            _runtime_module._record_run_failure(result, exc, phase="planning")
            runtime._conversation_store.clear_pending(session_id)
        except RunCancelled as exc:
            result.status = RunStatus.CANCELLED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="unavailable",
                    reason_code="run_cancelled_before_plan_evidence",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            _runtime_module._record_run_failure(result, exc, phase="control")
        except RunTimedOut as exc:
            result.status = RunStatus.TIMED_OUT
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="unavailable",
                    reason_code="run_timeout_before_plan_evidence",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            _runtime_module._record_run_failure(result, exc, phase="control")
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = runtime._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="rejected" if candidate_plan is not None else "unavailable",
                    reason_code=(
                        "plan_validation_rejected"
                        if candidate_plan is not None
                        else "planner_failed"
                    ),
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            _runtime_module._record_run_failure(
                result,
                exc,
                phase="planning" if candidate_plan is None else None,
            )
            result.answer = runtime._answer_composer.compose_failure(result)
        if result.planner_metrics is None:
            result.planner_metrics = runtime._planner_metrics()
        runtime._state_store.save(result)
        runtime._emit_run_event(result)
        return result
