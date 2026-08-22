"""Domain-neutral capability discovery value objects.

The Runtime only needs these bounded projections.  Lexical signals and route
definitions belong to a Domain Pack implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Tuple


CAPABILITY_DISCOVERY_SCHEMA_VERSION = "spatial-agent.capability-discovery.v1"
DISCOVERY_GUIDANCE_SCHEMA_VERSION = "spatial-agent.capability-discovery-guidance.v1"


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
    score: int = 0
    source: str = "domain"
    matched_hints: Tuple[str, ...] = field(default_factory=tuple)

    def as_context_dict(self) -> Mapping[str, Any]:
        result = {
            "capability_id": self.capability_id,
            "priority": self.priority,
            "signals": list(self.signals),
            "tasks": list(self.tasks),
            "constraints": list(self.constraints),
        }
        if self.score:
            result["score"] = self.score
        if self.source:
            result["source"] = self.source
        if self.matched_hints:
            result["matched_hints"] = list(self.matched_hints[:8])
        return result


@dataclass(frozen=True)
class CapabilityDiscovery:
    """Planner-facing JSON-safe discovery projection."""

    signals: Tuple[str, ...]
    tasks: Tuple[str, ...]
    constraints: Tuple[str, ...]
    entities: Mapping[str, Any] = field(default_factory=dict)
    candidates: Tuple[CapabilityMatch, ...] = field(default_factory=tuple)
    selection_state: str = "selected"
    source: str = "domain"

    @property
    def selected(self) -> CapabilityMatch | None:
        return (
            self.candidates[0]
            if self.candidates and self.selection_state == "selected"
            else None
        )

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
            "selection_state": self.selection_state,
            "source": self.source,
            "candidates": [
                item.as_context_dict()
                for item in candidates
            ],
        }
        # Keep the old GIS field in the projection for artifact compatibility;
        # new Domain Packs should use ``entities`` instead.
        if self.entities.get("admin_name"):
            result["admin_name"] = str(self.entities["admin_name"])[:120]
        return result


def discover_from_catalog(
    request: str,
    request_facts: Any,
    capability_definitions: Sequence[Mapping[str, Any]],
    *,
    max_candidates: int = 8,
) -> CapabilityDiscovery:
    """Discover capabilities from Domain-declared hints and request facts.

    This is deliberately lexical-policy agnostic: a Domain Pack declares
    ``request_hints`` beside each capability, while this shared implementation
    only scores phrase/task/dataset/constraint overlap.  It never interprets a
    dataset name, result type, or capability ID.  A single clear match is
    selected; multiple matches remain ambiguous so Runtime can expose a
    structured choice instead of silently taking the first catalog entry.
    """

    facts = _facts_snapshot(request_facts)
    text = str(request or "").strip().lower()
    candidates: list[CapabilityMatch] = []
    for index, definition in enumerate(capability_definitions or ()):
        if not isinstance(definition, Mapping):
            continue
        capability_id = str(definition.get("id") or "").strip()
        hints = definition.get("request_hints")
        if not capability_id or not isinstance(hints, Mapping):
            continue

        phrases = _bounded_strings(hints.get("phrases"))
        hint_tasks = _bounded_strings(hints.get("tasks"))
        hint_datasets = _bounded_strings(hints.get("datasets"))
        hint_constraints = _bounded_strings(hints.get("constraints"))
        required_entities = _bounded_strings(
            hints.get("required_entities") or hints.get("entities")
        )
        phrase_hits = tuple(item for item in phrases if item.lower() in text)
        task_hits = tuple(item for item in hint_tasks if item in facts["tasks"])
        dataset_hits = tuple(item for item in hint_datasets if item in facts["datasets"])
        constraint_hits = tuple(
            item for item in hint_constraints if item in facts["constraints"]
        )
        entity_hits = tuple(
            item for item in required_entities if facts["entities"].get(item)
        )
        if required_entities and len(entity_hits) != len(required_entities):
            continue
        structured_hits = (
            len(task_hits)
            + len(dataset_hits)
            + len(constraint_hits)
            + len(entity_hits)
        )
        # A dataset name alone is too weak to select a capability.  Domain
        # Packs can still provide an explicit phrase for short requests, or
        # two independent fact dimensions for structured requests.
        if not phrase_hits and structured_hits < 2:
            continue
        score = (
            len(phrase_hits) * 8
            + len(task_hits) * 4
            + len(dataset_hits) * 3
            + len(constraint_hits) * 4
            + len(entity_hits)
        )
        if score <= 0:
            continue
        priority = definition.get("discovery_priority", definition.get("priority", index + 100))
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = index + 100
        matched_hints = tuple(
            list(phrase_hits)
            + ["task:" + item for item in task_hits]
            + ["dataset:" + item for item in dataset_hits]
            + ["constraint:" + item for item in constraint_hits]
            + ["entity:" + item for item in entity_hits]
        )
        candidates.append(
            CapabilityMatch(
                capability_id=capability_id,
                priority=priority,
                signals=phrase_hits,
                tasks=task_hits,
                constraints=constraint_hits,
                score=score,
                source="catalog",
                matched_hints=matched_hints,
            )
        )

    # Prefer explicit lexical evidence over broad fact overlap.  For example,
    # “栅格元数据” should not become ambiguous merely because DEM also fits a
    # generic raster-statistics declaration.
    phrase_candidates = [item for item in candidates if item.signals]
    if phrase_candidates:
        candidates = phrase_candidates
    candidates.sort(key=lambda item: (-item.score, item.priority, item.capability_id))
    bounded = tuple(candidates[: max(1, int(max_candidates))])
    state = "selected" if len(bounded) == 1 else "ambiguous" if bounded else "unavailable"
    entities = {
        key: facts["entities"].get(key)
        for key in ("admin_name", "region", "entity", "place")
        if facts["entities"].get(key)
    }
    return CapabilityDiscovery(
        signals=tuple(item for candidate in bounded for item in candidate.signals)[:16],
        tasks=tuple(sorted(facts["tasks"])),
        constraints=tuple(sorted(facts["constraints"])),
        entities=entities,
        candidates=bounded,
        selection_state=state,
        source="catalog",
    )


def enrich_discovery_context(
    discovery: Any,
    request_facts: Any,
    capability_catalog: Mapping[str, Any] | None,
    *,
    max_fields: int = 8,
    max_suggestions: int = 8,
) -> dict[str, Any]:
    """Add bounded, domain-neutral next-step guidance to discovery.

    Discovery itself answers "what matched".  This projection answers the
    follow-up question needed by an Agent UI and Planner: "what is missing, or
    what can the user choose next?"  The catalog remains the only source of
    labels, input facts, result types and availability; the Runtime does not
    interpret capability IDs or domain vocabulary.

    The function accepts either ``CapabilityDiscovery`` or its JSON projection
    so it can be used before persistence without introducing a second domain
    routing implementation.
    """

    source = discovery
    as_context = getattr(discovery, "as_context_dict", None)
    if callable(as_context):
        source = as_context()
    result = dict(source) if isinstance(source, Mapping) else {}
    catalog = capability_catalog if isinstance(capability_catalog, Mapping) else {}
    definitions = [
        item
        for item in (catalog.get("capabilities") or [])
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    ]
    candidate_ids = _bounded_strings(
        result.get("candidate_ids") or result.get("selected_capability_id")
    )
    if result.get("selected_capability_id") and result.get("selected_capability_id") not in candidate_ids:
        candidate_ids.insert(0, str(result["selected_capability_id"])[:96])
    candidate_ids = candidate_ids[:16]

    # Import lazily so the value-object module remains safe for compatibility
    # callers that only need lexical discovery.
    from .capability_catalog import project_clarification_requirements

    requirements = project_clarification_requirements(
        candidate_ids,
        request_facts,
        capability_definitions=definitions,
        max_fields=max_fields,
    )
    missing_fields = [
        item for item in (requirements.get("missing_fields") or [])
        if isinstance(item, Mapping)
    ][: max(1, int(max_fields))]

    suggestions = []
    if not candidate_ids:
        suggestions = _catalog_guidance_cards(
            definitions,
            only_ids=None,
            max_items=max_suggestions,
        )
    state = str(result.get("selection_state") or "unavailable")
    if missing_fields:
        guidance_state = "clarification"
        reason_code = "selected_capability_missing_facts" if len(candidate_ids) == 1 else "candidate_capabilities_missing_facts"
        next_actions = ["补充" + "、".join(str(item.get("label")) for item in missing_fields)]
    elif state == "ambiguous":
        guidance_state = "ambiguous"
        reason_code = "multiple_capabilities"
        next_actions = ["选择一个候选能力", "或补充更明确的任务目标和条件"]
    elif candidate_ids:
        guidance_state = "selected"
        reason_code = "capability_selected"
        next_actions = ["预览计划或继续执行"]
    else:
        guidance_state = "unavailable"
        reason_code = "no_matching_capability"
        next_actions = ["补充任务对象、区域或分析条件", "或从能力目录选择一个能力"]

    guidance = {
        "schema_version": DISCOVERY_GUIDANCE_SCHEMA_VERSION,
        "state": guidance_state,
        "reason_code": reason_code,
        "missing_fields": _normalize_guidance_fields(missing_fields),
        "suggested_capability_ids": [
            str(item.get("id"))[:96] for item in suggestions if item.get("id")
        ][:max(1, int(max_suggestions))],
        "suggested_capability_details": suggestions,
        "next_actions": [str(item)[:160] for item in next_actions[:4]],
    }
    result["guidance"] = guidance
    # Keep the two most useful fields at the discovery boundary as well. This
    # supports older consumers that do not yet understand the nested guidance
    # object while preserving the versioned nested contract for new consumers.
    result["missing_fields"] = guidance["missing_fields"]
    result["suggested_capability_ids"] = guidance["suggested_capability_ids"]
    result["suggested_capability_details"] = guidance["suggested_capability_details"]
    result["discovery_reason_code"] = reason_code
    return result


def _catalog_guidance_cards(
    definitions: Sequence[Mapping[str, Any]],
    *,
    only_ids: Sequence[str] | None,
    max_items: int,
) -> list[dict[str, Any]]:
    allowed = set(only_ids or ())
    cards = []
    for definition in definitions:
        capability_id = str(definition.get("id") or "").strip()
        if not capability_id or (allowed and capability_id not in allowed):
            continue
        requirements = definition.get("request_requirements")
        fields = []
        if isinstance(requirements, Mapping):
            fields = _normalize_guidance_fields(
                requirements.get("clarification_fields") or []
            )
        cards.append(
            {
                "id": capability_id[:96],
                "label": str(definition.get("label") or capability_id)[:120],
                "description": str(
                    definition.get("description")
                    or "提供“{}”能力。".format(definition.get("label") or capability_id)
                )[:320],
                "available": definition.get("available") is not False,
                "input_facts": fields[:16],
                "result_types": _bounded_strings(definition.get("result_types"))[:8],
                "data": {
                    "dataset_gate": str(definition.get("dataset_gate") or "unknown")[:32],
                    "availability_mode": str(definition.get("availability_mode") or "unknown")[:32],
                    "availability_reason": str(definition.get("availability_reason") or "unknown")[:96],
                    "missing_datasets": _bounded_strings(definition.get("missing_datasets"))[:8],
                },
                "actions": ["select_capability", "preview"],
            }
        )
        if len(cards) >= max(1, int(max_items)):
            break
    return cards


def _normalize_guidance_fields(value: Any) -> list[dict[str, str]]:
    values = value if isinstance(value, (list, tuple)) else []
    result = []
    for item in values[:16]:
        if not isinstance(item, Mapping):
            continue
        field_id = str(item.get("id") or "").strip()[:80]
        label = str(item.get("label") or "").strip()[:120]
        kind = str(item.get("kind") or "fact").strip()[:32]
        if field_id and label:
            result.append({"id": field_id, "label": label, "kind": kind})
    return result


def _facts_snapshot(request_facts: Any) -> dict[str, Any]:
    source = request_facts if isinstance(request_facts, Mapping) else None
    if source is None:
        method = getattr(request_facts, "as_context_dict", None)
        value = method() if callable(method) else None
        source = value if isinstance(value, Mapping) else {}
    tasks = source.get("tasks") or ()
    datasets = source.get("datasets") or ()
    constraints = source.get("constraints") or {}
    if isinstance(tasks, str):
        tasks = (tasks,)
    if isinstance(datasets, str):
        datasets = (datasets,)
    if not isinstance(constraints, Mapping):
        constraints = {}
    entities = {
        key: source.get(key)
        for key in ("admin_name", "region", "entity", "place")
    }
    return {
        "tasks": {str(item).strip() for item in tasks if str(item).strip()},
        "datasets": {str(item).strip() for item in datasets if str(item).strip()},
        "constraints": {str(item).strip() for item in constraints if str(item).strip()},
        "entities": entities,
    }


def _bounded_strings(value: Any, *, limit: int = 16) -> tuple[str, ...]:
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple, set)):
        return ()
    result = []
    for item in value:
        text = str(item or "").strip()[:96]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return tuple(result)
