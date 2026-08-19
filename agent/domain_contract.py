"""Contracts for domain packs consumed by the generic Agent Runtime.

The runtime only needs a bounded capability catalog and discovery projection.
GIS is the default domain pack, but neither the orchestration loop nor the
planner context builder should need to know GIS dataset names.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol


DOMAIN_DISCOVERY_SCHEMA_VERSION = "spatial-agent.domain-discovery.v1"
DOMAIN_ACTION_SCHEMA_VERSION = "spatial-agent.actions.v1"


@dataclass(frozen=True)
class DomainActionSpec:
    """A bounded, discoverable action owned by a Domain Pack.

    The metadata is descriptive only. Execution still requires the selected
    Domain Pack to explicitly implement the action and is never dispatched by
    reflecting over arbitrary Service methods.
    """

    action_id: str
    label: str
    description: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    result_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        schema = self.input_schema if isinstance(self.input_schema, Mapping) else {}
        properties = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
        safe_properties = {}
        for name, definition in list(properties.items())[:24]:
            if not isinstance(definition, Mapping):
                continue
            safe_properties[str(name)[:64]] = {
                key: deepcopy(definition[key])
                for key in (
                    "type",
                    "title",
                    "description",
                    "minimum",
                    "maximum",
                    "minLength",
                    "maxLength",
                    "minItems",
                    "maxItems",
                    "items",
                    "enum",
                )
                if key in definition
            }
        safe_schema = {
            "type": str(schema.get("type") or "object")[:24],
            "required": [str(item)[:64] for item in (schema.get("required") or [])[:24]],
            "properties": safe_properties,
            "additionalProperties": bool(schema.get("additionalProperties", False)),
        }
        return {
            "id": str(self.action_id)[:96],
            "label": str(self.label)[:120],
            "description": str(self.description)[:320],
            "input_schema": safe_schema,
            "result_type": str(self.result_type)[:96] if self.result_type else None,
        }


class DomainPack(Protocol):
    """A domain adapter for capability discovery and catalog projection."""

    domain_id: str

    def action_specs(self) -> Any:
        """Return discoverable, domain-owned action specifications."""

    def execute_action(self, action_id: str, payload: Mapping[str, Any], *, context: Any = None) -> Any:
        """Execute one declared action through an explicit domain adapter."""

    def answer_composer(self) -> Any:
        """Return the domain-owned answer composer."""

    def default_permissions(self) -> Any:
        """Return the default permission grant for this domain's tools."""

    def preflight_tool(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        completed_results: Mapping[str, Mapping[str, Any]],
        *,
        required_datasets: Iterable[str] = (),
        require_dependency_evidence: bool = False,
    ) -> Any:
        """Apply optional domain-owned data/evidence preflight policy."""

    def result_registry(self) -> Any:
        """Return result titles and workspace metadata for this domain."""

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        """Return optional domain-specific runtime/data evidence."""

    def release_evidence(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Return optional domain-owned release/data publication evidence."""

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


def domain_action_catalog(domain_pack: DomainPack) -> dict[str, Any]:
    """Normalize a bounded action list without imposing domain semantics."""
    method = getattr(domain_pack, "action_specs", None)
    raw = method() if callable(method) else []
    items = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if isinstance(item, DomainActionSpec):
            items.append(item.as_dict())
        elif isinstance(item, Mapping) and item.get("id"):
            items.append(
                DomainActionSpec(
                    action_id=str(item.get("id")),
                    label=str(item.get("label") or item.get("id")),
                    description=str(item.get("description") or ""),
                    input_schema=item.get("input_schema") if isinstance(item.get("input_schema"), Mapping) else {},
                    result_type=str(item.get("result_type")) if item.get("result_type") else None,
                ).as_dict()
            )
    return {
        "schema_version": DOMAIN_ACTION_SCHEMA_VERSION,
        "domain_id": str(getattr(domain_pack, "domain_id", "unknown"))[:80],
        "actions": items[:32],
    }


def execute_domain_action(
    domain_pack: DomainPack,
    action_id: str,
    payload: Mapping[str, Any],
    *,
    context: Any = None,
) -> Any:
    """Execute only an action declared by the selected Domain Pack."""
    action_id = str(action_id or "").strip()
    declared = {item.get("id") for item in domain_action_catalog(domain_pack).get("actions", [])}
    if action_id not in declared:
        from .action_contract import ActionContractError

        raise ActionContractError(
            "unknown domain action: " + action_id,
            action_id=action_id,
            code="action_not_declared",
        )
    method = getattr(domain_pack, "execute_action", None)
    if not callable(method):
        from .action_contract import ActionContractError

        raise ActionContractError(
            "domain action execution is unavailable",
            action_id=action_id,
            code="action_execution_unavailable",
        )
    if not isinstance(payload, Mapping):
        raise ValueError("action payload must be an object")
    raw_specs = getattr(domain_pack, "action_specs", lambda: ())()
    selected = None
    for item in raw_specs if isinstance(raw_specs, (list, tuple)) else ():
        if isinstance(item, DomainActionSpec) and item.action_id == action_id:
            selected = item
            break
        if isinstance(item, Mapping) and str(item.get("id") or "") == action_id:
            selected = DomainActionSpec(
                action_id=action_id,
                label=str(item.get("label") or action_id),
                description=str(item.get("description") or ""),
                input_schema=item.get("input_schema") if isinstance(item.get("input_schema"), Mapping) else {},
                result_type=str(item.get("result_type")) if item.get("result_type") else None,
            )
            break
    if selected is not None and selected.input_schema:
        from .action_contract import ActionContractError, validate_action_payload

        try:
            validate_action_payload(dict(payload), selected.input_schema)
        except ValueError as exc:
            raise ActionContractError(str(exc), action_id=action_id) from exc
    return method(action_id, dict(payload), context=context)


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


def preflight_tool(
    domain_pack: DomainPack,
    tool: str,
    arguments: Mapping[str, Any],
    completed_results: Mapping[str, Mapping[str, Any]],
    *,
    required_datasets: Iterable[str] = (),
    require_dependency_evidence: bool = False,
) -> None:
    """Delegate data/evidence policy without making Runtime know a domain."""
    method = getattr(domain_pack, "preflight_tool", None)
    if not callable(method):
        return
    method(
        str(tool),
        dict(arguments),
        completed_results,
        required_datasets=tuple(str(item) for item in required_datasets if str(item)),
        require_dependency_evidence=bool(require_dependency_evidence),
    )


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


def release_evidence(
    domain_pack: DomainPack,
    *,
    config_path: str | None = None,
    max_files: int = 10,
) -> dict[str, Any]:
    """Read release evidence through the selected Domain Pack seam.

    The generic Runtime deliberately has no fallback to a GIS provider. An
    older Domain Pack that has not implemented this optional seam receives a
    bounded ``not_evaluated`` response instead of inheriting another domain's
    data policy.
    """
    method = getattr(domain_pack, "release_evidence", None)
    if not callable(method):
        return {
            "report_version": 1,
            "domain_id": str(getattr(domain_pack, "domain_id", "unknown"))[:80],
            "status": "not_evaluated",
            "data_readiness": "not_evaluated",
            "metadata": {"status": "not_evaluated"},
            "source_binding": {"status": "not_evaluated"},
            "output_manifest": {"status": "not_evaluated"},
            "manifest": {"status": "not_evaluated"},
        }
    value = method(config_path=config_path, max_files=max_files)
    return dict(value) if isinstance(value, Mapping) else {}


def default_domain_pack() -> DomainPack:
    """Load the GIS pack lazily for backwards-compatible default behavior."""
    from domains.gis import GIS_DOMAIN_PACK

    return GIS_DOMAIN_PACK
