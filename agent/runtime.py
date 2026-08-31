"""Compatibility import for the canonical Runtime engine.

The orchestration implementation lives under ``agent.runtime_core``.  This
module intentionally keeps the historical import path stable for callers and
for runtime-core recovery code that still resolves compatibility helpers here.
"""

from agent.runtime_core.runtime_engine import (
    AgentRuntime,
    _build_plan_evidence,
    _plan_to_dict,
    _record_run_failure,
    _resolve_result_references,
)
from agent.agent_settings import open_agent_defaults
from agent.runtime_state import (
    InMemoryConversationStore,
    InMemoryStateStore,
    PendingClarification,
)

__all__ = [
    "AgentRuntime",
    "InMemoryConversationStore",
    "InMemoryStateStore",
    "PendingClarification",
    "open_agent_defaults",
    "_resolve_result_references",
]
