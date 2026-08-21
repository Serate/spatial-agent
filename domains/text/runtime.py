"""Factory for the complete non-GIS text Runtime replay."""

from __future__ import annotations

from typing import Any

from agent.observability import ObservabilityEmitter
from agent.runtime import AgentRuntime
from .domain import TEXT_DOMAIN_PACK


def build_text_runtime(
    planner_name: str = "rule",
    backend_name: str = "memory",
    state_store: Any = None,
    conversation_store: Any = None,
    memory: Any = None,
    observability: ObservabilityEmitter | None = None,
    decision_store: Any = None,
    **_: Any,
) -> AgentRuntime:
    from agent.runtime_factory import build_runtime

    return build_runtime(
        planner_name,
        backend_name,
        state_store=state_store,
        conversation_store=conversation_store,
        memory=memory,
        observability=observability,
        decision_store=decision_store,
        domain_pack=TEXT_DOMAIN_PACK,
    )
