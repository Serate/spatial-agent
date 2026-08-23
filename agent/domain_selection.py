"""Versioned, transport-neutral selection of one registered Domain Pack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent.domain_registry import DomainRegistry, DomainSelectionError, domain_registry


DOMAIN_SELECTION_SCHEMA_VERSION = "spatial-agent.domain-selection.v1"
_SELECTION_SOURCES = frozenset({"explicit", "automatic", "restored", "legacy"})


@dataclass(frozen=True)
class DomainSelection:
    """A validated decision about which Domain owns one operation.

    ``domain_id`` is always resolved through the deployment allowlist.  The
    source records how the decision was made without coupling the Host to
    request interpretation or planner behavior.
    """

    domain_id: str
    source: str = "explicit"
    schema_version: str = DOMAIN_SELECTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "domain_id": self.domain_id,
            "source": self.source,
        }


def resolve_domain_selection(
    value: DomainSelection | Mapping[str, Any] | str,
    *,
    registry: DomainRegistry | None = None,
    source: str = "explicit",
) -> DomainSelection:
    """Normalize and validate a selection without an implicit GIS fallback."""

    selected_registry = registry or domain_registry()
    schema_version = DOMAIN_SELECTION_SCHEMA_VERSION
    domain_id: Any = value
    selected_source: Any = source

    if isinstance(value, DomainSelection):
        schema_version = value.schema_version
        domain_id = value.domain_id
        selected_source = value.source
    elif isinstance(value, Mapping):
        schema_version = value.get("schema_version") or DOMAIN_SELECTION_SCHEMA_VERSION
        domain_id = value.get("domain_id")
        selected_source = value.get("source") or source

    if schema_version != DOMAIN_SELECTION_SCHEMA_VERSION:
        raise DomainSelectionError(
            "unsupported domain selection schema: " + str(schema_version)[:96],
            code="unsupported_domain_selection_schema",
        )
    if not isinstance(domain_id, str) or not domain_id.strip():
        raise DomainSelectionError(
            "domain_id is required",
            code="domain_required",
        )
    selected_source = str(selected_source or "").strip().lower()
    if selected_source not in _SELECTION_SOURCES:
        raise DomainSelectionError(
            "unsupported domain selection source: " + selected_source[:64],
            code="invalid_domain_selection_source",
        )
    return DomainSelection(
        domain_id=selected_registry.resolve_id(domain_id),
        source=selected_source,
    )
