"""Contracts for domain packs consumed by the generic Agent Runtime.

The runtime only needs a bounded capability catalog and discovery projection.
GIS is the default domain pack, but neither the orchestration loop nor the
planner context builder should need to know GIS dataset names.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


DOMAIN_DISCOVERY_SCHEMA_VERSION = "spatial-agent.domain-discovery.v1"


class DomainPack(Protocol):
    """A domain adapter for capability discovery and catalog projection."""

    domain_id: str

    def answer_composer(self) -> Any:
        """Return the domain-owned answer composer."""

    def default_permissions(self) -> Any:
        """Return the default permission grant for this domain's tools."""

    def result_registry(self) -> Any:
        """Return result titles and workspace metadata for this domain."""

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        """Return optional domain-specific runtime/data evidence."""

    def extract_request_facts(self, request: str) -> Any:
        """Return the domain-neutral request facts for a request."""

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        """Return a JSON-safe capability catalog for the runtime context."""

    def discover(self, request: str, request_facts: Any) -> Any:
        """Return a mapping or object exposing ``as_context_dict``."""

    def workflow_template_context(
        self,
        *,
        include_arg_shape: bool = False,
        compact: bool = True,
    ) -> Mapping[str, Any]:
        """Return the domain-owned planner workflow context."""


def discovery_context(discovery: Any) -> dict[str, Any]:
    """Normalize a domain discovery result without imposing GIS types."""
    as_context = getattr(discovery, "as_context_dict", None)
    value = as_context() if callable(as_context) else discovery
    if not isinstance(value, Mapping):
        raise TypeError("domain discovery must be a mapping or expose as_context_dict()")
    return dict(value)


def selected_capability_ids(discovery: Any) -> list[str]:
    """Read selected candidates from either a generic mapping or legacy router."""
    context = discovery_context(discovery)
    selected = context.get("selected_capability_id")
    candidates = context.get("candidate_ids")
    values = [selected] if selected else []
    if isinstance(candidates, list):
        values.extend(candidates)
    result: list[str] = []
    for value in values:
        if value and str(value) not in result:
            result.append(str(value))
    return result[:8]


def workflow_context(domain_pack: DomainPack) -> dict[str, Any]:
    """Read workflow context through the domain seam without GIS fallback."""
    method = getattr(domain_pack, "workflow_template_context", None)
    if not callable(method):
        return {}
    value = method(include_arg_shape=False, compact=True)
    return dict(value) if isinstance(value, Mapping) else {}


def extract_request_facts(domain_pack: DomainPack, request: str) -> Any:
    """Use domain-owned request extraction, with the GIS compatibility fallback."""
    method = getattr(domain_pack, "extract_request_facts", None)
    if callable(method):
        return method(request)
    from .request_model import parse_spatial_request

    return parse_spatial_request(request)


def answer_composer(domain_pack: DomainPack) -> Any:
    """Resolve a domain-owned answer composer with GIS compatibility fallback."""
    factory = getattr(domain_pack, "answer_composer", None)
    if callable(factory):
        composer = factory()
        if composer is not None:
            return composer
    from .answer_composer import AnswerComposer

    return AnswerComposer()


def default_permissions(domain_pack: DomainPack) -> set[str]:
    """Resolve the default read grant owned by the selected domain pack."""
    factory = getattr(domain_pack, "default_permissions", None)
    if callable(factory):
        values = factory()
        if values is not None:
            permissions = {str(item) for item in values if str(item)}
            if permissions:
                return permissions
    return {"spatial_data:read"}


def result_registry(domain_pack: DomainPack) -> Any:
    """Resolve result metadata owned by a domain pack."""
    factory = getattr(domain_pack, "result_registry", None)
    if callable(factory):
        registry = factory()
        if registry is not None:
            return registry
    from .result_registry import default_result_registry

    return default_result_registry()


def runtime_evidence(domain_pack: DomainPack, *, max_files: int = 10) -> dict[str, Any]:
    """Read optional bounded runtime evidence without imposing a data model."""
    method = getattr(domain_pack, "runtime_evidence", None)
    if not callable(method):
        return {}
    value = method(max_files=max_files)
    return dict(value) if isinstance(value, Mapping) else {}


def default_domain_pack() -> DomainPack:
    """Load the GIS pack lazily for backwards-compatible default behavior."""
    from domains.gis import GIS_DOMAIN_PACK

    return GIS_DOMAIN_PACK
