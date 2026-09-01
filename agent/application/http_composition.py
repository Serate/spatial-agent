"""Shared HTTP Composition Root.

Both HTTP entrypoints serve the same Agent Runtime.  This module is the only
place that assembles the Host, product Service, routing application and
Composite applications.  Framework adapters may still choose how to encode a
response, but they must obtain their semantic ``HTTPApplication`` from this
composition rather than rebuilding the graph themselves.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent.answer_generation import LLMCompositeAnswerGenerator
from agent.application.composite import CompositeApplication
from agent.application.composite_planner import LLMCompositePlanner, RuleCompositePlanner
from agent.application.composite_planning import (
    CompositeCapabilityProjector,
    CompositePlanningApplication,
)
from agent.application.composite_runs import CompositeRunApplication
from agent.application.http import HTTPApplication
from agent.domain_registry import resolve_domain_id
from agent.domain_routing_entry import DomainRoutingApplication, routing_state_from_environment
from agent.domain_runtime_host import DomainRuntimeHost
from agent.integration.openai_config import load_answer_generation_config, load_openai_config
from agent.llm_planner import OpenAIPlannerClient
from agent.service import AgentService


def _answer_generator():
    if os.environ.get("SPATIAL_AGENT_DISABLE_LLM_ANSWER") == "1":
        return None
    try:
        config = load_answer_generation_config()
        if not config.get("api_key"):
            return None
        return LLMCompositeAnswerGenerator(OpenAIPlannerClient(**config))
    except Exception:
        return None


def _rule_candidate(_request, _context):
    return {
        "outcome": "needs_clarification",
        "goal": "",
        "message": "规则规划器不会猜测跨领域组合；请切换真实模型或明确提供组合能力。",
        "components": [],
    }


def _planner_factory(planner_name, _backend):
    if str(planner_name).lower() == "openai":
        return LLMCompositePlanner(OpenAIPlannerClient(**load_openai_config()))
    return RuleCompositePlanner(_rule_candidate)


def _repair_planner_factory(planner_name, _backend):
    if str(planner_name).lower() == "openai":
        config = load_openai_config()
        config["max_retries"] = 0
        return LLMCompositePlanner(OpenAIPlannerClient(**config))
    return None


@dataclass
class HTTPComposition:
    """The shared runtime graph owned by one HTTP process."""

    host: DomainRuntimeHost
    service: AgentService
    routing: DomainRoutingApplication
    composite: CompositeRunApplication
    composite_planning: CompositePlanningApplication
    _closed: bool = False

    def http_application(self, target_service: Optional[AgentService] = None) -> HTTPApplication:
        """Build a thin semantic adapter for the selected Service."""
        return build_http_application(
            target_service or self.service,
            routing=self.routing,
            composite=self.composite,
            composite_planning=self.composite_planning,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.composite.close()
        self.service.close()
        self.host.close()


def build_http_composition(*, legacy_domain_id: Optional[str] = None) -> HTTPComposition:
    """Create the single runtime graph used by both HTTP entrypoints."""
    host = DomainRuntimeHost()
    host.start()
    service = AgentService(
        general=True,
        legacy_domain_id=resolve_domain_id(legacy_domain_id or "gis"),
    )
    service.start_reaper()
    routing = DomainRoutingApplication(host, state=routing_state_from_environment())
    composite = CompositeRunApplication(
        coordinator=CompositeApplication(host=host, require_execution_binding=True),
        answer_generator=_answer_generator(),
    )
    composite_planning = CompositePlanningApplication(
        host=host,
        projector=CompositeCapabilityProjector(host),
        planner=RuleCompositePlanner(_rule_candidate),
        composite_runs=composite,
        planner_factory=_planner_factory,
        repair_planner_factory=_repair_planner_factory,
    )
    return HTTPComposition(
        host=host,
        service=service,
        routing=routing,
        composite=composite,
        composite_planning=composite_planning,
    )


def build_http_application(
    service: AgentService,
    *,
    routing: DomainRoutingApplication,
    composite: CompositeRunApplication,
    composite_planning: CompositePlanningApplication,
) -> HTTPApplication:
    """Build the shared semantic adapter from explicitly supplied dependencies.

    Keeping dependencies as arguments preserves the small test seam of both
    entrypoints: replacing a module-level Service or Composite adapter is
    observed at request time instead of being hidden in a captured object.
    """
    return HTTPApplication(
        service,
        use_product_defaults=True,
        routing=routing,
        composite=composite,
        composite_planning=composite_planning,
        action_handler=AgentService.estimate_area_handler,
        on_session_clear=lambda session_id: routing.forget_session(
            session_id, keep_binding=True
        ),
        on_session_delete=routing.forget_session,
    )


__all__ = ["HTTPComposition", "build_http_application", "build_http_composition"]
