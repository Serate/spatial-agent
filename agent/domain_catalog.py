"""Domain-neutral validation and construction for declarative Domain catalogs.

Domain Packs own the declarations passed to this module.  The helper only
checks their public shape and builds the existing capability catalog; it does
not select a domain, execute a tool, or encode business policy.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Mapping

from .analysis_intent import SUPPORTED_ANALYSIS_OPERATIONS
from .capability_catalog import capability_catalog


DOMAIN_CATALOG_SCHEMA_VERSION = "spatial-agent.domain-catalog-spec.v1"
_DOMAIN_ID = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class DomainCatalogSpec:
    """The bounded declarations needed to expose one Domain catalog."""

    domain_id: str
    capabilities: tuple[Mapping[str, Any], ...]
    dataset_tool_capabilities: Mapping[str, Iterable[str]]
    dataset_groups: Mapping[str, Iterable[str]]
    workflow_templates: Mapping[str, Mapping[str, Any]]
    known_tool_names: tuple[str, ...]
    known_result_types: tuple[str, ...]
    analysis_ready_capability_ids: tuple[str, ...] = field(default_factory=tuple)
    derived_datasets: tuple[str, ...] = field(default_factory=tuple)


def build_domain_catalog(
    spec: DomainCatalogSpec,
    *,
    environment: str = "unknown",
    actions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a Domain declaration and build the shared catalog contract."""

    validate_domain_catalog_spec(spec)
    catalog = capability_catalog(
        environment=environment,
        domain_id=spec.domain_id,
        capability_definitions=deepcopy(spec.capabilities),
        dataset_tool_capabilities=deepcopy(spec.dataset_tool_capabilities),
        dataset_groups=deepcopy(spec.dataset_groups),
        analysis_ready_capability_ids=spec.analysis_ready_capability_ids,
        workflow_templates=deepcopy(spec.workflow_templates),
        actions=deepcopy(actions) if isinstance(actions, Mapping) else None,
    )
    catalog["declaration_schema_version"] = DOMAIN_CATALOG_SCHEMA_VERSION
    catalog["derived_datasets"] = list(spec.derived_datasets)
    for item in catalog.get("capabilities", []):
        if isinstance(item, Mapping):
            item["derived_datasets"] = [
                name
                for name in item.get("datasets", [])
                if name in spec.derived_datasets
            ]
    return catalog


def workflow_catalog(spec: DomainCatalogSpec) -> dict[str, dict[str, Any]]:
    """Return an isolated copy of the validated Domain workflow declarations."""

    validate_domain_catalog_spec(spec)
    return deepcopy(dict(spec.workflow_templates))


def validate_domain_catalog_spec(spec: DomainCatalogSpec) -> None:
    """Reject cross-reference errors before a catalog reaches a Planner."""

    if not isinstance(spec, DomainCatalogSpec):
        raise TypeError("domain catalog must be a DomainCatalogSpec")
    domain_id = str(spec.domain_id or "")
    if not _DOMAIN_ID.fullmatch(domain_id):
        raise ValueError("domain_id must be a lowercase bounded identifier")

    known_tools = _unique_strings(spec.known_tool_names, "known_tool_names")
    known_results = _unique_strings(spec.known_result_types, "known_result_types")
    datasets = {
        str(name): _unique_strings(values, f"dataset_tool_capabilities.{name}")
        for name, values in (spec.dataset_tool_capabilities or {}).items()
    }
    if not datasets:
        raise ValueError("dataset_tool_capabilities must not be empty")
    derived_datasets = _unique_strings(spec.derived_datasets, "derived_datasets")
    overlap = sorted(set(derived_datasets) & set(datasets))
    if overlap:
        raise ValueError(
            "derived_datasets overlaps physical datasets: " + ", ".join(overlap)
        )
    for name, tools in datasets.items():
        unknown = sorted(set(tools) - set(known_tools))
        if unknown:
            raise ValueError(
                f"dataset {name} references unknown tools: {', '.join(unknown)}"
            )

    groups = spec.dataset_groups or {}
    for group, values in groups.items():
        for dataset in _unique_strings(values, f"dataset_groups.{group}"):
            if dataset not in datasets:
                raise ValueError(f"dataset group references unknown dataset: {dataset}")

    capabilities = list(spec.capabilities or ())
    capability_ids = _unique_strings(
        [item.get("id") for item in capabilities if isinstance(item, Mapping)],
        "capabilities",
    )
    if len(capability_ids) != len(capabilities):
        raise ValueError("capabilities must be non-empty objects with unique ids")
    for item in capabilities:
        if not isinstance(item, Mapping):
            raise ValueError("capability declaration must be an object")
        capability_id = str(item.get("id") or "")
        declared_datasets = _unique_strings(
            item.get("datasets") or (), f"capability {capability_id}.datasets"
        )
        unknown_datasets = sorted(
            set(declared_datasets) - set(datasets) - set(derived_datasets)
        )
        if unknown_datasets:
            raise ValueError(
                f"capability {capability_id} references unknown datasets: "
                + ", ".join(unknown_datasets)
            )
        declared_tools = _unique_strings(
            item.get("tools") or (), f"capability {capability_id}.tools"
        )
        unknown_tools = sorted(set(declared_tools) - set(known_tools))
        if unknown_tools:
            raise ValueError(
                f"capability {capability_id} references unknown tools: "
                + ", ".join(unknown_tools)
            )
        declared_results = _unique_strings(
            item.get("result_types") or (), f"capability {capability_id}.result_types"
        )
        unknown_results = sorted(set(declared_results) - set(known_results))
        if unknown_results:
            raise ValueError(
                f"capability {capability_id} references unknown result types: "
                + ", ".join(unknown_results)
            )
        declared_operations = _unique_strings(
            item.get("analysis_operations") or (),
            f"capability {capability_id}.analysis_operations",
        )
        unknown_operations = sorted(
            set(declared_operations) - set(SUPPORTED_ANALYSIS_OPERATIONS)
        )
        if unknown_operations:
            raise ValueError(
                f"capability {capability_id} references unknown analysis operations: "
                + ", ".join(unknown_operations)
            )
        explicit_workflows = _unique_strings(
            item.get("workflow_ids") or item.get("workflow_id") or (),
            f"capability {capability_id}.workflow_ids",
        )
        unknown_workflows = sorted(set(explicit_workflows) - set(spec.workflow_templates or {}))
        if unknown_workflows:
            raise ValueError(
                f"capability {capability_id} references unknown workflows: "
                + ", ".join(unknown_workflows)
            )

    workflow_ids = set()
    for key, template in (spec.workflow_templates or {}).items():
        if not isinstance(template, Mapping):
            raise ValueError(f"workflow template {key} must be an object")
        template_id = str(template.get("id") or key)
        if template_id != str(key):
            raise ValueError(f"workflow template key/id mismatch: {key}")
        if template_id in workflow_ids:
            raise ValueError(f"duplicate workflow template: {template_id}")
        workflow_ids.add(template_id)
        allowed = _unique_strings(
            template.get("allowed_tools") or (), f"workflow {template_id}.allowed_tools"
        )
        unknown_allowed = sorted(set(allowed) - set(known_tools))
        if unknown_allowed:
            raise ValueError(
                f"workflow {template_id} references unknown tools: "
                + ", ".join(unknown_allowed)
            )
        results = _unique_strings(
            template.get("result_types") or (), f"workflow {template_id}.result_types"
        )
        unknown_workflow_results = sorted(set(results) - set(known_results))
        if unknown_workflow_results:
            raise ValueError(
                f"workflow {template_id} references unknown result types: "
                + ", ".join(unknown_workflow_results)
            )
        for step in template.get("step_blueprint") or ():
            if isinstance(step, Mapping) and str(step.get("tool") or "") not in allowed:
                raise ValueError(
                    f"workflow {template_id} step uses a tool outside allowed_tools"
                )

    unknown_ready = set(spec.analysis_ready_capability_ids or ()) - set(capability_ids)
    if unknown_ready:
        raise ValueError(
            "analysis_ready_capability_ids references unknown capability: "
            + ", ".join(sorted(str(value) for value in unknown_ready))
        )


def _unique_strings(values: Iterable[Any], label: str) -> list[str]:
    if isinstance(values, str):
        values = (values,)
    result = []
    for value in values or ():
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{label} contains an empty value")
        if text in result:
            raise ValueError(f"{label} contains a duplicate value: {text}")
        result.append(text)
    if not result and label in {"known_tool_names", "known_result_types", "capabilities"}:
        raise ValueError(f"{label} must not be empty")
    return result
