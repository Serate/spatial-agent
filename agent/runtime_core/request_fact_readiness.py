"""Bounded, domain-neutral readiness for Planner-facing request facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


REQUEST_FACT_READINESS_SCHEMA_VERSION = "spatial-agent.request-fact-readiness.v1"
_STATES = {"complete", "partial", "missing", "unavailable"}
_MAX_FIELDS = 8


def build_request_fact_readiness(
    requirements: Any,
    facts: Any,
    *,
    discovery_state: Any = "available",
) -> dict[str, Any]:
    """Classify request facts without deciding or authorizing a capability.

    Missing facts remain execution-blocking, but are not automatically
    Planner-blocking. Domain-owned requirements are treated as opaque
    declarations; this module never interprets a field name or domain ID.
    """

    requirement = requirements if isinstance(requirements, Mapping) else {}
    missing = _missing_fields(requirement.get("missing_fields"))
    state = str(discovery_state or "available").strip().lower()
    if state == "unavailable":
        readiness = "unavailable"
    elif not missing:
        readiness = "complete"
    elif _has_observed_facts(facts):
        readiness = "partial"
    else:
        readiness = "missing"
    return {
        "schema_version": REQUEST_FACT_READINESS_SCHEMA_VERSION,
        "state": readiness,
        "planner_available": readiness != "unavailable",
        "execution_blocking": readiness in {"partial", "missing", "unavailable"},
        "missing_fields": missing,
        "source": "domain_requirements",
    }


def project_request_fact_readiness(value: Any) -> dict[str, Any]:
    """Project readiness across the provider/artifact boundary."""

    source = value if isinstance(value, Mapping) else {}
    state = str(source.get("state") or "missing").strip().lower()
    if state not in _STATES:
        state = "missing"
    return {
        "schema_version": REQUEST_FACT_READINESS_SCHEMA_VERSION,
        "state": state,
        "planner_available": bool(
            source.get("planner_available", state != "unavailable")
        ),
        "execution_blocking": bool(
            source.get("execution_blocking", state != "complete")
        ),
        "missing_fields": _missing_fields(source.get("missing_fields")),
        "source": "domain_requirements",
    }


def _missing_fields(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    values = value if isinstance(value, Sequence) and not isinstance(value, str) else ()
    for raw in values:
        if not isinstance(raw, Mapping):
            continue
        field_id = str(raw.get("id") or "").strip()[:80]
        label = str(raw.get("label") or "").strip()[:120]
        kind = str(raw.get("kind") or "").strip()[:32]
        if not field_id or not label or kind not in {"entity", "dataset", "constraint"}:
            continue
        result.append({"id": field_id, "label": label, "kind": kind})
        if len(result) >= _MAX_FIELDS:
            break
    return result


def _has_observed_facts(value: Any) -> bool:
    source = value if isinstance(value, Mapping) else {}
    entities = source.get("entities")
    constraints = source.get("constraints")
    return bool(
        isinstance(entities, Mapping)
        and any(item is not None and str(item).strip() for item in entities.values())
    ) or bool(
        isinstance(constraints, Mapping)
        and any(item is not None and str(item).strip() for item in constraints.values())
    )


__all__ = [
    "REQUEST_FACT_READINESS_SCHEMA_VERSION",
    "build_request_fact_readiness",
    "project_request_fact_readiness",
]
