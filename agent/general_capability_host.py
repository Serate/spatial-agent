"""Domain-neutral capability and provider aggregation.

The existing :class:`DomainRuntimeHost` owns isolated application services.
This module owns a different seam: one bounded ToolProvider view over several
registered Domain Packs.  It keeps capability discovery, tool ownership and
provider dispatch together so a future general Runtime does not need to know
which Domain implements a tool.

The Host is deliberately descriptive at its catalog seam and strict at its
execution seam:

* catalogs and result metadata are copied and annotated with their owner;
* duplicate capability, tool or result identities fail closed;
* provider initialization failures retain a degraded Domain record and never
  make unrelated direct answers unavailable;
* tool calls and Domain preflight calls are routed only through an indexed
  owner, with no reflection over arbitrary methods.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any

from .domain_contract import default_permissions
from .domain_registry import DomainRegistry, domain_registry
from .errors import ToolError
from .tool_provider import (
    TOOL_PROVIDER_HEALTH_SCHEMA,
    ToolProviderError,
    UnavailableToolProvider,
    validate_tool_definitions,
)


GENERAL_CAPABILITY_HOST_SCHEMA_VERSION = "spatial-agent.general-capability-host.v1"
GENERAL_CAPABILITY_CATALOG_SCHEMA_VERSION = "spatial-agent.general-capability-catalog.v1"

_HEALTH_STATUSES = frozenset({"ready", "degraded", "unavailable", "unknown"})
_CHECK_STATUSES = frozenset({"passed", "warning", "failed", "unknown"})


class GeneralCapabilityHostError(ValueError):
    """A bounded, machine-readable Host construction or routing error."""

    def __init__(self, message: str, *, code: str):
        self.code = str(code)[:80]
        super().__init__(message)


@dataclass(frozen=True)
class _DomainBinding:
    """Private owner record; Domain Pack and provider objects never leak."""

    domain_id: str
    pack: Any | None
    provider: Any | None
    definitions: Mapping[str, Mapping[str, Any]]
    catalog: Mapping[str, Any]
    permissions: tuple[str, ...]
    provider_id: str
    reason_code: str | None = None


class GeneralCapabilityHost:
    """Aggregate registered Domain capabilities behind a ToolProvider seam.

    Interface:
        ``definitions`` supplies the validated union of provider tools;
        ``invoke`` dispatches one validated tool to its owner;
        ``capability_catalog`` exposes a bounded cross-Domain projection;
        ``preflight_tool`` forwards data policy to the same owner.

    Provider construction is lazy with respect to the Domain Registry import,
    but eager for the selected Host.  This makes conflicts deterministic at
    startup and keeps request execution free of owner discovery races.
    """

    provider_id = "general-capability-host"

    def __init__(
        self,
        *,
        backend_name: str = "memory",
        root: str | Path | None = None,
        registry: DomainRegistry | None = None,
        domain_ids: Iterable[str] | None = None,
        provider_factory: Callable[[str, Any], Any] | None = None,
    ) -> None:
        self._backend_name = str(backend_name or "unknown")[:80]
        self._root = Path(root) if root is not None else None
        self._registry = registry or domain_registry()
        requested = tuple(domain_ids) if domain_ids is not None else self._registry.ids()
        if not requested:
            raise GeneralCapabilityHostError(
                "at least one Domain is required",
                code="domain_required",
            )
        normalized: list[str] = []
        for value in requested:
            selected = self._registry.resolve_id(value)
            if selected not in normalized:
                normalized.append(selected)
        self._domain_ids = tuple(sorted(normalized))
        self._provider_factory = provider_factory
        self._lock = RLock()
        self._bindings = tuple(self._load_binding(domain_id) for domain_id in self._domain_ids)
        self._tool_bindings: dict[str, _DomainBinding] = {}
        self._capability_owners: dict[str, str] = {}
        self._result_type_owners: dict[str, str] = {}
        self._result_type_entries: dict[str, dict[str, Any]] = {}
        self._index_bindings()
        self._context_fingerprint = self._build_context_fingerprint()
        self._result_owners: dict[str, str] = {}

    @property
    def names(self) -> tuple[str, ...]:
        """Return all provider tools, in deterministic order."""

        return tuple(sorted(self._tool_bindings))

    @property
    def domain_ids(self) -> tuple[str, ...]:
        return self._domain_ids

    @property
    def backend_name(self) -> str:
        """Return the selected backend without exposing Host internals."""

        return self._backend_name

    @property
    def context_fingerprint(self) -> str:
        """Return identity based only on stable configuration metadata."""

        return self._context_fingerprint

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        """Return an isolated union of already schema-validated definitions."""

        result: dict[str, dict[str, Any]] = {}
        for binding in self._bindings:
            for name, definition in binding.definitions.items():
                result[name] = deepcopy(dict(definition))
        return result

    def provider_info(self) -> dict[str, Any]:
        """Return safe aggregate provider identity for Runtime context."""

        return {
            "id": self.provider_id,
            "tool_count": len(self.names),
            "domain_count": len(self._domain_ids),
            "context_fingerprint": self.context_fingerprint,
        }

    def owner_for(self, tool: str) -> str | None:
        """Return the registered Domain owner, including degraded providers."""

        binding = self._tool_bindings.get(str(tool or "").strip())
        return binding.domain_id if binding is not None else None

    def domain_pack_for(self, domain_id: str) -> Any | None:
        """Return an internal Domain adapter for a registered Domain id."""

        selected = str(domain_id or "").strip()
        for binding in self._bindings:
            if binding.domain_id == selected:
                return binding.pack
        return None

    def result_owner_for(self, result_type: str) -> str | None:
        """Return the unique owner for an advertised result type."""

        return self._result_type_owners.get(str(result_type or "").strip())

    def owner_map(self) -> dict[str, str]:
        """Return a detached tool-to-Domain map for planner/evidence use."""

        return {
            name: binding.domain_id
            for name, binding in sorted(self._tool_bindings.items())
        }

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch only to the unique owner of one registered tool."""

        tool_name = str(name or "").strip()
        binding = self._tool_bindings.get(tool_name)
        if binding is None:
            raise ToolProviderError(
                "tool owner is not registered: " + tool_name[:96],
                provider_id=self.provider_id,
                code="tool_owner_unresolved",
                retryable=False,
            )
        provider = binding.provider
        if provider is None:
            raise ToolProviderError(
                "tool provider is unavailable for Domain " + binding.domain_id,
                provider_id=binding.provider_id,
                code=binding.reason_code or "provider_unavailable",
                retryable=True,
            )
        try:
            result = provider.invoke(tool_name, dict(arguments))
        except ToolProviderError:
            raise
        except ToolError:
            raise
        except Exception as exc:
            raise ToolProviderError(
                "tool provider execution failed",
                provider_id=binding.provider_id,
                code="provider_execution",
                retryable=False,
            ) from exc
        if not isinstance(result, dict):
            raise ToolProviderError(
                "tool provider returned a non-object result",
                provider_id=binding.provider_id,
                code="provider_result_invalid",
                retryable=False,
            )
        result_ref = result.get("result_ref")
        if isinstance(result_ref, str) and result_ref.strip():
            with self._lock:
                self._result_owners[result_ref[:256]] = binding.domain_id
        return result

    def preflight_tool(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        completed_results: Mapping[str, Mapping[str, Any]],
        *,
        required_datasets: Iterable[str] = (),
        require_dependency_evidence: bool = False,
    ) -> Any:
        """Forward Domain-owned data/evidence preflight for a tool."""

        binding = self._tool_bindings.get(str(tool or "").strip())
        if binding is None or binding.pack is None:
            # Generic tools such as Web search have no Domain preflight.
            return None
        method = getattr(binding.pack, "preflight_tool", None)
        if not callable(method):
            return None
        return method(
            str(tool),
            dict(arguments) if isinstance(arguments, Mapping) else {},
            completed_results if isinstance(completed_results, Mapping) else {},
            required_datasets=tuple(
                str(item) for item in (required_datasets or ()) if str(item)
            ),
            require_dependency_evidence=bool(require_dependency_evidence),
        )

    def health(self) -> dict[str, Any]:
        """Return aggregate health while retaining per-Domain degradation."""

        domains = []
        for binding in self._bindings:
            provider_health = self._provider_health(binding)
            domains.append(
                {
                    "domain_id": binding.domain_id,
                    "provider_id": binding.provider_id,
                    "status": provider_health["status"],
                    "tool_count": len(binding.definitions),
                    "capability_count": len(self._capabilities(binding.catalog)),
                    "reason_code": provider_health.get("reason_code") or binding.reason_code,
                }
            )
        statuses = [str(item["status"]) for item in domains]
        status = _aggregate_status(statuses)
        return {
            "schema_version": TOOL_PROVIDER_HEALTH_SCHEMA,
            "provider_id": self.provider_id,
            "status": status,
            "tool_count": len(self.names),
            "domain_count": len(domains),
            "domains": domains,
            "checks": [
                {
                    "name": "domain_providers",
                    "status": "passed" if status == "ready" else "warning" if status == "degraded" else "failed",
                },
                {
                    "name": "owner_index",
                    "status": "passed" if self._tool_bindings else "warning",
                },
            ],
            "reason_code": (
                None
                if status == "ready"
                else "some_domain_providers_unavailable"
                if status == "degraded"
                else "domain_providers_unavailable"
            ),
        }

    def provider_health(self) -> dict[str, Any]:
        """Alias used by capability surfaces that do not know ToolProvider."""

        return self.health()

    def capability_catalog(self) -> dict[str, Any]:
        """Return a bounded, owner-annotated aggregate capability catalog."""

        capabilities: list[dict[str, Any]] = []
        descriptors: list[dict[str, Any]] = []
        dataset_tools: dict[str, list[str]] = {}
        available_dataset_tools: dict[str, list[str]] = {}
        dataset_groups: dict[str, list[str]] = {}
        workflows: dict[str, dict[str, Any]] = {}
        actions: list[dict[str, Any]] = []
        domains: list[dict[str, Any]] = []
        all_permissions: set[str] = set()

        for binding in self._bindings:
            health = self._provider_health(binding)
            provider_available = health["status"] in {"ready", "degraded"}
            raw_capabilities = self._capabilities(binding.catalog)
            for raw in raw_capabilities:
                item = deepcopy(dict(raw))
                item["owner_domain_id"] = binding.domain_id
                item["provider_id"] = binding.provider_id
                item["provider_status"] = health["status"]
                if not provider_available:
                    item["available"] = False
                    item["availability_mode"] = "unavailable"
                    item["availability_reason"] = "provider_unavailable"
                capabilities.append(item)
            for raw in self._descriptors(binding.catalog):
                item = deepcopy(dict(raw))
                item["owner_domain_id"] = binding.domain_id
                item["provider_id"] = binding.provider_id
                item["provider_status"] = health["status"]
                if not provider_available:
                    # ``capability_descriptors`` cross the public planner
                    # boundary and must retain the versioned descriptor
                    # shape.  In particular, ``availability`` is an object,
                    # not the short status string used by older catalog
                    # projections.  Keep existing metadata while making the
                    # provider degradation explicit and machine-readable.
                    availability = item.get("availability")
                    availability = (
                        dict(availability) if isinstance(availability, Mapping) else {}
                    )
                    availability.update(
                        {
                            "available": False,
                            "mode": "unavailable",
                            "status": health["status"],
                            "reason": "provider_unavailable",
                        }
                    )
                    item["availability"] = availability
                descriptors.append(item)

            all_permissions.update(binding.permissions)
            for dataset, names in _mapping_lists(binding.catalog.get("dataset_tools")):
                key = f"{binding.domain_id}:{dataset}"
                dataset_tools[key] = list(names)
            for dataset, names in _mapping_lists(binding.catalog.get("available_dataset_tools")):
                key = f"{binding.domain_id}:{dataset}"
                available_dataset_tools[key] = list(names) if provider_available else []
            for group, datasets in _mapping_lists(binding.catalog.get("dataset_groups")):
                dataset_groups[f"{binding.domain_id}:{group}"] = list(datasets)
            for workflow_id, raw in _mapping_mappings(binding.catalog.get("workflow_templates")):
                key = f"{binding.domain_id}:{workflow_id}"
                workflow = deepcopy(dict(raw))
                workflow["domain_id"] = binding.domain_id
                workflows[key] = workflow
            raw_actions = binding.catalog.get("actions")
            if isinstance(raw_actions, Mapping):
                for raw in raw_actions.get("actions") or []:
                    if not isinstance(raw, Mapping):
                        continue
                    action = deepcopy(dict(raw))
                    action["domain_id"] = binding.domain_id
                    actions.append(action)
            domains.append(
                {
                    "domain_id": binding.domain_id,
                    "provider_id": binding.provider_id,
                    "provider_health": health,
                    "permissions": list(binding.permissions),
                    "capability_ids": [str(item.get("id")) for item in raw_capabilities if item.get("id")],
                    "tool_names": sorted(
                        name for name, owner in self.owner_map().items() if owner == binding.domain_id
                    ),
                }
            )

        health = self.health()
        return {
            "schema_version": GENERAL_CAPABILITY_CATALOG_SCHEMA_VERSION,
            "host_schema_version": GENERAL_CAPABILITY_HOST_SCHEMA_VERSION,
            "domain_id": "general",
            "domain_ids": list(self._domain_ids),
            "environment": self._backend_name,
            "version": "1.0",
            "context_fingerprint": self.context_fingerprint,
            "health_status": health["status"],
            "provider_health": health,
            "domains": domains,
            "permissions": sorted(all_permissions),
            "capabilities": capabilities,
            "capability_descriptors": descriptors,
            "capability_descriptor_count": len(descriptors),
            "dataset_tools": dataset_tools,
            "available_dataset_tools": available_dataset_tools,
            "dataset_groups": dataset_groups,
            "workflow_templates": workflows,
            "actions": {
                "schema_version": "spatial-agent.actions.v1",
                "domain_id": "general",
                "actions": actions[:128],
            },
            "tool_owners": self.owner_map(),
            "result_type_owners": dict(sorted(self._result_type_owners.items())),
            "result_types": [
                deepcopy(self._result_type_entries[key])
                for key in sorted(self._result_type_entries)
            ],
        }

    def export_result(self, result_ref: str, max_features: int = 100) -> dict[str, Any]:
        """Route a previously returned result reference to its owner."""

        ref = str(result_ref or "").strip()
        owner = self._result_owners.get(ref)
        candidates = [
            binding
            for binding in self._bindings
            if callable(getattr(binding.provider, "export_result", None))
        ]
        if owner:
            candidates = [item for item in candidates if item.domain_id == owner]
        elif len(candidates) != 1:
            raise ToolProviderError(
                "result owner cannot be resolved",
                provider_id=self.provider_id,
                code="result_owner_unresolved",
                retryable=False,
            )
        if not candidates:
            raise ToolProviderError(
                "result export is unavailable",
                provider_id=self.provider_id,
                code="result_export_unavailable",
                retryable=True,
            )
        return candidates[0].provider.export_result(ref, max_features=max_features)

    def _load_binding(self, domain_id: str) -> _DomainBinding:
        pack = None
        catalog: Mapping[str, Any] = {}
        reason_code: str | None = None
        try:
            pack = self._registry.resolve(domain_id)
        except Exception:
            reason_code = "domain_initialization_unavailable"

        if pack is not None:
            try:
                value = pack.capability_catalog(environment=self._backend_name)
                catalog = deepcopy(dict(value)) if isinstance(value, Mapping) else {}
            except Exception:
                catalog = {}
                reason_code = reason_code or "capability_catalog_unavailable"

        provider_id = self._provider_id_from_pack(
            pack,
            domain_id,
            backend_name=self._backend_name,
            root=self._root,
        )
        provider = None
        definitions: Mapping[str, Mapping[str, Any]] = {}
        if pack is not None:
            try:
                provider = (
                    self._provider_factory(domain_id, pack)
                    if self._provider_factory is not None
                    else pack.tool_provider(backend_name=self._backend_name, root=self._root)
                )
                raw_definitions = provider.definitions()
                definitions = validate_tool_definitions(raw_definitions)
                provider_id = str(getattr(provider, "provider_id", provider_id) or provider_id)[:96]
            except Exception:
                provider = UnavailableToolProvider(
                    {},
                    provider_id=provider_id,
                    reason_code="provider_initialization_unavailable",
                    message="Domain tool provider is unavailable",
                )
                definitions = {}
                reason_code = reason_code or "provider_initialization_unavailable"
        return _DomainBinding(
            domain_id=domain_id,
            pack=pack,
            provider=provider,
            definitions=definitions,
            catalog=catalog,
            permissions=tuple(sorted(default_permissions(pack))) if pack is not None else (),
            provider_id=provider_id,
            reason_code=reason_code,
        )

    def _index_bindings(self) -> None:
        for binding in self._bindings:
            for name in binding.definitions:
                self._claim(self._tool_bindings, name, binding, "tool_name_conflict")
            for item in self._capabilities(binding.catalog):
                capability_id = str(item.get("id") or "").strip()
                if capability_id:
                    self._claim(self._capability_owners, capability_id, binding.domain_id, "capability_id_conflict")
                for name in item.get("tools") or []:
                    tool_name = str(name or "").strip()
                    if tool_name:
                        self._claim(self._tool_bindings, tool_name, binding, "tool_name_conflict")
            for name, entry in self._result_entries(binding):
                self._claim(self._result_type_owners, name, binding.domain_id, "result_type_conflict")
                self._result_type_entries[name] = entry

    def _claim(self, index: dict[str, Any], key: str, owner: Any, code: str) -> None:
        previous = index.get(key)
        previous_owner = (
            previous.domain_id if isinstance(previous, _DomainBinding) else previous
        )
        current_owner = owner.domain_id if isinstance(owner, _DomainBinding) else owner
        if previous_owner is not None and previous_owner != current_owner:
            raise GeneralCapabilityHostError(
                "conflicting registered identity: " + str(key)[:96],
                code=code,
            )
        index[key] = owner

    def _provider_health(self, binding: _DomainBinding) -> dict[str, Any]:
        if binding.provider is None:
            return {
                "schema_version": TOOL_PROVIDER_HEALTH_SCHEMA,
                "provider_id": binding.provider_id,
                "status": "unavailable",
                "tool_count": len(binding.definitions),
                "checks": [{"name": "provider", "status": "failed"}],
                "reason_code": binding.reason_code or "provider_unavailable",
            }
        checker = getattr(binding.provider, "health", None)
        try:
            raw = checker() if callable(checker) else {}
        except Exception:
            raw = {}
        raw = raw if isinstance(raw, Mapping) else {}
        status = str(raw.get("status") or "unknown").lower()
        if status not in _HEALTH_STATUSES:
            status = "unknown"
        checks = []
        for item in raw.get("checks") or []:
            if not isinstance(item, Mapping):
                continue
            check_status = str(item.get("status") or "unknown").lower()
            checks.append(
                {
                    "name": str(item.get("name") or "check")[:64],
                    "status": check_status if check_status in _CHECK_STATUSES else "unknown",
                }
            )
        if not checks:
            checks = [{"name": "provider", "status": "passed" if status == "ready" else "warning"}]
        result = {
            "schema_version": TOOL_PROVIDER_HEALTH_SCHEMA,
            "provider_id": binding.provider_id,
            "status": status,
            "tool_count": len(binding.definitions),
            "checks": checks[:12],
            "reason_code": str(raw.get("reason_code") or binding.reason_code)[:96]
            if raw.get("reason_code") or binding.reason_code
            else None,
        }
        data_readiness = raw.get("data_readiness")
        if data_readiness is not None:
            result["data_readiness"] = str(data_readiness)[:32]
        return result

    @staticmethod
    def _provider_id_from_pack(
        pack: Any,
        domain_id: str,
        *,
        backend_name: str,
        root: Path | None,
    ) -> str:
        method = getattr(pack, "tool_provider_info", None) if pack is not None else None
        if callable(method):
            try:
                value = method(backend_name=backend_name, root=root)
                if isinstance(value, Mapping) and value.get("id"):
                    return str(value["id"])[:96]
            except Exception:
                pass
        return "domain-" + str(domain_id)[:64]

    @staticmethod
    def _capabilities(catalog: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        value = catalog.get("capabilities") if isinstance(catalog, Mapping) else []
        return [item for item in value or [] if isinstance(item, Mapping)]

    @staticmethod
    def _descriptors(catalog: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        value = catalog.get("capability_descriptors") if isinstance(catalog, Mapping) else []
        return [item for item in value or [] if isinstance(item, Mapping)]

    @staticmethod
    def _result_entries(binding: _DomainBinding) -> list[tuple[str, dict[str, Any]]]:
        if binding.pack is None:
            return []
        method = getattr(binding.pack, "result_registry", None)
        if not callable(method):
            return []
        try:
            registry = method()
            context = registry.as_context() if callable(getattr(registry, "as_context", None)) else {}
        except Exception:
            return []
        values = context.get("result_types") if isinstance(context, Mapping) else []
        # A few legacy Domain registries retain compatibility-only result
        # entries that are not referenced by any advertised capability or
        # provider output.  They are not part of this Host's public result
        # plane; including them would create a false collision between
        # otherwise independent Domain Packs.  Actual declarations remain
        # strict and are still checked by ``_index_bindings``.
        referenced = _referenced_result_types(binding)
        result = []
        for raw in values or []:
            if not isinstance(raw, Mapping):
                continue
            name = str(raw.get("type") or "").strip()
            if not name:
                continue
            if referenced and name not in referenced:
                continue
            entry = deepcopy(dict(raw))
            entry["owner_domain_id"] = binding.domain_id
            entry["provider_id"] = binding.provider_id
            result.append((name, entry))
        return result

    def _build_context_fingerprint(self) -> str:
        payload = {
            "schema_version": GENERAL_CAPABILITY_HOST_SCHEMA_VERSION,
            "backend": self._backend_name,
            "domains": [
                {
                    "domain_id": binding.domain_id,
                    "provider_id": binding.provider_id,
                    "permissions": list(binding.permissions),
                    "tools": sorted(binding.definitions),
                    "capabilities": sorted(
                        str(item.get("id"))
                        for item in self._capabilities(binding.catalog)
                        if item.get("id")
                    ),
                    "result_types": sorted(name for name, _ in self._result_entries(binding)),
                }
                for binding in self._bindings
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _aggregate_status(statuses: Iterable[str]) -> str:
    values = list(statuses)
    if not values or all(value == "unavailable" for value in values):
        return "unavailable"
    if all(value == "ready" for value in values):
        return "ready"
    return "degraded"


def _referenced_result_types(binding: _DomainBinding) -> set[str]:
    """Collect result ids that are part of the advertised execution plane."""

    referenced: set[str] = set()
    for capability in GeneralCapabilityHost._capabilities(binding.catalog):
        referenced.update(
            str(item).strip()
            for item in (capability.get("result_types") or [])
            if str(item).strip()
        )
    templates = binding.catalog.get("workflow_templates")
    if isinstance(templates, Mapping):
        for template in templates.values():
            if not isinstance(template, Mapping):
                continue
            referenced.update(
                str(item).strip()
                for item in (template.get("result_types") or [])
                if str(item).strip()
            )
    for definition in binding.definitions.values():
        schema = definition.get("output_schema") if isinstance(definition, Mapping) else None
        if not isinstance(schema, Mapping):
            continue
        declared = schema.get("result_type")
        if isinstance(declared, str) and declared.strip():
            referenced.add(declared.strip())
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            value = properties.get("result_type")
            if isinstance(value, Mapping) and value.get("const"):
                referenced.add(str(value["const"]).strip())
    return referenced


def _mapping_lists(value: Any) -> list[tuple[str, list[str]]]:
    if not isinstance(value, Mapping):
        return []
    result = []
    for key, raw in value.items():
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple, set)):
            continue
        result.append(
            (
                str(key)[:96],
                [str(item)[:96] for item in raw if str(item).strip()][:64],
            )
        )
    return result


def _mapping_mappings(value: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(value, Mapping):
        return []
    return [
        (str(key)[:96], raw)
        for key, raw in value.items()
        if isinstance(raw, Mapping)
    ]


__all__ = [
    "GENERAL_CAPABILITY_CATALOG_SCHEMA_VERSION",
    "GENERAL_CAPABILITY_HOST_SCHEMA_VERSION",
    "GeneralCapabilityHost",
    "GeneralCapabilityHostError",
]
