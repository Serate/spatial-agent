"""Compatibility facade for the former GIS plan composer.

The implementation now belongs to ``domains.gis.rule_planning``.  Existing
imports remain usable while generic Runtime code does not own GIS builders.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import TaskPlan


def _implementation():
    from domains.gis import rule_planning

    return rule_planning


class RuleBasedPlanComposer:
    """Bounded legacy adapter delegating to the GIS Domain implementation."""

    def __init__(self, router: Optional[Any] = None) -> None:
        self._delegate = _implementation().RuleBasedPlanComposer(router)

    @property
    def rule_ids(self):
        return self._delegate.rule_ids

    def compose(self, facts: Any) -> TaskPlan:
        return self._delegate.compose(facts)


def __getattr__(name: str) -> Any:
    if name == "PlanningFacts":
        return _implementation().PlanningFacts
    raise AttributeError(name)
