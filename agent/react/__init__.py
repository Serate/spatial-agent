"""Bounded, domain-neutral ReAct contracts and execution helpers."""

from .contracts import (
    REACT_ACTIONS,
    REACT_DECISION_SCHEMA_VERSION,
    REACT_EVIDENCE_SCHEMA_VERSION,
    REACT_RUN_STATES,
    ReactDecisionError,
    build_react_evidence,
    build_react_run_evidence,
    normalize_react_decision,
    normalize_react_evidence,
    normalize_react_run_evidence,
    project_react_decision,
    react_decision_schema,
)
from .loop import (
    ReactLoop,
    ReactLoopOutcome,
    ReactToolOutcome,
    invoke_react_decider,
    summarize_tool_result,
)

__all__ = [
    "REACT_ACTIONS",
    "REACT_DECISION_SCHEMA_VERSION",
    "REACT_EVIDENCE_SCHEMA_VERSION",
    "REACT_RUN_STATES",
    "ReactDecisionError",
    "ReactLoop",
    "ReactLoopOutcome",
    "ReactToolOutcome",
    "build_react_evidence",
    "build_react_run_evidence",
    "invoke_react_decider",
    "normalize_react_decision",
    "normalize_react_evidence",
    "normalize_react_run_evidence",
    "project_react_decision",
    "react_decision_schema",
    "summarize_tool_result",
]
