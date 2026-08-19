"""Factory for the complete non-GIS text Runtime replay."""

from __future__ import annotations

from typing import Any

from agent.domain_contract import DomainPack
from agent.observability import ObservabilityEmitter
from agent.runtime import AgentRuntime
from agent.tools import ToolRegistry
from agent.tool_provider import ToolProvider

from .domain import TEXT_DOMAIN_PACK
from .planner import TextSummaryPlanner
from .provider import TextToolProvider


def build_text_runtime(
    planner_name: str = "rule",
    backend_name: str = "memory",
    state_store: Any = None,
    conversation_store: Any = None,
    memory: Any = None,
    observability: ObservabilityEmitter | None = None,
    **_: Any,
) -> AgentRuntime:
    provider: ToolProvider = TextToolProvider()
    registry = ToolRegistry.from_provider(provider)
    return AgentRuntime(
        TextSummaryPlanner(),
        registry,
        state_store=state_store,
        conversation_store=conversation_store,
        memory=memory,
        observability=observability,
        backend_name=backend_name,
        domain_pack=TEXT_DOMAIN_PACK,
    )
