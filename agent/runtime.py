import uuid
import inspect
from threading import Lock
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, Mapping, Optional, Set

from .errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from .answer_composer import AnswerComposer
from .context_engineering import ContextBuilder, ContextPacket
from .memory import FactMemory
from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .planner import Planner
from .replanning import (
    ReplanningPolicy,
    build_replan_event,
    failure_category,
    merge_replanned_plan,
    rule_replan_plan,
)
from .request_model import parse_spatial_request
from .tools import ToolRegistry
from .workflow_templates import WorkflowTemplateError, validate_workflow_plan


class InMemoryStateStore:
    def __init__(self):
        self._runs: Dict[str, AgentRunResult] = {}
        self._cancelled: Set[str] = set()
        self._lock = Lock()

    def save(self, result: AgentRunResult) -> None:
        with self._lock:
            self._runs[result.run_id] = result

    def get(self, run_id: str) -> Optional[AgentRunResult]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, limit: int = 20, session_id: Optional[str] = None):
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            values = list(self._runs.values())
        if session_id:
            values = [item for item in values if item.session_id == session_id]
        values = list(reversed(values[-limit:]))
        return [
            {
                "run_id": item.run_id,
                "session_id": item.session_id,
                "status": item.status.value,
                "request": item.request,
                "answer": item.answer,
                "error": item.error,
                "planner_metrics": item.planner_metrics,
            }
            for item in values
        ]

    def clear_session_runs(self, session_id: str) -> int:
        with self._lock:
            run_ids = [
                run_id for run_id, item in self._runs.items()
                if item.session_id == session_id
            ]
            for run_id in run_ids:
                self._runs.pop(run_id, None)
                self._cancelled.discard(run_id)
        return len(run_ids)

    def request_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.add(run_id)

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancelled

    def clear_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled.discard(run_id)


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
        context_builder: Optional[ContextBuilder] = None,
        max_steps: int = 12,
        max_retries: int = 2,
        replan_policy: Optional[ReplanningPolicy] = None,
        memory: Optional[FactMemory] = None,
    ):
        self._planner = planner
        self._registry = registry
        self._state_store = state_store or InMemoryStateStore()
        self._conversation_store = conversation_store or InMemoryConversationStore()
        self._answer_composer = answer_composer or AnswerComposer()
        self._context_builder = context_builder or ContextBuilder()
        self._max_steps = max_steps
        self._max_retries = max_retries
        self._replan_policy = replan_policy or ReplanningPolicy()
        self._memory = memory
        self._control_lock = Lock()
        self._cancelled_runs: Set[str] = set()

    def run(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        run_id: Optional[str] = None,
        workflow: Optional[Mapping[str, Any]] = None,
    ) -> AgentRunResult:
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        deadline = perf_counter() + timeout_seconds if timeout_seconds is not None else None
        resolved_request = self._resolve_request(request, session_id)
        result = AgentRunResult(
            run_id=run_id or str(uuid.uuid4()),
            status=RunStatus.PLANNING,
            request=request,
            session_id=session_id,
            resolved_request=resolved_request,
            workflow=dict(workflow) if workflow is not None else None,
        )
        memory_section = (
            self._memory.context_section(session_id)
            if self._memory is not None
            else None
        )
        context_packet = self._context_builder.build(
            request=request,
            resolved_request=resolved_request,
            session_id=session_id,
            workflow=workflow,
            available_tools=self._registry.names,
            planner_kind=type(self._planner).__name__,
            spatial_request=parse_spatial_request(resolved_request).as_context_dict(),
            memory_section=memory_section,
        )
        result.context_evidence = context_packet.evidence
        self._state_store.save(result)
        try:
            # Check controls around planning as well as tool dispatch. A
            # direct-answer plan has no step boundary where cancellation or
            # timeout would otherwise be observed.
            self._check_control(result.run_id, deadline)
            plan = self._plan(resolved_request, workflow, context_packet)
            self._check_control(result.run_id, deadline)
            if workflow is not None:
                _validate_runtime_workflow_plan(plan, workflow)
            result.planner_metrics = self._planner_metrics()
            if plan.output.get("type") == "direct_answer":
                result.plan = plan
                result.status = RunStatus.COMPLETED
                result.answer = str(plan.output.get("message", ""))
                self._conversation_store.clear_pending(session_id)
                self._conversation_store.save_completed(session_id, resolved_request)
                self._remember(result)
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
            replan_count = 0
            index = 0
            while index < len(result.steps):
                step_run = result.steps[index]
                step = result.plan.steps[index]
                try:
                    self._check_control(result.run_id, deadline)
                    self._execute_step(result.run_id, deadline, step_run, step, completed, completed_results)
                    completed.add(step.id)
                    if step_run.result is not None:
                        completed_results[step.id] = step_run.result
                    index += 1
                except RunCancelled as exc:
                    self._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except RunTimedOut as exc:
                    self._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except Exception as exc:
                    if not self._try_replan(
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
                        self._block_remaining_steps(result.steps, index + 1, step.id, str(exc))
                        raise
                    replan_count += 1
                    index += 1
            result.status = RunStatus.COMPLETED
            result.answer = self._answer_composer.compose(result)
            self._remember(result)
            self._conversation_store.clear_pending(session_id)
            self._conversation_store.save_completed(session_id, resolved_request)
        except ClarificationNeeded as exc:
            result.status = RunStatus.NEEDS_CLARIFICATION
            result.error = str(exc)
            result.clarification = exc.details
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
            result.answer = self._answer_composer.compose_failure(result)
        if result.planner_metrics is None:
            result.planner_metrics = self._planner_metrics()
        self._state_store.save(result)
        return result

    def clear_session(self, session_id: str) -> None:
        """Clear runtime-only clarification state for a conversation."""
        self._conversation_store.clear_pending(session_id)

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
        request_cancel = getattr(self._state_store, "request_cancel", None)
        if callable(request_cancel):
            request_cancel(run_id)
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
        result.retry_count = int(getattr(result, "retry_count", 0) or 0) + 1
        with self._control_lock:
            self._cancelled_runs.discard(run_id)
        clear_cancel = getattr(self._state_store, "clear_cancel", None)
        if callable(clear_cancel):
            clear_cancel(run_id)
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
            result.answer = self._answer_composer.compose_failure(result)
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

    def _plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]],
        context_packet: ContextPacket,
    ) -> TaskPlan:
        """Pass context to capable planners while preserving old Planner adapters."""
        method = self._planner.plan
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_context = "context" in parameters or any(
            item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
        )
        kwargs = {}
        if workflow is not None:
            kwargs["workflow"] = workflow
        if accepts_context:
            kwargs["context"] = context_packet.payload
        return method(request, **kwargs)

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
        try:
            self._enforce_preflight_policy(step.tool, step.args, completed_results)
        except ToolError as exc:
            step_run.status = "FAILED"
            step_run.error = str(exc)
            step_run.finished_at = _utc_now()
            raise
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

    def _try_replan(
        self,
        result: AgentRunResult,
        request: str,
        index: int,
        step_run: StepRun,
        step: PlanStep,
        exc: Exception,
        completed: Set[str],
        completed_results: Dict[str, Dict[str, Any]],
        replan_count: int,
        deadline: Optional[float],
    ) -> bool:
        """Attempt one adaptive replan round after a failed step.

        Returns True when a valid replacement plan was merged and execution can
        continue; False when the run must fail fast (policy denies, budget
        exhausted, or replanning itself failed).
        """
        if not self._replan_policy.should_replan(
            replan_count=replan_count,
            step_status=step_run.status,
            step_error=str(exc),
        ):
            return False
        completed_steps = [
            {"id": step_id, "tool": self._tool_for_step(result.plan, step_id)}
            for step_id in completed
        ]
        failed_payload = {
            "id": step.id,
            "tool": step.tool,
            "args": dict(step.args),
            "error_category": failure_category(str(exc)),
        }
        feedback = self._replan_policy.feedback_payload(
            request=request,
            completed_steps=completed_steps,
            failed_step=failed_payload,
            remaining_tools=self._registry.names,
            output_type=(result.plan.output or {}).get("type"),
        )
        started = perf_counter()
        try:
            if getattr(self._planner, "capability_rules", None) is not None:
                replacement = rule_replan_plan(failed_payload, completed_results)
            else:
                replacement = self._planner.plan(
                    request, context=_replan_context(feedback)
                )
            merged = merge_replanned_plan(
                result.plan, replacement, failed_step_id=step.id
            )
            # Validate the merged plan only: replacement steps may legitimately
            # depend on original steps that survive in the merged plan, which
            # a standalone validation of the replacement would reject.
            self._validate_plan(merged)
            # Rebuild step runs to match the merged plan: keep runs for steps
            # that still exist (completed ones keep their results, the failed
            # step keeps its FAILED state), create fresh runs for new steps.
            old_by_id = {item.id: item for item in result.steps}
            rebuilt: List[StepRun] = []
            new_step_ids: List[str] = []
            for item in merged.steps:
                previous = old_by_id.get(item.id)
                if previous is not None:
                    rebuilt.append(previous)
                else:
                    fresh = StepRun(item.id, item.tool, item.args, list(item.depends_on))
                    rebuilt.append(fresh)
                    new_step_ids.append(item.id)
            result.plan = merged
            result.steps = rebuilt
            result.replan_events.append(
                build_replan_event(
                    failed_step_id=step.id,
                    failed_tool=step.tool,
                    failure_category=failure_category(str(exc)),
                    new_step_ids=new_step_ids,
                    latency_ms=(perf_counter() - started) * 1000,
                )
            )
            return True
        except Exception:
            # Replanning failed; the caller falls back to fail-fast.
            return False

    def _tool_for_step(self, plan: TaskPlan, step_id: str) -> Optional[str]:
        for item in plan.steps:
            if item.id == step_id:
                return item.tool
        return None

    def _enforce_preflight_policy(
        self,
        tool: str,
        arguments: Dict[str, Any],
        completed_results: Dict[str, Dict[str, Any]],
    ) -> None:
        health = next(
            (value for value in completed_results.values() if value.get("capabilities") is not None),
            None,
        )
        if health is None:
            if tool in _PIXEL_ALIGNMENT_TOOLS:
                raise ToolError(
                    "像元级对齐门控阻止工具 {}：缺少 DEM/土地利用网格对齐证据".format(tool)
                )
            return
        if tool in _PIXEL_ALIGNMENT_TOOLS:
            alignment = (
                (health.get("relationships") or {})
                .get("dem_land_use", {})
                .get("grid_alignment")
            )
            # In-memory demos intentionally have no raster geometry. Preserve
            # their explanatory placeholder, but never run real joint pixels
            # when an explicit health report says the grids are incompatible.
            if isinstance(alignment, dict) and alignment.get("status") not in {"aligned"}:
                status = alignment.get("status") or "unknown"
                reason = alignment.get("reason") or "未提供对齐原因"
                raise ToolError(
                    "像元级对齐门控阻止工具 {}：DEM/土地利用网格状态为 {}；{}".format(
                        tool, status, reason
                    )
                )
        reports = {item.get("dataset"): item for item in health.get("datasets", [])}
        for dataset in _required_health_datasets(tool, arguments):
            report = reports.get(dataset) or {}
            if report.get("status") != "unavailable":
                continue
            capabilities = report.get("usable_for") or []
            capability_text = ", ".join(capabilities) if capabilities else "无"
            raise ToolError(
                f"数据预检阻止工具 {tool}：数据集 {dataset} 不可用；"
                f"当前可用能力：{capability_text}。请切换到本地 GIS 后端或补充数据配置。"
            )

    def _remember(self, result: AgentRunResult) -> None:
        """Persist one bounded memory fact for a completed run."""
        if self._memory is not None:
            self._memory.remember(result)

    def _check_control(self, run_id: str, deadline: Optional[float]) -> None:
        with self._control_lock:
            is_cancel_requested = getattr(self._state_store, "is_cancel_requested", None)
            if run_id in self._cancelled_runs or (
                callable(is_cancel_requested) and is_cancel_requested(run_id)
            ):
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

def _validate_runtime_workflow_plan(
    plan: TaskPlan, workflow: Mapping[str, Any]
) -> None:
    """Recheck planner output against the selected workflow before execution."""

    try:
        template_id = workflow["template_id"]
        constraints = workflow["constraints"]
        evidence = workflow["evidence"]
    except (KeyError, TypeError) as exc:
        raise WorkflowTemplateError("workflow selection is incomplete") from exc
    payload = {
        "template_id": template_id,
        "template_version": workflow.get("template_version"),
        "goal": plan.goal,
        "constraints": constraints,
        "evidence": evidence,
        "steps": [
            {
                "id": step.id,
                "tool": step.tool,
                "args": step.args,
                "depends_on": list(step.depends_on),
            }
            for step in plan.steps
        ],
        "output": dict(plan.output),
        "assumptions": list(plan.assumptions),
    }
    validate_workflow_plan(template_id, payload)


def _replan_context(feedback: Mapping[str, Any]) -> Dict[str, Any]:
    """Wrap replan feedback in the same trusted-context shape planners expect."""
    return {
        "feedback": feedback,
        "note": "Adaptive replan: revise only the remaining steps needed to finish the request.",
    }


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


def _required_health_datasets(tool: str, arguments: Dict[str, Any]) -> Set[str]:
    if tool in {"get_raster_metadata", "get_raster_statistics", "get_zonal_raster_statistics"}:
        dataset = arguments.get("dataset")
        return {dataset} if dataset in {"dem", "land_use"} else set()
    if tool == "get_zonal_slope_statistics":
        return {"dem"}
    if tool == "get_zonal_land_use_distribution":
        return {"land_use"}
    if tool == "get_zonal_buildability_analysis":
        return {"dem", "land_use"}
    if tool == "get_zonal_constrained_buildability_analysis":
        required = {"dem", "land_use", "roads"}
        if arguments.get("exclude_water", True):
            required.add("water")
        return required
    return set()


_PIXEL_ALIGNMENT_TOOLS = {
    "get_zonal_buildability_analysis",
    "get_zonal_constrained_buildability_analysis",
}
