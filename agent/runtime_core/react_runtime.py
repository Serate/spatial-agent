"""Runtime bridge for bounded, one-action-at-a-time ReAct execution.

The bridge owns incremental TaskPlan materialization and delegates every tool
effect to the existing Runtime execution seam.  The synchronous lifecycle only
selects this module; it does not duplicate ToolRegistry, policy, retry, result,
event, or answer behavior.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from agent.errors import ClarificationNeeded, RequestRejected, ToolError
from agent.evidence.revalidation import build_evidence_binding
from agent.models import PlanStep, RunStatus, StepRun, TaskPlan
from agent.result_completeness import build_result_completeness
from agent.react import (
    ReactLoop,
    ReactToolOutcome,
    build_react_run_evidence,
    invoke_react_decider,
    summarize_tool_result,
)

from .plan_evidence import build_plan_evidence
from .projection import resolve_result_references


_LIFECYCLE_STAGE_COUNT = 7


class RuntimeReactExecution:
    """Connect one ReAct loop to an injected AgentRuntime instance."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def run(self, context: Any, *, resume: bool = False) -> None:
        runtime = self._runtime
        result = _result(context)
        settings = runtime._agent_settings
        allowed_tools = tuple(runtime._registry.names)
        tool_catalog = runtime._registry.definition_summary(allowed_tools)
        network_enabled = bool(
            settings.get("web_search_enabled", True)
            and settings.get("web_mode", "allowlist") != "off"
        )
        tool_proposals_enabled = bool(
            settings.get("tool_proposals_enabled", True)
        )
        proposal_validator = getattr(runtime, "_proposal_validator", None)
        if resume:
            initial_decision = None
            initial_history, initial_evidence, initial_action_count, start_turn = (
                self._resume_state(result)
            )
            runtime._emit_progress_event(
                result.run_id,
                phase="plan",
                kind="stage_completed",
                status=RunStatus.EXECUTING.value,
                message="已恢复审批通过的运行，继续生成下一步动作",
                data={
                    "stage_index": 3,
                    "stage_count": _LIFECYCLE_STAGE_COUNT,
                    "reason_code": "tool_approval_accepted_resume",
                },
            )
        else:
            initial_decision = self._initial_decision(
                context,
                allowed_tools=allowed_tools,
                tool_catalog=tool_catalog,
                network_enabled=network_enabled,
                tool_proposals_enabled=tool_proposals_enabled,
            )
            initial_history = ()
            initial_evidence = ()
            initial_action_count = 0
            start_turn = 0
        result.status = RunStatus.EXECUTING
        self._emit_stage_starts(context)

        prepared: Dict[str, tuple[PlanStep, TaskPlan]] = {}
        validation_announced = False

        def validate_action(
            decision: Mapping[str, Any], turn_index: int, action_id: str
        ) -> None:
            nonlocal validation_announced
            runtime._check_control(result.run_id, context.deadline)
            action = str(decision.get("action") or "")
            if action == "call_tool":
                prepared[action_id] = self._prepare_tool_action(
                    context,
                    decision,
                    turn_index=turn_index,
                    action_id=action_id,
                )
            elif action == "search":
                prepared[action_id] = self._prepare_search_action(
                    context,
                    decision,
                    turn_index=turn_index,
                    action_id=action_id,
                )
            elif action == "finish":
                self._prepare_finish(context, decision)
            if not validation_announced:
                validation_announced = True
                runtime._emit_progress_event(
                    result.run_id,
                    phase="validate",
                    kind="stage_completed",
                    status=RunStatus.EXECUTING.value,
                    message="动作校验完成，可以继续",
                    data={
                        "stage_index": 4,
                        "stage_count": _LIFECYCLE_STAGE_COUNT,
                    },
                )

        def execute_tool(
            decision: Mapping[str, Any], turn_index: int, action_id: str
        ) -> ReactToolOutcome:
            del decision, turn_index
            prepared_action = prepared.pop(action_id, None)
            if prepared_action is None:
                raise ToolError(
                    "validated ReAct action is unavailable",
                    category="validation",
                    code="react_action_not_prepared",
                    retryable=False,
                )
            return self._execute_tool_action(context, *prepared_action)

        def execute_search(
            decision: Mapping[str, Any], turn_index: int, action_id: str
        ) -> ReactToolOutcome:
            del decision, turn_index
            prepared_action = prepared.pop(action_id, None)
            if prepared_action is None:
                raise ToolError(
                    "validated ReAct search action is unavailable",
                    category="validation",
                    code="react_action_not_prepared",
                    retryable=False,
                )
            return self._execute_tool_action(context, *prepared_action)

        def validate_proposal(
            decision: Mapping[str, Any], turn_index: int, action_id: str
        ) -> Mapping[str, Any]:
            del turn_index, action_id
            if proposal_validator is None:
                return {
                    "status": "unavailable",
                    "reason_code": "sandbox_unavailable",
                }
            method = getattr(proposal_validator, "validate", None)
            if not callable(method):
                raise ToolError(
                    "tool proposal validator is unavailable",
                    category="validation",
                    code="proposal_validator_unavailable",
                    retryable=False,
                )
            return method(
                decision.get("proposal"),
                existing_tools=runtime._registry.names,
            )

        loop = ReactLoop(
            runtime._planner,
            allowed_tools=allowed_tools,
            tool_catalog=tool_catalog,
            max_turns=int(settings.get("react_max_turns") or 8),
            max_actions=int(settings.get("react_max_actions") or 12),
            network_enabled=network_enabled,
            tool_proposals_enabled=tool_proposals_enabled,
            budget=context.budget,
            progress=context.progress,
            control_check=lambda: runtime._check_control(
                result.run_id, context.deadline
            ),
            on_event=lambda kind, payload: self._emit_react_event(
                context, kind, payload
            ),
        )
        outcome = loop.run(
            context.resolved_request,
            context=context.context_packet.payload,
            initial_decision=initial_decision,
            initial_history=initial_history,
            initial_evidence=initial_evidence,
            initial_action_count=initial_action_count,
            start_turn=start_turn,
            validate_action=validate_action,
            execute_tool=execute_tool,
            execute_search=execute_search,
            validate_proposal=validate_proposal,
        )
        result.react_evidence = build_react_run_evidence(
            outcome.evidence,
            state=outcome.state,
            action_count=outcome.action_count,
            final_decision=outcome.final_decision,
            reason_code=outcome.reason_code,
            final_summary=outcome.final_message,
        )
        if result.plan is not None:
            context.candidate_plan = result.plan
            self._record_plan_evidence(context)
        runtime._state_store.save(result)
        return self._finish_outcome(context, outcome)

    @staticmethod
    def _resume_state(result: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
        """Rebuild only safe ReAct state needed after an approval decision."""

        evidence = getattr(result, "react_evidence", None)
        turns = evidence.get("turns") if isinstance(evidence, Mapping) else []
        history: list[dict[str, Any]] = []
        safe_evidence: list[dict[str, Any]] = []
        for item in turns if isinstance(turns, list) else []:
            if not isinstance(item, Mapping):
                continue
            safe_evidence.append(dict(item))
            decision = item.get("decision")
            if not isinstance(decision, Mapping):
                continue
            entry: dict[str, Any] = {
                "turn_index": item.get("turn_index"),
                "action_id": item.get("action_id"),
                "action": decision.get("action"),
                "tool_name": decision.get("tool_name"),
                "result_ref": item.get("result_ref"),
                "output_type": decision.get("output_type"),
                "summary": decision.get("summary") or item.get("reason_code"),
            }
            history.append({key: value for key, value in entry.items() if value is not None})
        # Approval is a durable control fact, not a completed tool result. It
        # belongs in the bounded model history so a resumed model knows that
        # the proposal is already accepted and registered. Keep this
        # projection source-free: no proposal code, prompt, example arguments,
        # or model response crosses the resume boundary.
        action_receipt = getattr(result, "action_receipt", None)
        approval = (
            action_receipt.get("approval")
            if isinstance(action_receipt, Mapping)
            and isinstance(action_receipt.get("approval"), Mapping)
            else {}
        )
        if approval.get("status") == "approved":
            tool_name = approval.get("name")
            approval_id = approval.get("approval_id")
            if isinstance(tool_name, str) and tool_name.strip():
                history.append(
                    {
                        "action_id": (
                            "approval-" + str(approval_id).strip()[:96]
                            if isinstance(approval_id, str) and approval_id.strip()
                            else "approval-accepted"
                        ),
                        "action": "tool_approval_accepted",
                        "tool_name": tool_name.strip()[:96],
                        "summary": "工具提案已获批准并注册，可以直接调用该工具",
                    }
                )
        turn_count = evidence.get("turn_count", len(safe_evidence)) if isinstance(evidence, Mapping) else len(safe_evidence)
        action_count = evidence.get("action_count", 0) if isinstance(evidence, Mapping) else 0
        if isinstance(turn_count, bool) or not isinstance(turn_count, int):
            turn_count = len(safe_evidence)
        if isinstance(action_count, bool) or not isinstance(action_count, int):
            action_count = 0
        return history[-32:], safe_evidence[-32:], max(0, action_count), max(0, turn_count)

    def _initial_decision(
        self,
        context: Any,
        *,
        allowed_tools: tuple[str, ...],
        tool_catalog: Mapping[str, Any],
        network_enabled: bool,
        tool_proposals_enabled: bool,
    ) -> Mapping[str, Any]:
        runtime = self._runtime
        result = _result(context)
        if context.progress is not None:
            context.progress.start_phase(
                "plan",
                status=RunStatus.PLANNING.value,
                message="正在生成首个受控动作",
                emit_event=False,
            )
        runtime._check_control(result.run_id, context.deadline)
        runtime._emit_progress_event(
            result.run_id,
            phase="plan",
            kind="stage_started",
            status=RunStatus.PLANNING.value,
            message="正在生成首个受控动作",
            data={"stage_index": 3, "stage_count": _LIFECYCLE_STAGE_COUNT},
        )
        decision = invoke_react_decider(
            runtime._planner,
            context.resolved_request,
            context=context.context_packet.payload,
            history=(),
            allowed_tools=allowed_tools,
            tool_catalog=tool_catalog,
            network_enabled=network_enabled,
            tool_proposals_enabled=tool_proposals_enabled,
            budget=context.budget,
            progress=context.progress,
        )
        runtime._check_control(result.run_id, context.deadline)
        self._record_planner_metrics(result)
        runtime._emit_progress_event(
            result.run_id,
            phase="plan",
            kind="stage_completed",
            status=RunStatus.PLANNING.value,
            message="首个候选动作已生成，正在校验",
            data={"stage_index": 3, "stage_count": _LIFECYCLE_STAGE_COUNT},
        )
        return decision

    def _emit_stage_starts(self, context: Any) -> None:
        result = _result(context)
        for phase, message, stage_index in (
            ("validate", "正在校验动作和执行条件", 4),
            ("execute", "开始逐步执行分析动作", 5),
        ):
            # ReAct uses the same coordinator as the ordinary lifecycle. The
            # visible stage events below remain the compatibility surface; the
            # coordinator call only switches the heartbeat phase.
            if context.progress is not None:
                context.progress.start_phase(
                    phase,
                    status=RunStatus.EXECUTING.value,
                    message=message,
                    emit_event=False,
                )
            self._runtime._emit_progress_event(
                result.run_id,
                phase=phase,
                kind="stage_started",
                status=RunStatus.EXECUTING.value,
                message=message,
                data={
                    "stage_index": stage_index,
                    "stage_count": _LIFECYCLE_STAGE_COUNT,
                },
            )

    def _prepare_tool_action(
        self,
        context: Any,
        decision: Mapping[str, Any],
        *,
        turn_index: int,
        action_id: str,
    ) -> tuple[PlanStep, TaskPlan]:
        del turn_index
        runtime = self._runtime
        result = _result(context)
        refresh_tools = getattr(runtime._execution_policy_resolver, "refresh_known_tools", None)
        if callable(refresh_tools):
            refresh_tools(runtime._registry.names)
        tool = str(decision.get("tool_name") or "")
        arguments = decision.get("arguments")
        if not tool or not isinstance(arguments, dict):
            raise ToolError(
                "ReAct tool action is incomplete",
                category="validation",
                code="react_tool_action_invalid",
                retryable=False,
            )
        dependencies = _react_dependencies(decision, arguments)
        if any(item not in context.completed for item in dependencies):
            raise ToolError(
                "ReAct action references an unavailable result",
                category="validation",
                code="react_dependency_unavailable",
                retryable=False,
            )
        try:
            resolved_arguments = resolve_result_references(
                arguments, context.completed_results
            )
            runtime._registry.validate_arguments(tool, resolved_arguments)
        except ToolError as exc:
            raise ToolError(
                "ReAct tool arguments failed schema validation",
                category="validation",
                code="tool_arguments_invalid",
                retryable=False,
            ) from exc
        runtime._enforce_preflight_policy(
            tool,
            resolved_arguments,
            context.completed_results,
        )
        step = PlanStep(action_id, tool, dict(arguments), dependencies)
        existing_steps = list(result.plan.steps) if result.plan is not None else []
        current_output = (
            str(result.plan.output.get("type") or "")
            if result.plan is not None
            else ""
        )
        registry_output_type = str(
            runtime._registry.result_type_for_tool(
                tool,
                resolved_arguments,
            )
            or ""
        ).strip()
        # A checked result already selected by an earlier action, or derived
        # from this tool's operation contract, outranks a model-supplied
        # label. Compatible models occasionally emit a JSON Schema primitive
        # such as ``string`` instead of the public Result id; allowing that
        # label to win would either reject a valid action or weaken the result
        # contract. If no trusted inference exists, the model label remains a
        # candidate and is validated by the normal policy gate below.
        output_type = (
            current_output
            or registry_output_type
            or str(decision.get("output_type") or "").strip()
            or self._inferred_output_type(context)
        )
        if not output_type:
            raise ToolError(
                "ReAct action did not declare a public result type",
                category="validation",
                code="react_result_type_missing",
                retryable=False,
            )
        plan = TaskPlan(
            goal=(context.resolved_request.strip() or "执行受控 Agent 请求")[:240],
            steps=[*existing_steps, step],
            output={"type": output_type[:96]},
        )
        runtime._planning_surface.validate_plan_for_execution(
            plan,
            context.workflow,
            policy_mode="open_react",
        )
        return step, plan

    @staticmethod
    def _inferred_output_type(context: Any) -> str:
        """Use trusted selection metadata when a JSON-only model omits output_type.

        ReAct decisions are allowed to be small, but the final public result
        type must still come from a checked Domain catalog or explicit
        workflow.  This fallback never derives a type from a tool name and
        never accepts a model-invented value.
        """

        packet = getattr(context, "context_packet", None)
        payload = getattr(packet, "payload", None)
        sections = payload.get("sections") if isinstance(payload, Mapping) else None
        if not isinstance(sections, Mapping):
            return ""

        candidates: list[str] = []

        def add(values: Any) -> None:
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, (list, tuple)):
                return
            for value in values[:16]:
                if isinstance(value, str) and value.strip() and value.strip() not in candidates:
                    candidates.append(value.strip()[:96])

        workflow = sections.get("workflow")
        if isinstance(workflow, Mapping):
            add(workflow.get("result_types"))
            output = workflow.get("output")
            if isinstance(output, Mapping):
                add(output.get("type"))

        selection = sections.get("workflow_selection")
        if isinstance(selection, Mapping):
            add(selection.get("result_types"))
            template_id = selection.get("workflow_template_id")
            templates = sections.get("workflow_templates")
            if isinstance(template_id, str) and isinstance(templates, Mapping):
                template = templates.get(template_id)
                if isinstance(template, Mapping):
                    add(template.get("result_types"))
                    output = template.get("output_template")
                    if isinstance(output, Mapping):
                        add(output.get("type"))
            selected_id = selection.get("selected_capability_id")
            for item in selection.get("known_capability_result_types") or []:
                if not isinstance(item, Mapping):
                    continue
                if str(item.get("id") or "") == str(selected_id or ""):
                    add(item.get("result_types"))
            for item in selection.get("candidate_details") or []:
                if not isinstance(item, Mapping):
                    continue
                if str(item.get("id") or "") == str(selected_id or ""):
                    add(item.get("result_types"))
                    detail = item.get("workflow")
                    if isinstance(detail, Mapping):
                        add(detail.get("result_types"))
            for item in selection.get("candidate_summaries") or []:
                if not isinstance(item, Mapping):
                    continue
                if str(item.get("id") or "") == str(selected_id or ""):
                    add(item.get("result_types"))

        return candidates[0] if candidates else ""

    def _prepare_finish(
        self,
        context: Any,
        decision: Mapping[str, Any],
    ) -> None:
        runtime = self._runtime
        result = _result(context)
        message = str(
            decision.get("message")
            or decision.get("summary")
            or "已有足够信息生成回答"
        )[:800]
        if result.plan is None or not result.plan.steps:
            plan = TaskPlan(
                goal=(context.resolved_request.strip() or "回答用户请求")[:240],
                steps=[],
                output={"type": "direct_answer", "message": message},
            )
        else:
            output_type = str(
                result.plan.output.get("type")
                or decision.get("output_type")
                or "unknown"
            )[:96]
            plan = TaskPlan(
                goal=result.plan.goal,
                steps=list(result.plan.steps),
                output={"type": output_type},
                assumptions=list(result.plan.assumptions),
            )
        runtime._planning_surface.validate_plan_for_execution(
            plan,
            context.workflow,
            policy_mode="open_react",
        )
        result.plan = plan
        context.candidate_plan = plan

    def _prepare_search_action(
        self,
        context: Any,
        decision: Mapping[str, Any],
        *,
        turn_index: int,
        action_id: str,
    ) -> tuple[PlanStep, TaskPlan]:
        """Materialize a ReAct search as the ordinary registered tool."""

        arguments: dict[str, Any] = {"query": str(decision.get("query") or "")}
        if decision.get("domains") is not None:
            arguments["domains"] = list(decision.get("domains") or [])
        if decision.get("max_results") is not None:
            arguments["max_results"] = decision["max_results"]
        return self._prepare_tool_action(
            context,
            {
                "tool_name": "web_search",
                "arguments": arguments,
                "output_type": "document_evidence",
            },
            turn_index=turn_index,
            action_id=action_id,
        )

    def _execute_tool_action(
        self,
        context: Any,
        step: PlanStep,
        plan: TaskPlan,
    ) -> ReactToolOutcome:
        runtime = self._runtime
        result = _result(context)
        if context.progress is not None:
            context.progress.start_phase(
                "execute",
                status=RunStatus.EXECUTING.value,
                message="正在执行分析步骤",
                emit_event=False,
            )
        step_run = StepRun(
            step.id,
            step.tool,
            dict(step.args),
            list(step.depends_on),
        )
        result.plan = plan
        context.candidate_plan = plan
        result.steps.append(step_run)
        runtime._emit_progress_event(
            result.run_id,
            phase="execute",
            kind="tool_started",
            status=RunStatus.EXECUTING.value,
            message="正在执行分析步骤",
            data={"step_id": step.id, "tool": step.tool},
        )
        try:
            runtime._execute_step(
                result.run_id,
                context.deadline,
                step_run,
                step,
                context.completed,
                context.completed_results,
                result_projector=lambda tool, value: runtime._project_transient_tool_result(
                    result, tool, value
                ),
                source_request=context.resolved_request,
            )
        except Exception:
            runtime._emit_progress_event(
                result.run_id,
                phase="execute",
                kind="tool_failed",
                status=RunStatus.EXECUTING.value,
                message="分析步骤未完成",
                data={
                    "step_id": step.id,
                    "tool": step.tool,
                    "error_category": step_run.error_category,
                    "reason_code": step_run.error_code,
                    "retryable": step_run.retryable,
                },
            )
            runtime._state_store.save(result)
            raise
        context.completed.add(step.id)
        if step_run.result is not None:
            context.completed_results[step.id] = step_run.result
            self._append_transient_context(
                context,
                getattr(result, "_transient_model_context", None),
            )
        runtime._state_store.save(result)
        runtime._emit_progress_event(
            result.run_id,
            phase="execute",
            kind="tool_completed",
            status=RunStatus.EXECUTING.value,
            message="分析步骤已完成",
            data={
                "step_id": step.id,
                "tool": step.tool,
                "attempts": step_run.attempts,
            },
        )
        tool_result = step_run.result or {}
        return ReactToolOutcome(
            result=tool_result,
            result_ref=step.id,
            output_type=str(plan.output.get("type") or "") or None,
            summary=summarize_tool_result(tool_result),
        )

    @staticmethod
    def _append_transient_context(context: Any, documents: Any) -> None:
        if not isinstance(documents, list) or not documents:
            return
        packet = getattr(context, "context_packet", None)
        payload = getattr(packet, "payload", None)
        if not isinstance(payload, Mapping):
            return
        projected = payload.setdefault("web_documents", [])
        if not isinstance(projected, list):
            projected = []
            payload["web_documents"] = projected
        projected[:] = [
            item
            for item in documents[-8:]
            if isinstance(item, Mapping) and item.get("text")
        ]

    def _record_plan_evidence(self, context: Any) -> None:
        runtime = self._runtime
        result = _result(context)
        if result.plan is None:
            return
        result.plan_evidence = build_plan_evidence(
            result.plan,
            context.workflow,
            context.context_packet,
            planner_kind=type(runtime._planner).__name__,
        )
        result.plan_evidence["plan_policy"] = runtime._plan_policy_evidence(
            result.plan,
            context.workflow,
            policy_mode="open_react",
            state="accepted",
            reason_code="react_plan_accepted",
            repair_lineage=result.replan_events,
        )
        result.plan_evidence["execution_policy"] = runtime._execution_policy_evidence(
            result.plan,
            context.workflow,
            policy_mode="open_react",
        )
        result.plan_evidence["evidence_binding"] = build_evidence_binding(
            context.context_packet.payload
        )
        self._record_planner_metrics(result)

    def _record_planner_metrics(self, result: Any) -> None:
        """Retain successful model evidence across later ReAct attempts.

        Planner adapters expose the metrics of their latest provider call.
        A later ReAct turn may time out after an earlier turn already
        succeeded, but replacing the result snapshot with that failure would
        make the public model evidence falsely claim that no model call
        succeeded. Keep the latest successful snapshot while allowing a
        later success to refresh it; ReAct evidence still records the later
        bounded failure and recovery decision.
        """

        metrics = self._runtime._planner_metrics()
        if not isinstance(metrics, Mapping):
            return
        current = getattr(result, "planner_metrics", None)
        if (
            current is None
            or not _planner_metrics_succeeded(current)
            or _planner_metrics_succeeded(metrics)
        ):
            result.planner_metrics = dict(metrics)

    def _finish_outcome(self, context: Any, outcome: Any) -> bool:
        runtime = self._runtime
        result = _result(context)
        if outcome.state == "clarification":
            raise ClarificationNeeded(
                outcome.final_message or "需要补充信息后继续",
                {
                    "schema_version": "spatial-agent.clarification.v1",
                    "state": "react_clarification",
                    "next_actions": ["补充缺失信息后继续"],
                },
            )
        if outcome.state == "rejected":
            raise RequestRejected(outcome.final_message or "请求未通过策略校验")
        if outcome.state == "awaiting_approval":
            result.status = RunStatus.WAITING_FOR_DECISION
            proposal_receipt = dict(outcome.proposal_receipt or {})
            approval = runtime._approval_store.create_from_receipt(
                proposal_receipt,
                domain_id=runtime.domain_id,
                run_id=result.run_id,
            )
            result.action_receipt = {
                "schema_version": "spatial-agent.tool-proposal-action.v1",
                "state": "awaiting_approval",
                "run_id": result.run_id,
                "proposal_version": approval.proposal_version,
                "receipt_fingerprint": approval.receipt_fingerprint,
                "receipt": proposal_receipt,
                "approval": approval.as_dict(),
            }
            runtime._emit_progress_event(
                result.run_id,
                phase="execute",
                kind="run_waiting",
                status=RunStatus.WAITING_FOR_DECISION.value,
                message="工具提案已验证，等待人工审批",
                data={
                    "reason_code": "react_tool_proposal_awaiting_approval",
                    "action_count": outcome.action_count,
                    "completeness": {
                        **build_result_completeness(result.to_dict()),
                    },
                },
                terminal=False,
            )
            runtime._state_store.save(result)
            return False
        if outcome.state not in {"finished", "partial"}:
            raise ToolError(
                "ReAct execution did not complete",
                category=outcome.error_category or "execution",
                code=(
                    outcome.error_code
                    or outcome.reason_code
                    or "react_execution_blocked"
                ),
                retryable=outcome.retryable,
            )
        runtime._emit_progress_event(
            result.run_id,
            phase="execute",
            kind="stage_completed",
            status=RunStatus.EXECUTING.value,
            message=(
                "分析动作已部分收束"
                if outcome.state == "partial"
                else "分析动作已执行完成"
            ),
            data={
                "stage_index": 5,
                "stage_count": _LIFECYCLE_STAGE_COUNT,
                "summary": "{} 个动作".format(outcome.action_count),
                "completion_state": (
                    "partial" if outcome.state == "partial" else "complete"
                ),
                "stop_reason": outcome.reason_code,
            },
        )
        return True

    def _emit_react_event(
        self,
        context: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> None:
        result = _result(context)
        messages = {
            "react_turn_started": "正在判断下一步动作",
            "react_action_accepted": "动作已通过校验",
            "react_action_completed": "动作已完成",
            "react_action_blocked": "动作未通过执行门禁",
            "react_finished": "逐步分析已收敛",
            "react_waiting_for_approval": "工具提案已验证，等待人工审批",
        }
        self._runtime._emit_progress_event(
            result.run_id,
            phase="execute",
            kind=kind,
            status=result.status.value,
            message=messages.get(kind, "Agent 状态已更新"),
            data=_react_event_data(payload),
            terminal=False,
        )


def _result(context: Any) -> Any:
    result = getattr(context, "result", None)
    if result is None:
        raise RuntimeError("lifecycle result has not been initialized")
    return result


def _react_dependencies(
    decision: Mapping[str, Any], arguments: Mapping[str, Any]
) -> list[str]:
    dependencies: list[str] = []
    for item in decision.get("depends_on") or []:
        text = str(item or "").strip()[:96]
        if text and text not in dependencies:
            dependencies.append(text)

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            source = value.get("$from")
            if isinstance(source, str):
                text = source.strip()[:96]
                if text and text not in dependencies:
                    dependencies.append(text)
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(arguments)
    return dependencies[:16]


def _react_event_data(payload: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in (
        "turn_index",
        "action_id",
        "validation_state",
        "result_ref",
        "output_type",
        "action_count",
        "max_actions",
        "max_turns",
        "reason_code",
        "summary",
    ):
        if payload.get(key) is not None:
            result[key] = payload[key]
    decision = payload.get("decision")
    if isinstance(decision, Mapping):
        if decision.get("action"):
            result["action"] = decision["action"]
        if decision.get("tool_name"):
            result["tool"] = decision["tool_name"]
        for key in ("output_type", "summary"):
            if decision.get(key) and key not in result:
                result[key] = decision[key]
    return result


def _planner_metrics_succeeded(value: Any) -> bool:
    """Identify a usable planner snapshot without trusting arbitrary fields."""

    if not isinstance(value, Mapping) or not value:
        return False
    status = str(value.get("status") or "").strip().lower()
    if status in {
        "error",
        "failed",
        "failure",
        "timeout",
        "timed_out",
        "unavailable",
    }:
        return False
    if value.get("error_type"):
        return False
    if status in {"success", "completed", "ok"}:
        return True
    return bool(value.get("execution_mode") or value.get("provider"))


__all__ = ["RuntimeReactExecution"]
