from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
    plan: Optional[TaskPlan] = None
    planner_metrics: Optional[Dict[str, Any]] = None
    steps: List[StepRun] = field(default_factory=list)
    answer: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data
