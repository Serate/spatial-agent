"""Planning-only Runtime preview seam.

Preview builds the same bounded planning evidence as execution without
dispatching tools or mutating run state.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, Mapping, Optional

from ..action_lifecycle import project_action_lifecycle
from ..conversation_turn import build_conversation_turn, resolve_turn_mode
from ..domain_contract import clarification_details as resolve_clarification_details, extract_request_facts
from ..evidence_revalidation import build_evidence_binding
from ..errors import ClarificationNeeded, RequestRejected, ToolError
from ..models import RunStatus, TaskPlan
from .component_fact_handoff import (
    ComponentFactHandoffError,
    normalize_component_fact_handoff,
    project_component_fact_handoff,
    request_facts_from_handoff,
)
from .projection import plan_dag as _plan_dag, plan_to_dict as _plan_to_dict


class RuntimePreviewSurface:
    """Own planning-only preview projection for an injected Runtime."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def preview(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        resolved_request_override: Optional[str] = None,
        component_fact_handoff: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Plan a request and return a bounded DAG preview without dispatching tools."""
        runtime = self._runtime
        from .. import runtime as _runtime_module
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
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
        handoff = None
        handoff_requires_clarification = False
        if component_fact_handoff is not None:
            try:
                handoff = normalize_component_fact_handoff(
                    component_fact_handoff,
                    expected_domain_id=str(runtime.domain_id),
                )
            except ComponentFactHandoffError as exc:
                raise ToolError(str(exc)) from exc
            request_facts = request_facts_from_handoff(
                handoff,
                text=resolved_request,
                require_ready=False,
            )
            handoff_requires_clarification = handoff.get("state") != "ready"
            if not handoff_requires_clarification and isinstance(workflow, Mapping):
                workflow = _merge_component_handoff_constraints(
                    workflow,
                    handoff.get("effective_constraints"),
                )
        else:
            request_facts = extract_request_facts(runtime._domain_pack, resolved_request)
        context_packet = runtime._build_context_packet(
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
            "domain_id": runtime.domain_id,
            "runtime_context": runtime.runtime_context(),
            "request_facts": request_facts.as_context_dict(),
            "workflow": dict(workflow) if workflow is not None else None,
            "context_evidence": context_packet.evidence,
            "execution": {
                "planned_only": True,
                "tool_execution": False,
                "artifact_export": False,
            },
        }
        if handoff is not None:
            payload["component_fact_handoff"] = project_component_fact_handoff(
                handoff
            )
        candidate_plan: Optional[TaskPlan] = None
        try:
            if handoff_requires_clarification:
                raise ClarificationNeeded(
                    "组件还缺少必要输入，请补充后继续。",
                    {
                        "schema_version": "spatial-agent.component-clarification.v1",
                        "state": "component_facts_required",
                        "reason_code": handoff.get("reason_code"),
                        "component_id": handoff.get("component_id"),
                        "domain_id": handoff.get("domain_id"),
                        "capability_id": handoff.get("capability_id"),
                        "missing_fields": list(handoff.get("missing_fields") or [])[:8],
                        "next_actions": ["provide_facts"],
                    },
                )
            runtime._require_workflow_selection(context_packet, workflow)
            plan = runtime._plan(resolved_request, workflow, context_packet)
            candidate_plan = plan
            plan, repair_event = runtime._validate_or_repair_plan(
                plan,
                resolved_request,
                workflow,
                deadline=deadline,
                run_id=None,
                context_packet=context_packet,
            )
            plan_payload = _plan_to_dict(plan)
            plan_evidence = _runtime_module._build_plan_evidence(
                plan,
                workflow,
                context_packet,
                planner_kind=type(runtime._planner).__name__,
            )
            plan_evidence["plan_policy"] = runtime._plan_policy_evidence(
                plan,
                workflow,
                state="accepted",
                reason_code="accepted",
                repair_lineage=[repair_event] if repair_event is not None else [],
            )
            plan_evidence["execution_policy"] = runtime._execution_policy_evidence(plan)
            plan_evidence["evidence_binding"] = build_evidence_binding(
                context_packet.payload
            )
            payload.update({
                "status": "PLANNED",
                "plan": plan_payload,
                "dag": _plan_dag(plan),
                "plan_evidence": plan_evidence,
                "plan_identity": dict(plan_evidence["plan_identity"]),
                "planner_metrics": runtime._planner_metrics(),
            })
            if repair_event is not None:
                payload["replan_events"] = [repair_event]
        except ClarificationNeeded as exc:
            payload.update({
                "status": RunStatus.NEEDS_CLARIFICATION.value,
                "error": str(exc),
                "clarification": exc.details or resolve_clarification_details(
                    runtime._domain_pack, resolved_request
                ) or None,
                "planner_metrics": runtime._planner_metrics(),
            })
            payload["plan_evidence"] = runtime._failure_plan_evidence(
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
                "planner_metrics": runtime._planner_metrics(),
            })
            payload["plan_evidence"] = runtime._failure_plan_evidence(
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
                "planner_metrics": runtime._planner_metrics(),
            })
            payload["plan_evidence"] = runtime._failure_plan_evidence(
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


def _merge_component_handoff_constraints(
    workflow: Mapping[str, Any], handoff_constraints: Any
) -> dict[str, Any]:
    """Merge only keys declared by the already normalized workflow.

    A composite handoff contains facts for the whole component request.  A
    capability such as catalog discovery may intentionally accept no
    constraints, while a query capability accepts a subset of those facts.
    The normalized workflow is the generic authority for that boundary;
    forwarding every handoff key would make discovery workflows fail closed
    with unrelated query constraints.
    """

    result = dict(workflow)
    declared = workflow.get("constraints")
    if not isinstance(declared, Mapping):
        return result
    incoming = handoff_constraints if isinstance(handoff_constraints, Mapping) else {}
    merged = dict(declared)
    merged.update(
        {
            str(key): value
            for key, value in incoming.items()
            if key in declared
        }
    )
    result["constraints"] = merged
    return result
