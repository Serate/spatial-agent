import uuid
import inspect
from threading import Lock
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, Iterable, Mapping, Optional, Set

from .errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from .capability_catalog import (
    CAPABILITY_CONTEXT_SCHEMA_VERSION,
    capability_context_summary,
)
from .capability_routing import CAPABILITY_DISCOVERY_SCHEMA_VERSION
from .context_engineering import ContextBuilder, ContextPacket
from .domain_contract import (
    DOMAIN_DISCOVERY_SCHEMA_VERSION,
    DomainPack,
    answer_composer as resolve_answer_composer,
    default_permissions,
    default_domain_pack,
    discovery_context,
    extract_request_facts,
    result_registry as resolve_result_registry,
    domain_action_catalog,
    execute_domain_action,
    preflight_tool as run_domain_preflight,
    runtime_evidence as resolve_runtime_evidence,
    release_evidence as resolve_release_evidence,
    request_understanding_guidance,
    selected_capability_ids,
    workflow_context,
)
from .failure_contract import build_failure_evidence
from .memory import FactMemory
from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .observability import ObservabilityEmitter
from .plan_identity import build_plan_identity
from .planner import Planner
from .replanning import (
    ReplanningPolicy,
    build_replan_event,
    failure_category,
    merge_replanned_plan,
    rule_replan_plan,
)
from .request_model import RequestFacts
from .tools import ToolRegistry
from .workflow_templates import (
    WorkflowTemplateError,
    validate_workflow_plan,
)


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
        answer_composer: Optional[Any] = None,
        context_builder: Optional[ContextBuilder] = None,
        max_steps: int = 12,
        max_retries: int = 2,
        replan_policy: Optional[ReplanningPolicy] = None,
        memory: Optional[FactMemory] = None,
        observability: Optional[ObservabilityEmitter] = None,
        backend_name: str = "unknown",
        domain_pack: Optional[DomainPack] = None,
        allowed_permissions: Optional[Iterable[str]] = None,
        approved_tools: Optional[Iterable[str]] = None,
        require_dependency_evidence: bool = False,
    ):
        self._planner = planner
        self._registry = registry
        self._state_store = state_store or InMemoryStateStore()
        self._conversation_store = conversation_store or InMemoryConversationStore()
        self._backend_name = backend_name
        self._domain_pack = domain_pack or default_domain_pack()
        self._result_registry = resolve_result_registry(self._domain_pack)
        self._answer_composer = answer_composer or resolve_answer_composer(self._domain_pack)
        self._context_builder = context_builder or ContextBuilder()
        self._max_steps = max_steps
        self._max_retries = max_retries
        self._replan_policy = replan_policy or ReplanningPolicy()
        self._memory = memory
        self._observability = observability
        # The selected Domain Pack owns its default grant. Callers can still
        # narrow or replace it explicitly for a deployment.
        self._allowed_permissions = {
            str(item) for item in (
                allowed_permissions
                if allowed_permissions is not None
                else default_permissions(self._domain_pack)
            ) if str(item)
        }
        self._approved_tools = {
            str(item) for item in (approved_tools or []) if str(item)
        }
        self._require_dependency_evidence = bool(require_dependency_evidence)
        self._control_lock = Lock()
        self._cancelled_runs: Set[str] = set()
        self._run_span_ids: Dict[str, str] = {}

    def result_registry(self):
        """Return the result metadata registry selected by this Domain Pack."""
        return self._result_registry

    def domain_actions(self) -> Dict[str, Any]:
        """Return the selected Domain Pack's bounded action catalog."""
        return domain_action_catalog(self._domain_pack)

    def execute_domain_action(
        self,
        action_id: str,
        payload: Mapping[str, Any],
        *,
        context: Any = None,
    ) -> Any:
        """Execute a declared action through the Domain Pack seam."""
        return execute_domain_action(
            self._domain_pack,
            action_id,
            payload,
            context=context,
        )

    def capability_catalog(self) -> Mapping[str, Any]:
        """Return the selected Domain Pack's bounded capability catalog."""
        catalog = self._domain_pack.capability_catalog(
            environment=self._backend_name or "unknown"
        )
        return dict(catalog) if isinstance(catalog, Mapping) else {}

    def runtime_capabilities(self, *, max_files: int = 10) -> Dict[str, Any]:
        """Return generic provider evidence plus optional domain evidence."""
        if not isinstance(max_files, int) or max_files < 1 or max_files > 10:
            raise ValueError("max_files must be between 1 and 10")
        snapshot = dict(self.capability_catalog())
        snapshot.setdefault("actions", self.domain_actions())
        snapshot.update({
            "domain_id": str(getattr(self._domain_pack, "domain_id", "unknown")),
            "runtime": {
                "backend": self._backend_name,
                "domain_id": str(getattr(self._domain_pack, "domain_id", "unknown")),
            },
            "tool_provider": self._registry.provider_info(),
            "tool_provider_health": self._registry.provider_health(),
            "tool_governance": self._registry.governance_summary(max_tools=32),
            "health_status": "not_evaluated",
            "data_readiness": "not_evaluated",
            "data_evidence": {},
            "data_provenance": {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            evidence = resolve_runtime_evidence(
                self._domain_pack,
                max_files=max_files,
            )
        except Exception:
            evidence = {
                "health_status": "unavailable",
                "evidence_error_code": "domain_runtime_evidence_unavailable",
            }
        capability_runtime = evidence.get("capabilities_runtime")
        if isinstance(capability_runtime, list):
            snapshot["capabilities"] = capability_runtime[:32]
        for key, value in evidence.items():
            if key not in {
                "capabilities",
                "capabilities_runtime",
                "tool_provider",
                "tool_provider_health",
                "tool_governance",
            }:
                snapshot[key] = value
        return snapshot

    def release_evidence(
        self,
        *,
        config_path: Optional[str] = None,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        """Return release evidence through the selected Domain Pack.

        Release/data publication policy is deliberately outside this Module's
        implementation. The Domain Pack owns the provider; the Runtime only
        validates the bounded request and returns its JSON-safe projection.
        """
        if not isinstance(max_files, int) or max_files < 1 or max_files > 10:
            raise ValueError("max_files must be between 1 and 10")
        evidence = resolve_release_evidence(
            self._domain_pack,
            config_path=config_path,
            max_files=max_files,
        )
        evidence.setdefault(
            "domain_id", str(getattr(self._domain_pack, "domain_id", "unknown"))[:80]
        )
        return evidence

    def run(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        run_id: Optional[str] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        expected_plan_fingerprint: Optional[str] = None,
    ) -> AgentRunResult:
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        deadline = perf_counter() + timeout_seconds if timeout_seconds is not None else None
        resolved_request = self._resolve_request(request, session_id)
        request_facts = extract_request_facts(self._domain_pack, resolved_request)
        resolved_run_id = run_id or str(uuid.uuid4())
        run_span_id = uuid.uuid4().hex[:16]
        self._run_span_ids[resolved_run_id] = run_span_id
        result = AgentRunResult(
            run_id=resolved_run_id,
            status=RunStatus.PLANNING,
            request=request,
            session_id=session_id,
            resolved_request=resolved_request,
            request_facts=request_facts.as_context_dict(),
            workflow=dict(workflow) if workflow is not None else None,
        )
        context_packet = self._build_context_packet(
            request, resolved_request, session_id, workflow, request_facts=request_facts
        )
        result.context_evidence = context_packet.evidence
        self._state_store.save(result)
        try:
            # Check controls around planning as well as tool dispatch. A
            # direct-answer plan has no step boundary where cancellation or
            # timeout would otherwise be observed.
            self._check_control(result.run_id, deadline)
            plan = self._plan(resolved_request, workflow, context_packet)
            result.plan_evidence = _build_plan_evidence(
                plan,
                workflow,
                context_packet,
                planner_kind=type(self._planner).__name__,
            )
            result.plan_evidence["execution_policy"] = self._execution_policy_evidence(plan)
            if expected_plan_fingerprint is not None:
                actual_fingerprint = (result.plan_evidence.get("plan_identity") or {}).get("fingerprint")
                result.plan_evidence["expected_plan_fingerprint"] = str(expected_plan_fingerprint)
                result.plan_evidence["plan_fingerprint_match"] = (
                    str(expected_plan_fingerprint) == str(actual_fingerprint)
                )
                if not result.plan_evidence["plan_fingerprint_match"]:
                    raise ToolError("preview plan fingerprint mismatch")
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
            _record_run_failure(result, exc, phase="planning")
            self._conversation_store.save_pending(session_id, resolved_request, result.error)
        except RequestRejected as exc:
            result.status = RunStatus.REJECTED
            result.error = str(exc)
            _record_run_failure(result, exc, phase="planning")
            self._conversation_store.clear_pending(session_id)
        except RunCancelled as exc:
            result.status = RunStatus.CANCELLED
            result.error = str(exc)
            _record_run_failure(result, exc, phase="control")
        except RunTimedOut as exc:
            result.status = RunStatus.TIMED_OUT
            result.error = str(exc)
            _record_run_failure(result, exc, phase="control")
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
            _record_run_failure(result, exc)
            result.answer = self._answer_composer.compose_failure(result)
        if result.planner_metrics is None:
            result.planner_metrics = self._planner_metrics()
        self._state_store.save(result)
        self._emit_run_event(result)
        return result

    def preview(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        workflow: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Plan a request and return a bounded DAG preview without dispatching tools."""
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        resolved_request = self._resolve_request(request, session_id)
        request_facts = extract_request_facts(self._domain_pack, resolved_request)
        context_packet = self._build_context_packet(
            request, resolved_request, session_id, workflow, request_facts=request_facts
        )
        payload: Dict[str, Any] = {
            "status": "PLANNING",
            "request": request,
            "resolved_request": resolved_request,
            "session_id": session_id,
            "request_facts": request_facts.as_context_dict(),
            "workflow": dict(workflow) if workflow is not None else None,
            "context_evidence": context_packet.evidence,
            "execution": {
                "planned_only": True,
                "tool_execution": False,
                "artifact_export": False,
            },
        }
        try:
            plan = self._plan(resolved_request, workflow, context_packet)
            if workflow is not None:
                _validate_runtime_workflow_plan(plan, workflow)
            if plan.output.get("type") != "direct_answer":
                self._validate_plan(plan)
            plan_payload = _plan_to_dict(plan)
            plan_evidence = _build_plan_evidence(
                plan,
                workflow,
                context_packet,
                planner_kind=type(self._planner).__name__,
            )
            plan_evidence["execution_policy"] = self._execution_policy_evidence(plan)
            payload.update({
                "status": "PLANNED",
                "plan": plan_payload,
                "dag": _plan_dag(plan),
                "plan_evidence": plan_evidence,
                "plan_identity": dict(plan_evidence["plan_identity"]),
                "planner_metrics": self._planner_metrics(),
            })
        except ClarificationNeeded as exc:
            payload.update({
                "status": RunStatus.NEEDS_CLARIFICATION.value,
                "error": str(exc),
                "clarification": exc.details,
                "planner_metrics": self._planner_metrics(),
            })
        except RequestRejected as exc:
            payload.update({
                "status": RunStatus.REJECTED.value,
                "error": str(exc),
                "planner_metrics": self._planner_metrics(),
            })
        except Exception as exc:
            payload.update({
                "status": RunStatus.FAILED.value,
                "error": str(exc),
                "planner_metrics": self._planner_metrics(),
            })
        if payload.get("workflow") is None:
            payload.pop("workflow", None)
        return payload

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

    def _execution_policy_evidence(self, plan: TaskPlan) -> Dict[str, Any]:
        """Project the Registry governance used by this plan into evidence."""
        tools = []
        seen = set()
        for step in plan.steps:
            if step.tool in seen:
                continue
            seen.add(step.tool)
            tools.append(self._registry.governance_for(step.tool))
        return {
            "schema_version": "spatial-agent.execution-policy.v1",
            "provider_id": self._registry.provider_info().get("id", "unknown"),
            "dependency_evidence_required": self._require_dependency_evidence,
            "allowed_permission_count": len(self._allowed_permissions),
            "wildcard_permission": "*" in self._allowed_permissions,
            "approved_tool_count": len(self._approved_tools),
            "tools": tools[:32],
        }

    def _build_context_packet(
        self,
        request: str,
        resolved_request: str,
        session_id: str,
        workflow: Optional[Mapping[str, Any]],
        *,
        request_facts: Optional[RequestFacts] = None,
    ) -> ContextPacket:
        memory_section = (
            self._memory.context_section(session_id)
            if self._memory is not None
            else None
        )
        spatial_request = request_facts or extract_request_facts(
            self._domain_pack, resolved_request
        )
        capability_discovery = self._domain_pack.discover(
            resolved_request,
            spatial_request,
        )
        discovery_payload = discovery_context(
            capability_discovery,
            domain_id=str(getattr(self._domain_pack, "domain_id", "unknown")),
        )
        understanding_payload = request_understanding_guidance(self._domain_pack)
        capability_catalog = capability_context_summary(
            catalog=self._domain_pack.capability_catalog(
                environment=self._backend_name or "unknown"
            ),
            tool_definitions=self._registry.definition_summary(),
            tool_provider=self._registry.provider_info(),
            tool_provider_health=self._registry.provider_health(),
            tool_governance=self._registry.governance_summary(max_tools=8),
            selected_capability_ids=selected_capability_ids(capability_discovery)[:1],
            max_capabilities=1,
            max_tools=8,
        )
        return self._context_builder.build(
            request=request,
            resolved_request=resolved_request,
            session_id=session_id,
            workflow=workflow,
            available_tools=self._registry.names,
            planner_kind=type(self._planner).__name__,
            spatial_request=spatial_request.as_context_dict(),
            request_understanding=understanding_payload,
            capability_discovery=discovery_payload,
            capability_catalog=capability_catalog,
            memory_section=memory_section,
            workflow_templates=workflow_context(self._domain_pack),
        )

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
        resolved_args = _resolve_result_references(step.args, completed_results)
        step_run.governance = self._registry.governance_for(step.tool)
        try:
            self._enforce_preflight_policy(step.tool, resolved_args, completed_results)
        except ToolError as exc:
            step_run.status = "FAILED"
            step_run.error = str(exc)
            step_run.error_category = getattr(exc, "category", None) or "tool_gate"
            step_run.error_code = getattr(exc, "code", None)
            step_run.retryable = getattr(exc, "retryable", None)
            step_run.finished_at = _utc_now()
            self._emit_step_event(run_id, step_run)
            raise
        self._check_control(run_id, deadline)
        step_run.args = resolved_args
        step_run.status = "RUNNING"
        step_run.started_at = _utc_now()
        started = perf_counter()
        for attempt in range(1, self._max_retries + 2):
            self._check_control(run_id, deadline)
            step_run.attempts = attempt
            try:
                tool_timeout = self._registry.timeout_seconds(step.tool)
                if deadline is not None:
                    remaining = deadline - perf_counter()
                    if remaining <= 0:
                        raise RunTimedOut("run exceeded timeout_seconds")
                    if tool_timeout is not None:
                        tool_timeout = min(float(tool_timeout), remaining)
                step_run.result = self._registry.invoke(
                    step.tool,
                    resolved_args,
                    timeout_seconds=tool_timeout,
                )
                step_run.status = "COMPLETED"
                step_run.finished_at = _utc_now()
                step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
                self._emit_step_event(run_id, step_run)
                return
            except ToolError as exc:
                step_run.error = str(exc)
                step_run.error_category = getattr(exc, "category", None) or failure_category(str(exc))
                step_run.error_code = getattr(exc, "code", None)
                step_run.retryable = getattr(exc, "retryable", None)
                if exc.retryable is False or attempt > self._max_retries:
                    step_run.status = "FAILED"
                    step_run.finished_at = _utc_now()
                    step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
                    self._emit_step_event(run_id, step_run)
                    raise
        step_run.status = "FAILED"
        step_run.finished_at = _utc_now()
        step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
        self._emit_step_event(run_id, step_run)

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
            "error_category": step_run.error_category or failure_category(str(exc)),
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
                    failure_category=step_run.error_category or failure_category(str(exc)),
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
        governance = self._registry.governance_for(tool)
        required_permissions = governance.get("permissions") or []
        missing_permissions = [
            permission
            for permission in required_permissions
            if permission not in self._allowed_permissions
            and "*" not in self._allowed_permissions
        ]
        if missing_permissions:
            raise ToolError(
                "工具权限门控阻止 {}：缺少 {}".format(
                    tool, ", ".join(missing_permissions)
                ),
                category="policy",
                code="permission_denied",
                retryable=False,
            )
        if governance.get("requires_approval") and tool not in self._approved_tools:
            raise ToolError(
                "工具审批门控阻止 {}：该工具需要显式审批".format(tool),
                category="policy",
                code="approval_required",
                retryable=False,
            )

        run_domain_preflight(
            self._domain_pack,
            tool,
            arguments,
            completed_results,
            required_datasets=self._registry.data_dependencies(tool, arguments),
            require_dependency_evidence=self._require_dependency_evidence,
        )

    def _remember(self, result: AgentRunResult) -> None:
        """Persist one bounded memory fact for a completed run."""
        if self._memory is not None:
            self._memory.remember(result)

    def _emit_run_event(self, result: AgentRunResult) -> None:
        if self._observability is None:
            return
        span_id = self._run_span_ids.get(result.run_id)
        run_category = _run_error_category(result)
        attributes = {
            "session_id": result.session_id,
            "result_type": _result_type_for_observability(result),
            "error_category": run_category,
            "error_code": (result.failure or {}).get("code") or result.error_code,
            "failure_phase": (result.failure or {}).get("phase"),
            "failure_retryable": (result.failure or {}).get("retryable"),
            "replan_count": len(result.replan_events),
            "memory_fact_count": len(self._memory.recall(session_id=result.session_id or "default"))
            if self._memory is not None
            else 0,
        }
        attributes = {key: value for key, value in attributes.items() if value is not None}
        self._observability.emit_run(
            run_id=result.run_id,
            session_id=result.session_id,
            name="{}:{}".format(type(self._planner).__name__, _result_type_for_observability(result)),
            status=result.status.value,
            duration_ms=_run_duration_ms(result),
            attributes=attributes,
            span_id=span_id,
        )
        if span_id:
            self._run_span_ids.pop(result.run_id, None)

    def _emit_step_event(
        self,
        run_id: str,
        step_run: StepRun,
    ) -> None:
        if self._observability is None:
            return
        parent_span_id = self._run_span_ids.get(run_id)
        attributes = {
            "attempts": step_run.attempts,
            "error_category": step_run.error_category or failure_category(step_run.error),
            "error_code": step_run.error_code,
        }
        attributes = {key: value for key, value in attributes.items() if value is not None}
        self._observability.emit_step(
            run_id=run_id,
            parent_span_id=parent_span_id,
            name=step_run.tool,
            status=step_run.status,
            duration_ms=step_run.latency_ms,
            attributes=attributes,
        )

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


def _plan_to_dict(plan: TaskPlan) -> Dict[str, Any]:
    return {
        "goal": plan.goal,
        "steps": [
            {
                "id": step.id,
                "tool": step.tool,
                "args": dict(step.args),
                "depends_on": list(step.depends_on),
            }
            for step in plan.steps
        ],
        "output": dict(plan.output),
        "assumptions": list(plan.assumptions),
    }


def _plan_dag(plan: TaskPlan) -> Dict[str, Any]:
    nodes = [
        {
            "id": step.id,
            "tool": step.tool,
            "depends_on": list(step.depends_on),
            "arg_keys": sorted(step.args.keys()),
        }
        for step in plan.steps
    ]
    edges = [
        {"from": dependency, "to": step.id}
        for step in plan.steps
        for dependency in step.depends_on
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _build_plan_evidence(
    plan: TaskPlan,
    workflow: Optional[Mapping[str, Any]],
    context_packet: ContextPacket,
    *,
    planner_kind: str,
) -> Dict[str, Any]:
    """Build a bounded, persisted explanation of the planning source."""

    output_type = str((plan.output or {}).get("type") or "unknown")
    tool_names = [step.tool for step in plan.steps]
    sections = (context_packet.payload or {}).get("sections", {})
    if not isinstance(sections, Mapping):
        sections = {}
    templates_section = sections.get("workflow_templates")
    templates_available = (
        isinstance(templates_section, Mapping)
        and not templates_section.get("omitted")
        and isinstance(templates_section.get("templates"), list)
    )
    request_section = sections.get("request")
    if not isinstance(request_section, Mapping):
        request_section = {}
    understanding_section = sections.get("request_understanding")
    understanding_available = (
        isinstance(understanding_section, Mapping)
        and understanding_section.get("schema_version")
        == "spatial-agent.request-understanding-guidance.v1"
        and not understanding_section.get("omitted")
    )
    capability_section = sections.get("capability_discovery")
    capability_available = (
        isinstance(capability_section, Mapping)
        and capability_section.get("schema_version") in {
            CAPABILITY_DISCOVERY_SCHEMA_VERSION,
            DOMAIN_DISCOVERY_SCHEMA_VERSION,
        }
        and not capability_section.get("omitted")
    )
    capability_catalog_section = sections.get("capability_catalog")
    capability_catalog_available = (
        isinstance(capability_catalog_section, Mapping)
        and capability_catalog_section.get("schema_version") == CAPABILITY_CONTEXT_SCHEMA_VERSION
        and not capability_catalog_section.get("omitted")
    )
    evidence: Dict[str, Any] = {
        "available": True,
        "planner_kind": planner_kind,
        "source": _planner_source(planner_kind, workflow),
        "output_type": output_type,
        "step_count": len(plan.steps),
        "tool_names": tool_names,
        "unique_tools": _unique(tool_names),
        "context_schema_version": context_packet.evidence.get("schema_version"),
        "context_sections": list(context_packet.evidence.get("section_names") or []),
        "template_context_available": templates_available,
        "template_context_truncated": bool(context_packet.evidence.get("truncated")),
        "request_understanding_available": understanding_available,
        "capability_discovery_available": capability_available,
        "capability_catalog_available": capability_catalog_available,
        "plan_identity": build_plan_identity(
            plan,
            request=str(request_section.get("original") or ""),
            resolved_request=str(request_section.get("resolved") or ""),
            workflow=workflow,
            planner_kind=planner_kind,
        ),
    }
    # Keep the selected domain visible in the generic planning envelope.  The
    # Runtime must not import or interpret domain-specific identifiers; both
    # discovery and the capability catalog already expose this boundary for
    # custom Domain Packs.
    domain_id = None
    if isinstance(capability_section, Mapping):
        domain_id = capability_section.get("domain_id")
    if not domain_id and isinstance(capability_catalog_section, Mapping):
        domain_id = capability_catalog_section.get("domain_id")
    evidence["domain_id"] = str(domain_id)[:80] if domain_id else "unknown"
    request_facts = sections.get("spatial_request")
    if isinstance(request_facts, Mapping):
        evidence["request_facts"] = {
            "schema_version": str(
                request_facts.get("schema_version", "spatial-agent.request-facts.v1")
            )[:80],
            "admin_name": str(request_facts.get("admin_name"))[:120]
            if request_facts.get("admin_name")
            else None,
            "tasks": [str(item)[:64] for item in (request_facts.get("tasks") or [])[:16]],
            "datasets": [str(item)[:64] for item in (request_facts.get("datasets") or [])[:16]],
            "constraints": _safe_small_mapping(request_facts.get("constraints")),
            "evidence": [str(item)[:64] for item in (request_facts.get("evidence") or [])[:8]],
        }
    if understanding_available and isinstance(understanding_section, Mapping):
        evidence["request_understanding_domain_id"] = str(
            understanding_section.get("domain_id", "unknown")
        )[:80]
        evidence["request_understanding_schema_version"] = str(
            understanding_section.get("schema_version", "")
        )[:96]
    if isinstance(workflow, Mapping):
        evidence["workflow_template_id"] = workflow.get("template_id")
        evidence["workflow_template_version"] = workflow.get("template_version")
        evidence["workflow_constraints"] = _safe_small_mapping(workflow.get("constraints"))
        evidence["workflow_evidence"] = list(workflow.get("evidence") or [])
    if capability_available and isinstance(capability_section, Mapping):
        candidate_ids = capability_section.get("candidate_ids")
        signals = capability_section.get("signals")
        evidence["selected_capability_id"] = capability_section.get("selected_capability_id")
        evidence["capability_candidate_ids"] = (
            [str(item) for item in candidate_ids[:8]]
            if isinstance(candidate_ids, list)
            else []
        )
        evidence["capability_candidate_count"] = capability_section.get("candidate_count")
        evidence["capability_signals"] = (
            [str(item) for item in signals[:16]]
            if isinstance(signals, list)
            else []
        )
    if capability_catalog_available and isinstance(capability_catalog_section, Mapping):
        catalog_capabilities = capability_catalog_section.get("capabilities")
        tool_schemas = capability_catalog_section.get("tool_schemas")
        evidence["capability_catalog_environment"] = capability_catalog_section.get("environment")
        evidence["capability_catalog_ids"] = (
            [
                str(item.get("id"))
                for item in catalog_capabilities[:8]
                if isinstance(item, Mapping) and item.get("id")
            ]
            if isinstance(catalog_capabilities, list)
            else []
        )
        evidence["capability_catalog_tool_schema_count"] = (
            len(tool_schemas) if isinstance(tool_schemas, Mapping) else 0
        )
        provider = capability_catalog_section.get("tool_provider")
        if isinstance(provider, Mapping):
            evidence["capability_catalog_tool_provider"] = {
                "id": str(provider.get("id", "unknown"))[:64],
                "tool_count": int(provider.get("tool_count", 0) or 0),
            }
        provider_health = capability_catalog_section.get("tool_provider_health")
        if isinstance(provider_health, Mapping):
            evidence["capability_catalog_tool_provider_health"] = {
                "schema_version": str(provider_health.get("schema_version", ""))[:80],
                "provider_id": str(provider_health.get("provider_id", "unknown"))[:64],
                "status": str(provider_health.get("status", "unknown"))[:20],
                "tool_count": int(provider_health.get("tool_count", 0) or 0),
                "reason_code": str(provider_health.get("reason_code"))[:96]
                if provider_health.get("reason_code")
                else None,
            }
            contract = provider_health.get("definition_contract")
            if isinstance(contract, Mapping):
                evidence["capability_catalog_tool_provider_health"]["definition_contract"] = {
                    "schema_version": str(contract.get("schema_version", ""))[:80],
                    "provider_id": str(contract.get("provider_id", "unknown"))[:64],
                    "status": str(contract.get("status", "unknown"))[:20],
                    "tool_count": int(contract.get("tool_count", 0) or 0),
                    "validation": str(contract.get("validation", "unknown"))[:64],
                }
        governance = capability_catalog_section.get("tool_governance")
        if isinstance(governance, Mapping):
            evidence["capability_catalog_tool_governance"] = {
                "schema_version": str(governance.get("schema_version", ""))[:80],
                "provider_id": str(governance.get("provider_id", "unknown"))[:64],
                "tool_count": int(governance.get("tool_count", 0) or 0),
                "returned_tool_count": int(governance.get("returned_tool_count", 0) or 0),
                "requires_approval_count": int(governance.get("requires_approval_count", 0) or 0),
                "side_effect_tool_count": int(governance.get("side_effect_tool_count", 0) or 0),
                "tools": [
                    {
                        "name": str(item.get("name", ""))[:96],
                        "side_effect": str(item.get("side_effect", "unknown"))[:32],
                        "requires_approval": bool(item.get("requires_approval", False)),
                        "permissions": [str(x)[:96] for x in (item.get("permissions") or [])[:8]],
                        "data_dependencies": [str(x)[:96] for x in (item.get("data_dependencies") or [])[:8]],
                        "timeout_seconds": item.get("timeout_seconds"),
                    }
                    for item in (governance.get("tools") or [])[:8]
                    if isinstance(item, Mapping)
                ],
            }
    matched, exact = _matched_template_ids(
        templates_section if isinstance(templates_section, Mapping) else {},
        output_type=output_type,
        tool_names=tool_names,
        step_count=len(plan.steps),
        steps=[
            {
                "id": step.id,
                "tool": step.tool,
                "depends_on": list(step.depends_on),
                "arg_keys": sorted(step.args.keys()),
            }
            for step in plan.steps
        ],
    )
    evidence["matched_template_ids"] = matched
    evidence["exact_template_ids"] = exact
    return evidence


def _planner_source(planner_kind: str, workflow: Optional[Mapping[str, Any]]) -> str:
    if isinstance(workflow, Mapping) and workflow.get("template_id"):
        return "workflow_selection"
    lowered = planner_kind.lower()
    if "llm" in lowered or "openai" in lowered:
        return "llm"
    return "rule"


def _matched_template_ids(
    templates_section: Mapping[str, Any],
    *,
    output_type: str,
    tool_names: list[str],
    step_count: int,
    steps: list[Mapping[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    exact: list[str] = []
    templates = templates_section.get("templates")
    if not isinstance(templates, list):
        return matched, exact
    for template in templates:
        if not isinstance(template, Mapping):
            continue
        template_id = template.get("id")
        if not isinstance(template_id, str) or not template_id:
            continue
        result_types = template.get("result_types") or []
        allowed_tools = set(template.get("allowed_tools") or [])
        try:
            max_steps = int(template.get("max_steps") or 0)
        except (TypeError, ValueError):
            max_steps = 0
        if output_type not in result_types:
            continue
        if max_steps and step_count > max_steps:
            continue
        if any(tool not in allowed_tools for tool in tool_names):
            continue
        matched.append(template_id)
        blueprint_steps = [
            step
            for step in template.get("step_blueprint") or []
            if isinstance(step, Mapping)
        ]
        if blueprint_steps and _blueprint_steps_match(blueprint_steps, steps or []):
            exact.append(template_id)
    return matched, exact


def _blueprint_steps_match(
    blueprint_steps: list[Mapping[str, Any]],
    actual_steps: list[Mapping[str, Any]],
) -> bool:
    if len(blueprint_steps) != len(actual_steps):
        return False
    for expected, actual in zip(blueprint_steps, actual_steps):
        if actual.get("id") != expected.get("id"):
            return False
        if actual.get("tool") != expected.get("tool"):
            return False
        if list(actual.get("depends_on") or []) != list(expected.get("depends_on") or []):
            return False
        expected_arg_keys = sorted(expected.get("arg_keys") or [])
        if expected_arg_keys and sorted(actual.get("arg_keys") or []) != expected_arg_keys:
            return False
    return True


def _safe_small_mapping(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, Any] = {}
    for key, item in list(value.items())[:12]:
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[str(key)[:80]] = item
        else:
            result[str(key)[:80]] = str(item)[:160]
    return result


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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


def _result_type_for_observability(result: AgentRunResult) -> str:
    plan = result.plan
    if plan is not None:
        output_type = (plan.output or {}).get("type")
        if output_type:
            return str(output_type)
    return "unknown"


def _run_duration_ms(result: AgentRunResult) -> Optional[float]:
    values = [step.latency_ms for step in result.steps if step.latency_ms is not None]
    if not values:
        return None
    return round(sum(float(value) for value in values), 3)


def _record_run_failure(
    result: AgentRunResult,
    exc: Exception,
    *,
    phase: Optional[str] = None,
) -> None:
    """Promote the final failure classification to the run-level contract."""
    failed_steps = [
        step
        for step in reversed(result.steps)
        if step.status == "FAILED" or step.error
    ]
    failed_step = failed_steps[0] if failed_steps else None
    category = (
        getattr(exc, "category", None)
        or (failed_step.error_category if failed_step else None)
        or _run_error_category(result)
    )
    code = getattr(exc, "code", None) or (failed_step.error_code if failed_step else None)
    retryable = getattr(exc, "retryable", None)
    if retryable is None and failed_step is not None:
        retryable = failed_step.retryable
    result.error_category = str(category)[:64] if category else None
    result.error_code = str(code)[:96] if code else None
    result.failure = build_failure_evidence(
        status=result.status.value,
        category=result.error_category,
        code=result.error_code,
        phase=phase,
        retryable=retryable,
    )
    # Keep the legacy top-level fields aligned with the canonical evidence.
    result.error_category = result.failure["category"]
    result.error_code = result.failure["code"]


def _run_error_category(result: AgentRunResult) -> Optional[str]:
    status = result.status
    if status == RunStatus.COMPLETED:
        return None
    if status == RunStatus.CANCELLED:
        return "cancelled"
    if status == RunStatus.TIMED_OUT:
        return "timeout"
    if status == RunStatus.REJECTED:
        return "rejected"
    if status == RunStatus.NEEDS_CLARIFICATION:
        return "clarification"
    return failure_category(result.error)
