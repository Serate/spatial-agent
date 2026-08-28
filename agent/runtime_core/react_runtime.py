"""Runtime bridge for bounded, one-action-at-a-time ReAct execution.

The bridge owns incremental TaskPlan materialization and delegates every tool
effect to the existing Runtime execution seam.  The synchronous lifecycle only
selects this module; it does not duplicate ToolRegistry, policy, retry, result,
event, or answer behavior.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from agent.errors import ClarificationNeeded, RequestRejected, ToolError
from agent.evidence_revalidation import build_evidence_binding
from agent.models import PlanStep, RunStatus, StepRun, TaskPlan
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

    def run(self, context: Any) -> None:
        runtime = self._runtime
        result = _result(context)
        settings = runtime._agent_settings
        allowed_tools = tuple(runtime._registry.names)
        tool_catalog = runtime._registry.definition_summary(allowed_tools)
        network_enabled = bool(settings.get("web_search_enabled", True))
        tool_proposals_enabled = bool(
            settings.get("tool_proposals_enabled", True)
        )
        initial_decision = self._initial_decision(
            context,
            allowed_tools=allowed_tools,
            tool_catalog=tool_catalog,
            network_enabled=network_enabled,
            tool_proposals_enabled=tool_proposals_enabled,
        )
        result.status = RunStatus.EXECUTING
        self._emit_stage_starts(result)

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

        loop = ReactLoop(
            runtime._planner,
            allowed_tools=allowed_tools,
            tool_catalog=tool_catalog,
            max_turns=int(settings.get("react_max_turns") or 8),
            max_actions=int(settings.get("react_max_actions") or 12),
            network_enabled=network_enabled,
            tool_proposals_enabled=tool_proposals_enabled,
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
            validate_action=validate_action,
            execute_tool=execute_tool,
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
        self._finish_outcome(context, outcome)

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
        )
        runtime._check_control(result.run_id, context.deadline)
        result.planner_metrics = runtime._planner_metrics()
        runtime._emit_progress_event(
            result.run_id,
            phase="plan",
            kind="stage_completed",
            status=RunStatus.PLANNING.value,
            message="首个候选动作已生成，正在校验",
            data={"stage_index": 3, "stage_count": _LIFECYCLE_STAGE_COUNT},
        )
        return decision

    def _emit_stage_starts(self, result: Any) -> None:
        for phase, message, stage_index in (
            ("validate", "正在校验动作和执行条件", 4),
            ("execute", "开始逐步执行分析动作", 5),
        ):
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
        output_type = (
            str(decision.get("output_type") or "").strip()
            or current_output
            or str(runtime._registry.result_type_for_tool(tool) or "").strip()
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
        runtime._planning_surface.validate_plan_for_execution(plan, context.workflow)
        return step, plan

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
                decision.get("output_type")
                or result.plan.output.get("type")
                or "unknown"
            )[:96]
            plan = TaskPlan(
                goal=result.plan.goal,
                steps=list(result.plan.steps),
                output={"type": output_type},
                assumptions=list(result.plan.assumptions),
            )
        runtime._planning_surface.validate_plan_for_execution(plan, context.workflow)
        result.plan = plan
        context.candidate_plan = plan

    def _execute_tool_action(
        self,
        context: Any,
        step: PlanStep,
        plan: TaskPlan,
    ) -> ReactToolOutcome:
        runtime = self._runtime
        result = _result(context)
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
            state="accepted",
            reason_code="react_plan_accepted",
            repair_lineage=result.replan_events,
        )
        result.plan_evidence["execution_policy"] = runtime._execution_policy_evidence(
            result.plan,
            context.workflow,
        )
        result.plan_evidence["evidence_binding"] = build_evidence_binding(
            context.context_packet.payload
        )
        result.planner_metrics = runtime._planner_metrics()

    def _finish_outcome(self, context: Any, outcome: Any) -> None:
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
        if outcome.state != "finished":
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
            message="分析动作已执行完成",
            data={
                "stage_index": 5,
                "stage_count": _LIFECYCLE_STAGE_COUNT,
                "summary": "{} 个动作".format(outcome.action_count),
            },
        )

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


__all__ = ["RuntimeReactExecution"]
