"""Canonical plan evidence projection.

The module owns the bounded, domain-neutral explanation of planner context,
workflow selection, plan identity, and plan quality.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from ..capability_catalog import CAPABILITY_CONTEXT_SCHEMA_VERSION
from ..capability_routing import CAPABILITY_DISCOVERY_SCHEMA_VERSION
from ..capability_selection import build_capability_selection_evidence
from ..context_engineering import ContextPacket
from ..domain_contract import DOMAIN_DISCOVERY_SCHEMA_VERSION
from ..evidence_revalidation import build_evidence_binding
from ..models import TaskPlan
from ..plan_identity import build_plan_identity
from ..plan_quality import diagnose_plan, project_plan_quality_evidence
from ..planner_context import project_planner_sections
from ..planner_selection import build_planner_selection_evidence
from ..workflow_selection import normalize_workflow_selection_evidence
from .projection import (
    blueprint_steps_match,
    matched_template_ids,
    planner_source,
    safe_small_mapping,
    unique,
)
from . import projection as _runtime_projection

def build_plan_evidence(
    plan: TaskPlan,
    workflow: Optional[Mapping[str, Any]],
    context_packet: ContextPacket,
    *,
    planner_kind: str,
) -> Dict[str, Any]:
    """Build a bounded, persisted explanation of the planning source."""

    output_type = str((plan.output or {}).get("type") or "unknown")
    tool_names = [step.tool for step in plan.steps]
    source_payload = context_packet.source_payload or context_packet.payload
    sections = (source_payload or {}).get("sections", {})
    if not isinstance(sections, Mapping):
        sections = {}
    templates_section = sections.get("workflow_templates")
    templates_available = (
        isinstance(templates_section, Mapping)
        and not templates_section.get("omitted")
        and isinstance(templates_section.get("templates"), list)
    )
    request_section = sections.get("request")
    if not isinstance(request_section, Mapping):
        request_section = {}
    understanding_section = sections.get("request_understanding")
    understanding_available = (
        isinstance(understanding_section, Mapping)
        and understanding_section.get("schema_version")
        == "spatial-agent.request-understanding-guidance.v1"
        and not understanding_section.get("omitted")
    )
    capability_section = sections.get("capability_discovery")
    capability_available = (
        isinstance(capability_section, Mapping)
        and capability_section.get("schema_version") in {
            CAPABILITY_DISCOVERY_SCHEMA_VERSION,
            DOMAIN_DISCOVERY_SCHEMA_VERSION,
        }
        and not capability_section.get("omitted")
    )
    capability_catalog_section = sections.get("capability_catalog")
    capability_catalog_available = (
        isinstance(capability_catalog_section, Mapping)
        and capability_catalog_section.get("schema_version") == CAPABILITY_CONTEXT_SCHEMA_VERSION
        and not capability_catalog_section.get("omitted")
    )
    evidence: Dict[str, Any] = {
        "available": True,
        "planner_kind": planner_kind,
        "source": planner_source(planner_kind, workflow),
        "output_type": output_type,
        "step_count": len(plan.steps),
        "tool_names": tool_names,
        "unique_tools": unique(tool_names),
        "context_schema_version": context_packet.evidence.get("schema_version"),
        "context_sections": list(context_packet.evidence.get("section_names") or []),
        "template_context_available": templates_available,
        "template_context_truncated": bool(context_packet.evidence.get("truncated")),
        "request_understanding_available": understanding_available,
        "capability_discovery_available": capability_available,
        "capability_catalog_available": capability_catalog_available,
        # Keep the projection shape stable even when a bounded context has
        # omitted the catalog. Consumers can distinguish an empty projection
        # from unavailable catalog evidence via the boolean above.
        "capability_catalog_ids": [],
        "capability_catalog_tool_schema_count": 0,
        "plan_identity": build_plan_identity(
            plan,
            request=str(request_section.get("original") or ""),
            resolved_request=str(request_section.get("resolved") or ""),
            workflow=workflow,
            planner_kind=planner_kind,
        ),
        "evidence_binding": build_evidence_binding(context_packet.payload),
    }
    # Keep the selected domain visible in the generic planning envelope.  The
    # Runtime must not import or interpret domain-specific identifiers; both
    # discovery and the capability catalog already expose this boundary for
    # custom Domain Packs.
    domain_id = None
    if isinstance(capability_section, Mapping):
        domain_id = capability_section.get("domain_id")
    if not domain_id and isinstance(capability_catalog_section, Mapping):
        domain_id = capability_catalog_section.get("domain_id")
    evidence["domain_id"] = str(domain_id)[:80] if domain_id else "unknown"
    request_facts = sections.get("spatial_request")
    if isinstance(request_facts, Mapping):
        evidence["request_facts"] = {
            "schema_version": str(
                request_facts.get("schema_version", "spatial-agent.request-facts.v1")
            )[:80],
            "entities": safe_small_mapping(request_facts.get("entities")),
            "admin_name": str(request_facts.get("admin_name"))[:120]
            if request_facts.get("admin_name")
            else None,
            "tasks": [str(item)[:64] for item in (request_facts.get("tasks") or [])[:16]],
            "datasets": [str(item)[:64] for item in (request_facts.get("datasets") or [])[:16]],
            "constraints": safe_small_mapping(request_facts.get("constraints")),
            "evidence": [str(item)[:64] for item in (request_facts.get("evidence") or [])[:8]],
        }
    if understanding_available and isinstance(understanding_section, Mapping):
        evidence["request_understanding_domain_id"] = str(
            understanding_section.get("domain_id", "unknown")
        )[:80]
        evidence["request_understanding_schema_version"] = str(
            understanding_section.get("schema_version", "")
        )[:96]
    if isinstance(workflow, Mapping):
        evidence["workflow_template_id"] = workflow.get("template_id")
        evidence["workflow_template_version"] = workflow.get("template_version")
        evidence["workflow_constraints"] = safe_small_mapping(workflow.get("constraints"))
        evidence["workflow_evidence"] = list(workflow.get("evidence") or [])
    if capability_available and isinstance(capability_section, Mapping):
        candidate_ids = capability_section.get("candidate_ids")
        signals = capability_section.get("signals")
        evidence["selected_capability_id"] = capability_section.get("selected_capability_id")
        evidence["capability_candidate_ids"] = (
            [str(item) for item in candidate_ids[:8]]
            if isinstance(candidate_ids, list)
            else []
        )
        evidence["capability_candidate_count"] = capability_section.get("candidate_count")
        evidence["capability_signals"] = (
            [str(item) for item in signals[:16]]
            if isinstance(signals, list)
            else []
        )
    # Keep the historical top-level capability projection available when the
    # compact context builder has omitted the verbose discovery section.  The
    # values still come from the domain-neutral workflow-selection contract;
    # this is a compatibility alias, not a second selection implementation.
    selection_section = sections.get("workflow_selection")
    if isinstance(selection_section, Mapping):
        if "selected_capability_id" not in evidence:
            evidence["selected_capability_id"] = selection_section.get(
                "selected_capability_id"
            )
        if "capability_candidate_ids" not in evidence:
            candidate_ids = selection_section.get("candidate_ids")
            evidence["capability_candidate_ids"] = (
                [str(item) for item in candidate_ids[:8]]
                if isinstance(candidate_ids, list)
                else []
            )
        if "capability_candidate_count" not in evidence:
            evidence["capability_candidate_count"] = selection_section.get(
                "candidate_count"
            )
    alignment_selection = dict(selection_section) if isinstance(selection_section, Mapping) else {}
    if isinstance(capability_section, Mapping):
        for key in ("selected_capability_id", "candidate_ids", "candidate_count"):
            if key not in alignment_selection and key in capability_section:
                alignment_selection[key] = capability_section.get(key)
    if (
        not alignment_selection.get("candidate_details")
        and isinstance(capability_catalog_section, Mapping)
        and isinstance(capability_catalog_section.get("capabilities"), list)
    ):
        alignment_selection["candidate_details"] = capability_catalog_section.get("capabilities")
    template_section = sections.get("workflow_templates")
    templates = (
        template_section.get("templates")
        if isinstance(template_section, Mapping)
        else None
    )
    if isinstance(templates, list):
        existing_details = alignment_selection.get("candidate_details")
        existing_details = existing_details if isinstance(existing_details, list) else []
        existing_ids = {
            item.get("id")
            for item in existing_details
            if isinstance(item, Mapping) and item.get("id")
        }
        alignment_selection["candidate_details"] = existing_details + [
            {
                "id": item.get("id"),
                "result_types": item.get("result_types") or [item.get("output_type")],
            }
            for item in templates
            if isinstance(item, Mapping)
            and item.get("id")
            and item.get("id") not in existing_ids
        ]
    evidence["planner_selection"] = build_planner_selection_evidence(
        plan,
        alignment_selection,
        planner_kind=planner_kind,
    )
    evidence["capability_selection"] = build_capability_selection_evidence(
        discovery=capability_section if isinstance(capability_section, Mapping) else None,
        selection=selection_section if isinstance(selection_section, Mapping) else None,
        capability_catalog=(
            capability_catalog_section
            if isinstance(capability_catalog_section, Mapping)
            else None
        ),
        request_facts=request_facts if isinstance(request_facts, Mapping) else None,
        not_applicable=output_type == "direct_answer",
    )
    if capability_catalog_available and isinstance(capability_catalog_section, Mapping):
        catalog_capabilities = capability_catalog_section.get("capabilities")
        tool_schemas = capability_catalog_section.get("tool_schemas")
        evidence["capability_catalog_environment"] = capability_catalog_section.get("environment")
        evidence["capability_catalog_ids"] = (
            [
                str(item.get("id"))
                for item in catalog_capabilities[:8]
                if isinstance(item, Mapping) and item.get("id")
            ]
            if isinstance(catalog_capabilities, list)
            else []
        )
        evidence["capability_catalog_tool_schema_count"] = (
            len(tool_schemas) if isinstance(tool_schemas, Mapping) else 0
        )
        provider = capability_catalog_section.get("tool_provider")
        if isinstance(provider, Mapping):
            evidence["capability_catalog_tool_provider"] = {
                "id": str(provider.get("id", "unknown"))[:64],
                "tool_count": int(provider.get("tool_count", 0) or 0),
            }
        provider_health = capability_catalog_section.get("tool_provider_health")
        if isinstance(provider_health, Mapping):
            evidence["capability_catalog_tool_provider_health"] = {
                "schema_version": str(provider_health.get("schema_version", ""))[:80],
                "provider_id": str(provider_health.get("provider_id", "unknown"))[:64],
                "status": str(provider_health.get("status", "unknown"))[:20],
                "tool_count": int(provider_health.get("tool_count", 0) or 0),
                "reason_code": str(provider_health.get("reason_code"))[:96]
                if provider_health.get("reason_code")
                else None,
            }
            contract = provider_health.get("definition_contract")
            if isinstance(contract, Mapping):
                evidence["capability_catalog_tool_provider_health"]["definition_contract"] = {
                    "schema_version": str(contract.get("schema_version", ""))[:80],
                    "provider_id": str(contract.get("provider_id", "unknown"))[:64],
                    "status": str(contract.get("status", "unknown"))[:20],
                    "tool_count": int(contract.get("tool_count", 0) or 0),
                    "validation": str(contract.get("validation", "unknown"))[:64],
                }
        governance = capability_catalog_section.get("tool_governance")
        if isinstance(governance, Mapping):
            evidence["capability_catalog_tool_governance"] = {
                "schema_version": str(governance.get("schema_version", ""))[:80],
                "provider_id": str(governance.get("provider_id", "unknown"))[:64],
                "tool_count": int(governance.get("tool_count", 0) or 0),
                "returned_tool_count": int(governance.get("returned_tool_count", 0) or 0),
                "requires_approval_count": int(governance.get("requires_approval_count", 0) or 0),
                "side_effect_tool_count": int(governance.get("side_effect_tool_count", 0) or 0),
                "tools": [
                    {
                        "name": str(item.get("name", ""))[:96],
                        "side_effect": str(item.get("side_effect", "unknown"))[:32],
                        "requires_approval": bool(item.get("requires_approval", False)),
                        "permissions": [str(x)[:96] for x in (item.get("permissions") or [])[:8]],
                        "data_dependencies": [str(x)[:96] for x in (item.get("data_dependencies") or [])[:8]],
                        "timeout_seconds": item.get("timeout_seconds"),
                    }
                    for item in (governance.get("tools") or [])[:8]
                    if isinstance(item, Mapping)
                ],
            }
    evidence["workflow_selection"] = normalize_workflow_selection_evidence(
        sections.get("workflow_selection")
    )
    matched, exact = matched_template_ids(
        templates_section if isinstance(templates_section, Mapping) else {},
        output_type=output_type,
        tool_names=tool_names,
        step_count=len(plan.steps),
        steps=[
            {
                "id": step.id,
                "tool": step.tool,
                "depends_on": list(step.depends_on),
                "arg_keys": sorted(step.args.keys()),
            }
            for step in plan.steps
        ],
    )
    evidence["matched_template_ids"] = matched
    evidence["exact_template_ids"] = exact
    evidence["plan_quality"] = project_plan_quality_evidence(
        diagnose_plan(
            plan,
            {"workflow_templates": templates_section}
            if isinstance(templates_section, Mapping)
            else {},
        )
    )
    return evidence


def planner_source(planner_kind: str, workflow: Optional[Mapping[str, Any]]) -> str:
    return _runtime_projection.planner_source(planner_kind, workflow)


def matched_template_ids(
    templates_section: Mapping[str, Any],
    *,
    output_type: str,
    tool_names: list[str],
    step_count: int,
    steps: list[Mapping[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    return _runtime_projection.matched_template_ids(
        templates_section,
        output_type=output_type,
        tool_names=tool_names,
        step_count=step_count,
        steps=steps,
    )


def blueprint_steps_match(
    blueprint_steps: list[Mapping[str, Any]],
    actual_steps: list[Mapping[str, Any]],
) -> bool:
    return _runtime_projection.blueprint_steps_match(blueprint_steps, actual_steps)


def safe_small_mapping(value: Any) -> Dict[str, Any]:
    return _runtime_projection.safe_small_mapping(value)


def unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
