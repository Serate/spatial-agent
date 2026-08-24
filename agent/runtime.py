import uuid
import inspect
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

from .errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from .capability_catalog import (
    CAPABILITY_CONTEXT_SCHEMA_VERSION,
    capability_context_summary,
)
from .capability_routing import CAPABILITY_DISCOVERY_SCHEMA_VERSION
from .capability_discovery import enrich_discovery_context
from .context_engineering import ContextBuilder, ContextPacket
from .conversation_turn import build_conversation_turn, resolve_turn_mode
from .domain_contract import (
    DOMAIN_DISCOVERY_SCHEMA_VERSION,
    DomainPack,
    answer_composer as resolve_answer_composer,
    default_permissions,
    default_domain_pack,
    discovery_context,
    extract_request_facts,
    result_registry as resolve_result_registry,
    execute_domain_action,
    clarification_details as resolve_clarification_details,
    evidence_action_guidance as resolve_evidence_action_guidance,
    preflight_tool as run_domain_preflight,
    plan_policy as resolve_plan_policy,
    select_workflow as resolve_workflow_selection,
    request_understanding_guidance,
    selected_capability_ids,
    workflow_context,
    workflow_seam_summary,
)
from .decision_lifecycle import DecisionLifecycleError, DecisionRequest, DecisionStore
from .action_lifecycle import project_action_lifecycle
from .evidence_contract import project_capability_catalog_evidence
from .failure_contract import build_failure_evidence
from .answer_generation import fallback_answer_generation_evidence
from .memory import FactMemory
from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .plan_repair import PlanRepairEngine, PlanRepairInput
from .observability import ObservabilityEmitter
from .plan_identity import build_plan_identity
from .evidence_revalidation import (
    build_evidence_binding,
    build_evidence_revalidation_gate,
)
from .plan_quality import diagnose_plan, project_plan_quality_evidence
from .plan_policy import build_plan_policy_evidence
from .planner_selection import build_planner_selection_evidence
from .planner_context import (
    PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION,
    project_planner_sections,
)
from .workflow_selection import (
    build_workflow_selection_evidence,
    normalize_workflow_selection_evidence,
)
from .planner import Planner
from .replanning import (
    ReplanningPolicy,
    build_replan_event,
    failure_category,
    merge_replanned_plan,
    rule_replan_plan,
)
from .request_model import RequestFacts
from .runtime_context import build_runtime_context
from .tools import ToolRegistry
from .runtime_core import projection as _runtime_projection
from .runtime_core import planning as _runtime_planning
from .runtime_core import execution as _runtime_execution
from .runtime_core.capabilities import RuntimeCapabilitySurface
from .runtime_core.control import RunControl
from .runtime_state import (
    InMemoryConversationStore,
    InMemoryStateStore,
    PendingClarification,
)


class AgentRuntime:
    """The orchestration seam for planning, validation, execution, and tracing."""

    def __init__(
        self,
        planner: Planner,
        registry: ToolRegistry,
        state_store: Optional[InMemoryStateStore] = None,
        conversation_store: Optional[InMemoryConversationStore] = None,
        answer_composer: Optional[Any] = None,
        answer_generator: Optional[Any] = None,
        context_builder: Optional[ContextBuilder] = None,
        max_steps: int = 12,
        max_retries: int = 2,
        replan_policy: Optional[ReplanningPolicy] = None,
        plan_repair_engine: Optional[PlanRepairEngine] = None,
        decision_store: Optional[DecisionStore] = None,
        memory: Optional[FactMemory] = None,
        observability: Optional[ObservabilityEmitter] = None,
        backend_name: str = "unknown",
        planner_name: str = "unknown",
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
        self._planner_name = str(planner_name or "unknown")[:32]
        self._domain_pack = domain_pack or default_domain_pack()
        self._result_registry = resolve_result_registry(self._domain_pack)
        self._answer_composer = answer_composer or resolve_answer_composer(self._domain_pack)
        self._answer_generator = answer_generator
        self._context_builder = context_builder or ContextBuilder()
        self._max_steps = max_steps
        self._max_retries = max_retries
        self._replan_policy = replan_policy or ReplanningPolicy()
        self._decision_store = decision_store
        self._plan_repair_engine = plan_repair_engine or PlanRepairEngine(
            self._planner,
            self._replan_policy,
            available_tools=lambda: list(self._registry.names),
            validate_plan=self._validate_plan_for_execution,
            control_check=self._check_control,
        )
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
        self._capability_surface = RuntimeCapabilitySurface(
            domain_pack=self._domain_pack,
            backend_name=self._backend_name,
            registry=self._registry,
            domain_id=lambda: self.domain_id,
            runtime_context=self.runtime_context,
        )
        self._control = RunControl(self._state_store)
        self._run_span_ids: Dict[str, str] = {}

    @property
    def domain_id(self) -> str:
        """Return the selected Domain Pack identity for service boundaries."""
        return str(getattr(self._domain_pack, "domain_id", "unknown"))[:80]

    def runtime_context(self) -> Dict[str, Any]:
        """Return the immutable configuration evidence for this Runtime."""
        return build_runtime_context(
            domain_id=self.domain_id,
            planner=self._planner_name,
            backend=self._backend_name,
            tool_provider=self._registry.provider_info(),
            permissions=self._allowed_permissions,
            approved_tools=self._approved_tools,
            require_dependency_evidence=self._require_dependency_evidence,
        )

    def result_registry(self):
        """Return the result metadata registry selected by this Domain Pack."""
        return self._result_registry

    def domain_actions(self) -> Dict[str, Any]:
        """Return the selected Domain Pack's bounded action catalog."""
        return self._capability_surface.domain_actions()

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
        return self._capability_surface.capability_catalog()

    def workflow_template_catalog(self) -> Dict[str, Dict[str, Any]]:
        """Return the selected Domain's declarative workflow catalog."""
        return self._capability_surface.workflow_template_catalog()

    def workflow_contract(self) -> Dict[str, Any]:
        """Return bounded catalog and validator allowlists for HTTP seams."""
        return self._capability_surface.workflow_contract()

    def runtime_capabilities(self, *, max_files: int = 10) -> Dict[str, Any]:
        """Return generic provider evidence plus optional domain evidence."""
        return self._capability_surface.runtime_capabilities(max_files=max_files)

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
        return self._capability_surface.release_evidence(
            config_path=config_path,
            max_files=max_files,
        )

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
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        if decision_ttl_seconds is not None and decision_ttl_seconds <= 0:
            raise ToolError("decision_ttl_seconds must be positive")
        deadline = perf_counter() + timeout_seconds if timeout_seconds is not None else None
        pending = self._conversation_store.get_pending(session_id)
        turn_advice = resolve_turn_mode(
            self._domain_pack,
            request,
            pending_request=pending.request if pending is not None else None,
            pending_error=pending.error if pending is not None else None,
        )
        if resolved_request_override is not None:
            if not isinstance(resolved_request_override, str) or not resolved_request_override.strip():
                raise ToolError("resolved_request_override must be a non-empty string")
            resolved_request = resolved_request_override.strip()
        else:
            resolved_request = self._resolve_request(
                request,
                session_id,
                pending=pending,
                turn_advice=turn_advice,
            )
        request_facts = extract_request_facts(self._domain_pack, resolved_request)
        resolved_run_id = run_id or str(uuid.uuid4())
        if decision_id is not None:
            existing = self._state_store.get(resolved_run_id)
            if existing is None:
                raise ToolError("decision subject run not found: " + resolved_run_id)
            return self._resume_decision(
                existing,
                decision_id=str(decision_id),
                decision_version=decision_version,
                timeout_seconds=timeout_seconds,
            )
        run_span_id = uuid.uuid4().hex[:16]
        self._run_span_ids[resolved_run_id] = run_span_id
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
            domain_id=self.domain_id,
            runtime_context=self.runtime_context(),
            resolved_request=resolved_request,
            request_facts=request_facts.as_context_dict(),
            workflow=dict(workflow) if workflow is not None else None,
            decision_evidence=dict(decision_evidence) if decision_evidence else None,
        )
        context_packet = self._build_context_packet(
            request, resolved_request, session_id, workflow, request_facts=request_facts
        )
        result.context_evidence = context_packet.evidence
        self._state_store.save(result)
        candidate_plan: Optional[TaskPlan] = None
        try:
            # Check controls around planning as well as tool dispatch. A
            # direct-answer plan has no step boundary where cancellation or
            # timeout would otherwise be observed.
            self._check_control(result.run_id, deadline)
            self._require_workflow_selection(context_packet, workflow)
            plan = self._plan(resolved_request, workflow, context_packet)
            candidate_plan = plan
            # Preserve the candidate for rejected/clarification evidence even
            # when the plan fails before it becomes executable.
            result.plan = plan
            self._check_control(result.run_id, deadline)
            plan, _repair_event = self._validate_or_repair_plan(
                plan,
                resolved_request,
                workflow,
                deadline=deadline,
                result=result,
                run_id=result.run_id,
                context_packet=context_packet,
            )
            result.plan = plan
            result.plan_evidence = _build_plan_evidence(
                plan,
                workflow,
                context_packet,
                planner_kind=type(self._planner).__name__,
            )
            result.plan_evidence["plan_policy"] = self._plan_policy_evidence(
                plan,
                workflow,
                state="accepted",
                reason_code="accepted",
                repair_lineage=result.replan_events,
            )
            result.plan_evidence["execution_policy"] = self._execution_policy_evidence(plan)
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
            result.planner_metrics = self._planner_metrics()
            if require_confirmation:
                if self._decision_store is None:
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
                record = self._decision_store.create(
                    DecisionRequest(
                        subject_kind="run",
                        subject_id=result.run_id,
                        domain_id=self.domain_id,
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
                self._state_store.save(result)
                self._emit_run_event(result)
                return result
            if plan.output.get("type") == "direct_answer":
                result.status = RunStatus.COMPLETED
                result.answer = str(plan.output.get("message", ""))
                self._conversation_store.clear_pending(session_id)
                self._conversation_store.save_completed(session_id, resolved_request)
                self._remember(result)
                self._state_store.save(result)
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
            result.answer = self._compose_answer(result)
            self._remember(result)
            self._conversation_store.clear_pending(session_id)
            self._conversation_store.save_completed(session_id, resolved_request)
        except ClarificationNeeded as exc:
            result.status = RunStatus.NEEDS_CLARIFICATION
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = self._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="clarification",
                    reason_code="clarification_required",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            result.clarification = exc.details or resolve_clarification_details(
                self._domain_pack, resolved_request
            ) or None
            _record_run_failure(result, exc, phase="planning")
            self._conversation_store.save_pending(session_id, resolved_request, result.error)
        except RequestRejected as exc:
            result.status = RunStatus.REJECTED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = self._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="rejected",
                    reason_code="request_rejected",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            _record_run_failure(result, exc, phase="planning")
            self._conversation_store.clear_pending(session_id)
        except RunCancelled as exc:
            result.status = RunStatus.CANCELLED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = self._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="unavailable",
                    reason_code="run_cancelled_before_plan_evidence",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            _record_run_failure(result, exc, phase="control")
        except RunTimedOut as exc:
            result.status = RunStatus.TIMED_OUT
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = self._failure_plan_evidence(
                    plan=candidate_plan,
                    workflow=workflow,
                    state="unavailable",
                    reason_code="run_timeout_before_plan_evidence",
                    context_packet=context_packet,
                    repair_lineage=result.replan_events,
                )
            _record_run_failure(result, exc, phase="control")
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error = str(exc)
            if result.plan_evidence is None:
                result.plan_evidence = self._failure_plan_evidence(
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
            _record_run_failure(
                result,
                exc,
                phase="planning" if candidate_plan is None else None,
            )
            result.answer = self._answer_composer.compose_failure(result)
        if result.planner_metrics is None:
            result.planner_metrics = self._planner_metrics()
        self._state_store.save(result)
        self._emit_run_event(result)
        return result

    def _resume_decision(
        self,
        result: AgentRunResult,
        *,
        decision_id: str,
        decision_version: Optional[int],
        timeout_seconds: Optional[float],
    ) -> AgentRunResult:
        """Resume the exact persisted plan after an accepted decision.

        The plan is loaded from the waiting run snapshot instead of asking the
        Planner to regenerate it.  This makes approval meaningful even for a
        nondeterministic provider and keeps the fingerprint a real execution
        boundary rather than a best-effort comparison.
        """
        if self._decision_store is None:
            raise ToolError("decision store is unavailable")
        if result.status != RunStatus.WAITING_FOR_DECISION or result.plan is None:
            raise ToolError("run is not waiting for a decision: " + result.run_id)
        record = self._decision_store.get(decision_id, domain_id=self.domain_id)
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
        consumed = self._decision_store.consume(
            decision_id,
            expected_version=record.version,
            domain_id=self.domain_id,
        )
        result.decision_evidence = consumed.evidence()
        self._run_span_ids[result.run_id] = uuid.uuid4().hex[:16]
        clear_cancel = getattr(self._state_store, "clear_cancel", None)
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
                self._conversation_store.clear_pending(result.session_id or "default")
                self._conversation_store.save_completed(
                    result.session_id or "default", result.resolved_request or result.request
                )
                self._state_store.save(result)
                self._remember(result)
                self._emit_run_event(result)
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
                    self._check_control(result.run_id, deadline)
                    self._execute_step(
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
                    self._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except RunTimedOut as exc:
                    self._block_remaining_steps(result.steps, index, step.id, str(exc))
                    raise
                except Exception as exc:
                    if not self._try_replan(
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
                        self._block_remaining_steps(result.steps, index + 1, step.id, str(exc))
                        raise
                    replan_count += 1
                    index += 1
            result.status = RunStatus.COMPLETED
            result.answer = self._compose_answer(result)
            self._conversation_store.clear_pending(result.session_id or "default")
            self._conversation_store.save_completed(
                result.session_id or "default", result.resolved_request or result.request
            )
            self._remember(result)
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
        self._state_store.save(result)
        self._emit_run_event(result)
        return result

    def preview(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        resolved_request_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Plan a request and return a bounded DAG preview without dispatching tools."""
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        deadline = perf_counter() + timeout_seconds if timeout_seconds is not None else None
        pending = self._conversation_store.get_pending(session_id)
        turn_advice = resolve_turn_mode(
            self._domain_pack,
            request,
            pending_request=pending.request if pending is not None else None,
            pending_error=pending.error if pending is not None else None,
        )
        if resolved_request_override is not None:
            if not isinstance(resolved_request_override, str) or not resolved_request_override.strip():
                raise ToolError("resolved_request_override must be a non-empty string")
            resolved_request = resolved_request_override.strip()
        else:
            resolved_request = self._resolve_request(
                request,
                session_id,
                pending=pending,
                turn_advice=turn_advice,
            )
        request_facts = extract_request_facts(self._domain_pack, resolved_request)
        context_packet = self._build_context_packet(
            request, resolved_request, session_id, workflow, request_facts=request_facts
        )
        payload: Dict[str, Any] = {
            "status": "PLANNING",
            "request": request,
            "resolved_request": resolved_request,
            "session_id": session_id,
            "conversation_turn": build_conversation_turn(
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
            "domain_id": self.domain_id,
            "runtime_context": self.runtime_context(),
            "request_facts": request_facts.as_context_dict(),
            "workflow": dict(workflow) if workflow is not None else None,
            "context_evidence": context_packet.evidence,
            "execution": {
                "planned_only": True,
                "tool_execution": False,
                "artifact_export": False,
            },
        }
        candidate_plan: Optional[TaskPlan] = None
        try:
            self._require_workflow_selection(context_packet, workflow)
            plan = self._plan(resolved_request, workflow, context_packet)
            candidate_plan = plan
            plan, repair_event = self._validate_or_repair_plan(
                plan,
                resolved_request,
                workflow,
                deadline=deadline,
                run_id=None,
                context_packet=context_packet,
            )
            plan_payload = _plan_to_dict(plan)
            plan_evidence = _build_plan_evidence(
                plan,
                workflow,
                context_packet,
                planner_kind=type(self._planner).__name__,
            )
            plan_evidence["plan_policy"] = self._plan_policy_evidence(
                plan,
                workflow,
                state="accepted",
                reason_code="accepted",
                repair_lineage=[repair_event] if repair_event is not None else [],
            )
            plan_evidence["execution_policy"] = self._execution_policy_evidence(plan)
            plan_evidence["evidence_binding"] = build_evidence_binding(
                context_packet.payload
            )
            payload.update({
                "status": "PLANNED",
                "plan": plan_payload,
                "dag": _plan_dag(plan),
                "plan_evidence": plan_evidence,
                "plan_identity": dict(plan_evidence["plan_identity"]),
                "planner_metrics": self._planner_metrics(),
            })
            if repair_event is not None:
                payload["replan_events"] = [repair_event]
        except ClarificationNeeded as exc:
            payload.update({
                "status": RunStatus.NEEDS_CLARIFICATION.value,
                "error": str(exc),
                "clarification": exc.details or resolve_clarification_details(
                    self._domain_pack, resolved_request
                ) or None,
                "planner_metrics": self._planner_metrics(),
            })
            payload["plan_evidence"] = self._failure_plan_evidence(
                plan=candidate_plan,
                workflow=workflow,
                state="clarification",
                reason_code="clarification_required",
                context_packet=context_packet,
                repair_lineage=payload.get("replan_events"),
            )
        except RequestRejected as exc:
            payload.update({
                "status": RunStatus.REJECTED.value,
                "error": str(exc),
                "planner_metrics": self._planner_metrics(),
            })
            payload["plan_evidence"] = self._failure_plan_evidence(
                plan=candidate_plan,
                workflow=workflow,
                state="rejected",
                reason_code="request_rejected",
                context_packet=context_packet,
                repair_lineage=payload.get("replan_events"),
            )
        except Exception as exc:
            payload.update({
                "status": RunStatus.FAILED.value,
                "error": str(exc),
                "planner_metrics": self._planner_metrics(),
            })
            payload["plan_evidence"] = self._failure_plan_evidence(
                plan=candidate_plan,
                workflow=workflow,
                state="rejected" if candidate_plan is not None else "unavailable",
                reason_code=(
                    "plan_validation_rejected"
                    if candidate_plan is not None
                    else "planner_failed"
                ),
                context_packet=context_packet,
                repair_lineage=payload.get("replan_events"),
            )
        payload["lifecycle"] = project_action_lifecycle(payload)
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
        if result.status == RunStatus.WAITING_FOR_DECISION:
            evidence = result.decision_evidence or {}
            decision_id = evidence.get("decision_id")
            version = evidence.get("version")
            if self._decision_store is None or not decision_id:
                raise ToolError("waiting run has no cancellable decision")
            try:
                record = self._decision_store.resolve(
                    decision_id,
                    choice="reject",
                    expected_version=version,
                    domain_id=self.domain_id,
                )
            except DecisionLifecycleError as exc:
                raise ToolError(str(exc)) from exc
            result.status = RunStatus.CANCELLED
            result.error = "用户取消了待确认计划。"
            result.decision_evidence = record.evidence()
            self._state_store.save(result)
            self._emit_run_event(result)
            return result
        if result.status not in (RunStatus.PLANNING, RunStatus.EXECUTING):
            raise ToolError("run is not active: " + run_id)
        self._control.request_cancel(run_id)
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
        self._control.clear_cancel(run_id)
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
            result.answer = self._compose_answer(result)
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

    def _plan_policy_evidence(
        self,
        plan: Optional[TaskPlan],
        workflow: Optional[Mapping[str, Any]],
        *,
        state: str = "accepted",
        reason_code: Optional[str] = None,
        repair_lineage: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Project Domain policy metadata through one generic Runtime seam."""
        domain_policy = resolve_plan_policy(
            self._domain_pack,
            plan,
            workflow=workflow,
        )
        return build_plan_policy_evidence(
            plan,
            domain_policy=domain_policy,
            workflow=workflow,
            domain_id=self.domain_id,
            state=state,
            reason_code=reason_code,
            repair_lineage=tuple(repair_lineage or ()),
        )

    def _failure_plan_evidence(
        self,
        *,
        plan: Optional[TaskPlan],
        workflow: Optional[Mapping[str, Any]],
        state: str,
        reason_code: str,
        context_packet: Optional[ContextPacket] = None,
        repair_lineage: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create planning evidence even when no executable plan survived."""
        selection = None
        if context_packet is not None:
            sections = (
                context_packet.source_payload or context_packet.payload or {}
            ).get("sections", {})
            if isinstance(sections, Mapping):
                selection = sections.get("workflow_selection")
        return {
            "available": False,
            "planner_kind": type(self._planner).__name__,
            "source": _planner_source(type(self._planner).__name__, workflow),
            "domain_id": self.domain_id,
            "step_count": len(plan.steps) if isinstance(plan, TaskPlan) else 0,
            "tool_names": [step.tool for step in plan.steps]
            if isinstance(plan, TaskPlan)
            else [],
            "plan_policy": self._plan_policy_evidence(
                plan,
                workflow,
                state=state,
                reason_code=reason_code,
                repair_lineage=repair_lineage,
            ),
            "workflow_selection": normalize_workflow_selection_evidence(selection),
            "planner_selection": build_planner_selection_evidence(
                plan,
                selection,
                planner_kind=type(self._planner).__name__,
            ),
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
        catalog = self._domain_pack.capability_catalog(
            environment=self._backend_name or "unknown"
        )
        catalog_runtime_evidence = self._capability_context_evidence()
        catalog = project_capability_catalog_evidence(
            catalog,
            runtime_evidence=catalog_runtime_evidence,
        )
        discovery_payload = enrich_discovery_context(
            discovery_payload,
            spatial_request,
            catalog,
            # Keep the planner context compact while retaining enough choices
            # for an open request to continue without a fixed question page.
            max_suggestions=4,
        )
        domain_selection = resolve_workflow_selection(
            self._domain_pack,
            discovery_payload,
            spatial_request,
            workflow=workflow,
        )
        workflow_selection = build_workflow_selection_evidence(
            discovery=discovery_payload,
            domain_selection=domain_selection,
            workflow=workflow,
            capability_catalog=catalog,
            domain_seams=workflow_seam_summary(self._domain_pack),
            request_facts=spatial_request,
            domain_id=self.domain_id,
        )
        domain_guidance = resolve_evidence_action_guidance(
            self._domain_pack,
            workflow_selection,
            request_facts=spatial_request,
        )
        workflow_selection = build_workflow_selection_evidence(
            discovery=discovery_payload,
            domain_selection=domain_selection,
            workflow=workflow,
            capability_catalog=catalog,
            domain_seams=workflow_seam_summary(self._domain_pack),
            request_facts=spatial_request,
            domain_id=self.domain_id,
            evidence_action_guidance=domain_guidance,
        )
        workflow_templates = _compact_workflow_templates_for_context(
            workflow_context(self._domain_pack),
            workflow_selection,
        )
        capability_catalog = capability_context_summary(
            catalog=catalog,
            tool_definitions=self._registry.definition_summary(),
            tool_provider=self._registry.provider_info(),
            tool_provider_health=self._registry.provider_health(),
            tool_governance=self._registry.governance_summary(max_tools=4),
            selected_capability_ids=selected_capability_ids(capability_discovery)[:1],
            max_capabilities=1,
            max_tools=12,
        )
        planner_sections = project_planner_sections(
            capability_discovery=discovery_payload,
            capability_catalog=capability_catalog,
            workflow_selection=workflow_selection,
            workflow_templates=workflow_templates,
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
            workflow_selection=workflow_selection,
            memory_section=memory_section,
            workflow_templates=workflow_templates,
            planner_section_overrides=planner_sections,
            planner_projection_schema_version=(
                PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION
            ),
        )

    def _capability_context_evidence(self) -> Mapping[str, Any]:
        return self._capability_surface.context_evidence()

    def _resolve_request(
        self,
        request: str,
        session_id: str,
        *,
        pending: Optional[PendingClarification] = None,
        turn_advice: Optional[Mapping[str, Any]] = None,
    ) -> str:
        pending = pending if pending is not None else self._conversation_store.get_pending(session_id)
        advice = turn_advice or resolve_turn_mode(
            self._domain_pack,
            request,
            pending_request=pending.request if pending is not None else None,
            pending_error=pending.error if pending is not None else None,
        )
        mode = str(advice.get("mode") or "unknown") if isinstance(advice, Mapping) else "unknown"
        if pending is not None and mode in {
            "clarification_reply",
            "follow_up",
            "decision_reply",
        }:
            return request.strip() + " " + pending.request.strip()
        if pending is not None:
            # A clearly independent request starts a new turn.  Do not let an
            # old clarification leak into its planner context.
            self._conversation_store.clear_pending(session_id)
        previous = self._conversation_store.get_last_request(session_id)
        follow_up = ("继续", "刚才", "上面", "这个结果", "该结果", "改成", "调整为", "换成")
        if previous and any(term in request for term in follow_up):
            return request.strip() + "。基于上一轮请求：" + previous.strip()
        return request

    def _require_workflow_selection(
        self,
        context_packet: ContextPacket,
        workflow: Optional[Mapping[str, Any]],
    ) -> None:
        """Stop before planning when a Domain declares an ambiguous choice.

        Candidate discovery is descriptive by default. A Domain Pack may
        explicitly mark the projection as ``ambiguous`` when lexical or
        policy routing cannot safely choose one capability. The public
        Runtime owns the lifecycle transition, while the Domain remains the
        owner of candidate semantics. An explicit workflow is already a
        user decision and therefore bypasses this gate.
        """
        return _runtime_planning.require_workflow_selection(context_packet, workflow)

    def _planner_metrics(self) -> Optional[Dict]:
        metrics = getattr(self._planner, "metrics", None)
        return metrics() if callable(metrics) else None

    def _compose_answer(self, result: AgentRunResult) -> str:
        """Generate a natural-language answer with a deterministic fallback.

        The Domain Composer remains responsible for the trusted fallback.  A
        model may rewrite only the bounded facts assembled by the answer
        generator; it never replaces tool execution or evidence ownership.
        """

        fallback = self._answer_composer.compose(result)
        generator = self._answer_generator
        generate = getattr(generator, "generate", None) if generator is not None else None
        if not callable(generate):
            result.answer_generation_evidence = fallback_answer_generation_evidence(
                "answer_generation_disabled"
            )
            return _append_execution_degradation_notice(result, fallback)
        try:
            generated = generate(result)
            answer = getattr(generated, "answer", None)
            evidence = getattr(generated, "evidence", None)
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("answer generator returned an empty answer")
            result.answer_generation_evidence = (
                dict(evidence) if isinstance(evidence, Mapping) else
                fallback_answer_generation_evidence("answer_generation_evidence_missing")
            )
            return _append_execution_degradation_notice(result, answer.strip())
        except Exception:
            failure_evidence = getattr(generator, "failure_evidence", None)
            if callable(failure_evidence):
                result.answer_generation_evidence = failure_evidence(
                    "answer_generation_failed"
                )
            else:
                result.answer_generation_evidence = fallback_answer_generation_evidence(
                    "answer_generation_failed"
                )
            return _append_execution_degradation_notice(result, fallback)

    def _validate_or_repair_plan(
        self,
        plan: TaskPlan,
        request: str,
        workflow: Optional[Mapping[str, Any]],
        *,
        deadline: Optional[float],
        result: Optional[AgentRunResult] = None,
        run_id: Optional[str] = None,
        context_packet: Optional[ContextPacket] = None,
    ) -> tuple[TaskPlan, Optional[Dict[str, Any]]]:
        """Validate a plan and make one bounded model repair if needed.

        This is the planning-phase seam: no tool has run, so a repaired plan
        replaces the whole candidate rather than being merged with execution
        state.  The replacement still crosses the same workflow and Registry
        validation as the original plan.
        """

        try:
            self._validate_plan_for_execution(plan, workflow)
            return plan, None
        except Exception as exc:
            replacement, event = self._try_plan_repair(
                request,
                plan,
                workflow,
                exc,
                deadline,
                run_id=run_id,
                context_packet=context_packet,
            )
            if result is not None:
                if event is not None:
                    result.replan_events.append(event)
            if replacement is None or event is None:
                raise
            return replacement, event

    def _validate_plan_for_execution(
        self, plan: TaskPlan, workflow: Optional[Mapping[str, Any]]
    ) -> None:
        if workflow is not None:
            workflow_validator = getattr(self._domain_pack, "validate_workflow_plan", None)
            if callable(workflow_validator):
                workflow_validator(plan, workflow)
        domain_validator = getattr(self._domain_pack, "validate_plan", None)
        if callable(domain_validator):
            domain_validator(plan)
        if plan.output.get("type") != "direct_answer":
            self._validate_plan(plan)

    def _try_plan_repair(
        self,
        request: str,
        plan: TaskPlan,
        workflow: Optional[Mapping[str, Any]],
        exc: Exception,
        deadline: Optional[float],
        run_id: Optional[str],
        context_packet: Optional[ContextPacket],
    ) -> tuple[Optional[TaskPlan], Optional[Dict[str, Any]]]:
        capability_context = {}
        if context_packet is not None:
            source_payload = context_packet.source_payload or context_packet.payload
            sections = source_payload.get("sections", {})
            if isinstance(sections, Mapping):
                capability_context = {
                    key: sections[key]
                    for key in (
                        "available_tools",
                        "capability_discovery",
                        "capability_catalog",
                        "workflow_templates",
                    )
                    if key in sections
                }
        outcome = self._plan_repair_engine.repair(
            PlanRepairInput(
                request=request,
                candidate=plan,
                workflow=workflow,
                validation_error=str(exc),
                run_id=run_id,
                deadline=deadline,
                capability_context=capability_context,
            )
        )
        return outcome.plan, outcome.event

    def _plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]],
        context_packet: ContextPacket,
    ) -> TaskPlan:
        return _runtime_planning.invoke_planner(
            self._planner,
            request,
            workflow,
            context_packet,
        )

    def _validate_plan(self, plan: TaskPlan) -> None:
        return _runtime_planning.validate_plan(
            plan,
            self._registry.names,
            self._max_steps,
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
        hooks = _runtime_execution.StepExecutionHooks(
            registry=self._registry,
            max_retries=self._max_retries,
            preflight=self._enforce_preflight_policy,
            control_check=self._check_control,
            emit_step=self._emit_step_event,
            now=_utc_now,
        )
        return _runtime_execution.execute_step(
            hooks,
            run_id,
            deadline,
            step_run,
            step,
            completed,
            completed_results,
        )

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
        original_quality = diagnose_plan(
            result.plan,
            workflow_context(self._domain_pack),
        )
        feedback = self._replan_policy.feedback_payload(
            request=request,
            completed_steps=completed_steps,
            failed_step=failed_payload,
            remaining_tools=self._registry.names,
            output_type=(result.plan.output or {}).get("type"),
            plan_quality=original_quality,
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
            self._validate_plan_for_execution(merged, result.workflow)
            merged_quality = diagnose_plan(
                merged,
                workflow_context(self._domain_pack),
            )
            if merged_quality.get("available") and not merged_quality.get("passed"):
                raise ToolError("replanned workflow blueprint mismatch")
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
            if isinstance(result.plan_evidence, dict):
                result.plan_evidence["plan_quality"] = project_plan_quality_evidence(
                    merged_quality
                )
            result.replan_events.append(
                build_replan_event(
                    failed_step_id=step.id,
                    failed_tool=step.tool,
                    failure_category=step_run.error_category or failure_category(str(exc)),
                    new_step_ids=new_step_ids,
                    latency_ms=(perf_counter() - started) * 1000,
                    plan_quality_before=original_quality,
                    plan_quality_after=merged_quality,
                )
            )
            if isinstance(result.plan_evidence, dict):
                result.plan_evidence["plan_policy"] = self._plan_policy_evidence(
                    merged,
                    result.workflow,
                    state="accepted",
                    reason_code="execution_replan_accepted",
                    repair_lineage=result.replan_events,
                )
                result.plan_evidence["plan_identity"] = build_plan_identity(
                    merged,
                    request=result.request,
                    resolved_request=result.resolved_request or result.request,
                    workflow=result.workflow,
                    planner_kind=type(self._planner).__name__,
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
        return self._control.check(run_id, deadline)

    def _block_remaining_steps(
        self, steps, start_index: int, failed_step_id: str, reason: str
    ) -> None:
        return _runtime_execution.block_remaining_steps(
            steps,
            start_index,
            failed_step_id,
            reason,
        )

def _plan_to_dict(plan: TaskPlan) -> Dict[str, Any]:
    return _runtime_projection.plan_to_dict(plan)


def _plan_dag(plan: TaskPlan) -> Dict[str, Any]:
    return _runtime_projection.plan_dag(plan)


def _compact_workflow_templates_for_context(
    templates: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _runtime_projection.compact_workflow_templates(templates, selection)


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
    source_payload = context_packet.source_payload or context_packet.payload
    sections = (source_payload or {}).get("sections", {})
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
        # Keep the projection shape stable even when a bounded context has
        # omitted the catalog. Consumers can distinguish an empty projection
        # from unavailable catalog evidence via the boolean above.
        "capability_catalog_ids": [],
        "capability_catalog_tool_schema_count": 0,
        "plan_identity": build_plan_identity(
            plan,
            request=str(request_section.get("original") or ""),
            resolved_request=str(request_section.get("resolved") or ""),
            workflow=workflow,
            planner_kind=planner_kind,
        ),
        "evidence_binding": build_evidence_binding(context_packet.payload),
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
            "entities": _safe_small_mapping(request_facts.get("entities")),
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
    # Keep the historical top-level capability projection available when the
    # compact context builder has omitted the verbose discovery section.  The
    # values still come from the domain-neutral workflow-selection contract;
    # this is a compatibility alias, not a second selection implementation.
    selection_section = sections.get("workflow_selection")
    if isinstance(selection_section, Mapping):
        if "selected_capability_id" not in evidence:
            evidence["selected_capability_id"] = selection_section.get(
                "selected_capability_id"
            )
        if "capability_candidate_ids" not in evidence:
            candidate_ids = selection_section.get("candidate_ids")
            evidence["capability_candidate_ids"] = (
                [str(item) for item in candidate_ids[:8]]
                if isinstance(candidate_ids, list)
                else []
            )
        if "capability_candidate_count" not in evidence:
            evidence["capability_candidate_count"] = selection_section.get(
                "candidate_count"
            )
    alignment_selection = dict(selection_section) if isinstance(selection_section, Mapping) else {}
    if isinstance(capability_section, Mapping):
        for key in ("selected_capability_id", "candidate_ids", "candidate_count"):
            if key not in alignment_selection and key in capability_section:
                alignment_selection[key] = capability_section.get(key)
    if (
        not alignment_selection.get("candidate_details")
        and isinstance(capability_catalog_section, Mapping)
        and isinstance(capability_catalog_section.get("capabilities"), list)
    ):
        alignment_selection["candidate_details"] = capability_catalog_section.get("capabilities")
    template_section = sections.get("workflow_templates")
    templates = (
        template_section.get("templates")
        if isinstance(template_section, Mapping)
        else None
    )
    if isinstance(templates, list):
        existing_details = alignment_selection.get("candidate_details")
        existing_details = existing_details if isinstance(existing_details, list) else []
        existing_ids = {
            item.get("id")
            for item in existing_details
            if isinstance(item, Mapping) and item.get("id")
        }
        alignment_selection["candidate_details"] = existing_details + [
            {
                "id": item.get("id"),
                "result_types": item.get("result_types") or [item.get("output_type")],
            }
            for item in templates
            if isinstance(item, Mapping)
            and item.get("id")
            and item.get("id") not in existing_ids
        ]
    evidence["planner_selection"] = build_planner_selection_evidence(
        plan,
        alignment_selection,
        planner_kind=planner_kind,
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
    evidence["workflow_selection"] = normalize_workflow_selection_evidence(
        sections.get("workflow_selection")
    )
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
    evidence["plan_quality"] = project_plan_quality_evidence(
        diagnose_plan(
            plan,
            {"workflow_templates": templates_section}
            if isinstance(templates_section, Mapping)
            else {},
        )
    )
    return evidence


def _planner_source(planner_kind: str, workflow: Optional[Mapping[str, Any]]) -> str:
    return _runtime_projection.planner_source(planner_kind, workflow)


def _matched_template_ids(
    templates_section: Mapping[str, Any],
    *,
    output_type: str,
    tool_names: list[str],
    step_count: int,
    steps: list[Mapping[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    return _runtime_projection.matched_template_ids(
        templates_section,
        output_type=output_type,
        tool_names=tool_names,
        step_count=step_count,
        steps=steps,
    )


def _blueprint_steps_match(
    blueprint_steps: list[Mapping[str, Any]],
    actual_steps: list[Mapping[str, Any]],
) -> bool:
    return _runtime_projection.blueprint_steps_match(blueprint_steps, actual_steps)


def _safe_small_mapping(value: Any) -> Dict[str, Any]:
    return _runtime_projection.safe_small_mapping(value)


def _append_execution_degradation_notice(
    result: AgentRunResult,
    answer: str,
) -> str:
    return _runtime_projection.append_execution_degradation_notice(result, answer)


def _unique(values: list[str]) -> list[str]:
    return _runtime_projection.unique(values)


def _replan_context(feedback: Mapping[str, Any]) -> Dict[str, Any]:
    return _runtime_projection.replan_context(feedback)


def _utc_now() -> str:
    return _runtime_projection.utc_now()


def _capability_evidence_cache_ttl() -> float:
    return _runtime_projection.capability_evidence_cache_ttl()


def _resolve_result_references(value: Any, results: Dict[str, Dict[str, Any]]) -> Any:
    return _runtime_projection.resolve_result_references(value, results)


def _result_type_for_observability(result: AgentRunResult) -> str:
    return _runtime_projection.result_type_for_observability(result)


def _run_duration_ms(result: AgentRunResult) -> Optional[float]:
    return _runtime_projection.run_duration_ms(result)


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
    return _runtime_projection.run_error_category(result)
