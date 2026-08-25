from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from agent.execution_contract import build_execution_record
from agent.conversation_turn import normalize_conversation_turn
from agent.runtime_context import normalize_runtime_context
from agent.nested_schema import normalize_domain_routing_evidence_contract


class RunStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_FOR_DECISION = "WAITING_FOR_DECISION"
    COMPLETED = "COMPLETED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


@dataclass(frozen=True)
class PlanStep:
    id: str
    tool: str
    args: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskPlan:
    goal: str
    steps: List[PlanStep]
    output: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)


@dataclass
class StepRun:
    id: str
    tool: str
    args: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)
    status: str = "PENDING"
    attempts: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_category: Optional[str] = None
    error_code: Optional[str] = None
    retryable: Optional[bool] = None
    # Safe snapshot of the Registry governance used for this dispatch.
    governance: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    latency_ms: Optional[float] = None


@dataclass
class AgentRunResult:
    run_id: str
    status: RunStatus
    request: str
    session_id: Optional[str] = None
    # Domain-neutral, bounded identity of how this input related to session
    # continuation.  Raw pending request text is never persisted here.
    conversation_turn: Optional[Dict[str, Any]] = None
    # Stable Domain Pack identity used to isolate persistence and recovery.
    # Older synthetic fixtures may omit it; real Runtime runs populate it.
    domain_id: Optional[str] = None
    # Bounded evidence proving which Domain routing decision accepted this run.
    # Direct/legacy runs carry an explicit unavailable representation.
    domain_routing_evidence: Optional[Dict[str, Any]] = None
    # Immutable, bounded configuration evidence for this execution.
    runtime_context: Optional[Dict[str, Any]] = None
    # Normalized semantic spatial context retained for result reconstruction.
    # It is distinct from runtime_context: the latter describes execution
    # configuration, while this value contributes to request identity.
    spatial_context: Optional[Dict[str, Any]] = None
    resolved_request: Optional[str] = None
    # Structured request interpretation shared by planning, recovery and
    # result consumers. The original text remains in ``request``.
    request_facts: Optional[Dict[str, Any]] = None
    plan: Optional[TaskPlan] = None
    planner_metrics: Optional[Dict[str, Any]] = None
    # Safe evidence for the optional natural-language answer generation pass.
    # The model input and raw response are never persisted here.
    answer_generation_evidence: Optional[Dict[str, Any]] = None
    steps: List[StepRun] = field(default_factory=list)
    # Canonical domain-neutral result envelope. Composite runs use this field
    # so SQLite/artifact recovery can preserve the exact public Result
    # Contract instead of rebuilding it from synthetic child steps.
    result: Optional[Dict[str, Any]] = None
    answer: Optional[str] = None
    error: Optional[str] = None
    error_category: Optional[str] = None
    error_code: Optional[str] = None
    failure: Optional[Dict[str, Any]] = None
    clarification: Optional[Dict[str, Any]] = None
    # Normalized workflow selection retained for async polling and restart recovery.
    workflow: Optional[Dict[str, Any]] = None
    artifact_ref: Optional[str] = None
    geojson_ref: Optional[str] = None
    # Final bounded GeoJSON evidence persisted for async polling/recovery.
    geometry_evidence: Optional[Dict[str, Any]] = None
    # Safe summary of the planner context; raw context is never persisted here.
    context_evidence: Optional[Dict[str, Any]] = None
    # Safe summary of how the TaskPlan was produced and matched to templates.
    plan_evidence: Optional[Dict[str, Any]] = None
    # Number of in-place retries performed for this run.
    retry_count: int = 0
    # Bounded adaptive-replanning evidence (M80.1): one entry per replan round.
    replan_events: List[Dict[str, Any]] = field(default_factory=list)
    # Bounded user decision lifecycle evidence (M151).
    decision_evidence: Optional[Dict[str, Any]] = None
    # Versioned evidence index retained in SQLite/history snapshots (M159).
    evidence_registry: Optional[Dict[str, Any]] = None
    # Generic, bounded receipt for an interaction/lifecycle/recovery action.
    action_receipt: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["execution_record"] = build_execution_record(data, kind="run")
        for key in ("artifact_ref", "geojson_ref"):
            if data.get(key) is None:
                data.pop(key, None)
        if data.get("error_category") is None:
            data.pop("error_category", None)
        if data.get("error_code") is None:
            data.pop("error_code", None)
        if data.get("failure") is None:
            data.pop("failure", None)
        if data.get("workflow") is None:
            data.pop("workflow", None)
        if data.get("domain_id") is None:
            data.pop("domain_id", None)
        data["domain_routing_evidence"] = normalize_domain_routing_evidence_contract(
            data.get("domain_routing_evidence"),
            expected_domain_id=data.get("domain_id"),
        )
        if data.get("runtime_context") is not None:
            data["runtime_context"] = normalize_runtime_context(data["runtime_context"])
        if data.get("runtime_context") is None:
            data.pop("runtime_context", None)
        if data.get("spatial_context") is None:
            data.pop("spatial_context", None)
        elif isinstance(data.get("spatial_context"), dict):
            data["spatial_context"] = dict(data["spatial_context"])
        if data.get("request_facts") is None:
            data.pop("request_facts", None)
        if data.get("answer_generation_evidence") is None:
            data.pop("answer_generation_evidence", None)
        if data.get("result") is None:
            data.pop("result", None)
        if data.get("conversation_turn") is None:
            data.pop("conversation_turn", None)
        else:
            data["conversation_turn"] = normalize_conversation_turn(
                data["conversation_turn"]
            )
        if data.get("decision_evidence") is None:
            data.pop("decision_evidence", None)
        if data.get("evidence_registry") is None:
            data.pop("evidence_registry", None)
        if data.get("action_receipt") is None:
            data.pop("action_receipt", None)
        return data
