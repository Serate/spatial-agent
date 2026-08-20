"""Domain-neutral capability discovery value objects.

The Runtime only needs these bounded projections.  Lexical signals and route
definitions belong to a Domain Pack implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Tuple


CAPABILITY_DISCOVERY_SCHEMA_VERSION = "spatial-agent.capability-discovery.v1"


@dataclass(frozen=True)
class CapabilityRoute:
    """Declarative route predicate with domain-neutral fact dimensions."""

    capability_id: str
    priority: int
    required_entity: str | None = None
    min_task_count: int = 0
    all_tasks: Tuple[str, ...] = ()
    any_tasks: Tuple[str, ...] = ()
    no_tasks: Tuple[str, ...] = ()
    any_task_groups: Tuple[Tuple[str, ...], ...] = ()
    all_constraints: Tuple[str, ...] = ()
    any_constraints: Tuple[str, ...] = ()
    all_signals: Tuple[str, ...] = ()
    any_signals: Tuple[str, ...] = ()
    no_signals: Tuple[str, ...] = ()

    def matches(
        self,
        *,
        entities: Mapping[str, Any],
        tasks: Sequence[str],
        constraints: Sequence[str],
        signals: Sequence[str],
    ) -> bool:
        task_set = set(tasks)
        constraint_set = set(constraints)
        signal_set = set(signals)
        if self.required_entity and not entities.get(self.required_entity):
            return False
        if len(task_set) < self.min_task_count:
            return False
        if not set(self.all_tasks).issubset(task_set):
            return False
        if self.any_tasks and not task_set.intersection(self.any_tasks):
            return False
        if task_set.intersection(self.no_tasks):
            return False
        if self.any_task_groups and not any(
            set(group).issubset(task_set) for group in self.any_task_groups
        ):
            return False
        if not set(self.all_constraints).issubset(constraint_set):
            return False
        if self.any_constraints and not constraint_set.intersection(self.any_constraints):
            return False
        if not set(self.all_signals).issubset(signal_set):
            return False
        if self.any_signals and not signal_set.intersection(self.any_signals):
            return False
        if signal_set.intersection(self.no_signals):
            return False
        return True


@dataclass(frozen=True)
class CapabilityMatch:
    """A selected capability plus its bounded discovery evidence."""

    capability_id: str
    priority: int
    signals: Tuple[str, ...] = field(default_factory=tuple)
    tasks: Tuple[str, ...] = field(default_factory=tuple)
    constraints: Tuple[str, ...] = field(default_factory=tuple)

    def as_context_dict(self) -> Mapping[str, Any]:
        return {
            "capability_id": self.capability_id,
            "priority": self.priority,
            "signals": list(self.signals),
            "tasks": list(self.tasks),
            "constraints": list(self.constraints),
        }


@dataclass(frozen=True)
class CapabilityDiscovery:
    """Planner-facing JSON-safe discovery projection."""

    signals: Tuple[str, ...]
    tasks: Tuple[str, ...]
    constraints: Tuple[str, ...]
    entities: Mapping[str, Any] = field(default_factory=dict)
    candidates: Tuple[CapabilityMatch, ...] = field(default_factory=tuple)

    @property
    def selected(self) -> CapabilityMatch | None:
        return self.candidates[0] if self.candidates else None

    def as_context_dict(self, *, max_candidates: int = 8) -> Mapping[str, Any]:
        selected = self.selected
        candidates = self.candidates[:max_candidates]
        result = {
            "schema_version": CAPABILITY_DISCOVERY_SCHEMA_VERSION,
            "available": True,
            "signals": list(self.signals),
            "tasks": list(self.tasks),
            "constraints": list(self.constraints),
            "entities": {
                str(key)[:80]: str(value)[:160]
                for key, value in list(self.entities.items())[:16]
                if value is not None
            },
            "selected_capability_id": selected.capability_id if selected else None,
            "candidate_ids": [item.capability_id for item in candidates],
            "candidate_count": len(self.candidates),
            "candidates": [
                {"capability_id": item.capability_id, "priority": item.priority}
                for item in candidates
            ],
        }
        # Keep the old GIS field in the projection for artifact compatibility;
        # new Domain Packs should use ``entities`` instead.
        if self.entities.get("admin_name"):
            result["admin_name"] = str(self.entities["admin_name"])[:120]
        return result
