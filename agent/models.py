from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from agent.execution_contract import build_execution_record


class RunStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
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
    resolved_request: Optional[str] = None
    # Structured request interpretation shared by planning, recovery and
    # result consumers. The original text remains in ``request``.
    request_facts: Optional[Dict[str, Any]] = None
    plan: Optional[TaskPlan] = None
    planner_metrics: Optional[Dict[str, Any]] = None
    steps: List[StepRun] = field(default_factory=list)
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
        if data.get("request_facts") is None:
            data.pop("request_facts", None)
        return data
