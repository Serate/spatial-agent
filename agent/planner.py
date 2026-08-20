"""Planner protocol and bounded compatibility facade.

Domain-specific deterministic planners live in their Domain Pack.  The old
``RuleBasedPlanner`` import is retained as a small adapter for callers that
have not migrated to ``DomainPack.rule_planner()`` yet.
"""

from typing import Any, Mapping, Optional, Protocol

from .models import TaskPlan


class Planner(Protocol):
    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        ...


class RuleBasedPlanner:
    """Legacy GIS Planner facade; normal construction is Domain-owned."""

    def __init__(self, composer: Optional[Any] = None) -> None:
        from domains.gis.planner import RuleBasedPlanner as GisRuleBasedPlanner

        self._delegate = GisRuleBasedPlanner(composer)

    @property
    def capability_rules(self):
        return self._delegate.capability_rules

    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        return self._delegate.plan(request, workflow=workflow, context=context)
