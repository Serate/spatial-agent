"""Domain-neutral completeness checks for Composite planning.

This seam distinguishes a structurally parseable planner response from a
plan that can actually be materialized through a registered Domain workflow
and the canonical TaskPlan gate.  It only consumes bounded public projections;
it never selects tools or executes a run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PLAN_COMPLETENESS_SCHEMA_VERSION = "spatial-agent.plan-completeness.v1"
EXECUTION_READINESS_SCHEMA_VERSION = "spatial-agent.execution-readiness.v1"
_MAX_ITEMS = 64
_MAX_COMPONENTS = 8


class PlanCompletenessError(ValueError):
    """A Composite plan is not complete enough to create an execution run."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def assess_catalog_consistency(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded capability-to-workflow consistency receipt.

    Older Domain catalogs may contain answer-only or legacy capabilities that
    do not yet have a workflow.  They remain visible for discovery, but are
    marked ``unbound`` so a selected component cannot silently become an
    executable plan.  A capability is executable when at least one workflow
    is explicitly/equivalently bound and its tools/results are subsets of the
    capability declaration.
    """

    domains = catalog.get("domains") if isinstance(catalog, Mapping) else []
    bindings: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for domain in list(domains or [])[:_MAX_ITEMS]:
        if not isinstance(domain, Mapping):
            continue
        domain_id = _text(domain.get("domain_id"), 64)
        workflows = [
            item
            for item in (domain.get("workflows") or [])
            if isinstance(item, Mapping)
        ]
        for capability in list(domain.get("capabilities") or [])[:_MAX_ITEMS]:
            if not isinstance(capability, Mapping):
                continue
            capability_id = _text(capability.get("id"), 96)
            if not domain_id or not capability_id:
                continue
            tools = _strings(capability.get("tools"))
            results = _strings(capability.get("result_types"))
            explicit = _strings(
                capability.get("workflow_ids") or capability.get("workflow_id")
            )
            compatible = [
                workflow
                for workflow in workflows
                if _workflow_matches(
                    workflow,
                    capability_id=capability_id,
                    explicit_ids=explicit,
                    tools=tools,
                    results=results,
                )
            ]
            workflow_ids = [
                _text(item.get("id"), 96)
                for item in compatible
                if _text(item.get("id"), 96)
            ]
            if not tools and (not results or "direct_answer" in results):
                mode = "answer_only"
                reason_code = "answer_only_capability"
            elif workflow_ids:
                mode = "task_plan"
                reason_code = "workflow_bound"
            else:
                mode = "unbound"
                reason_code = "workflow_not_registered"
                violations.append(
                    {
                        "domain_id": domain_id,
                        "capability_id": capability_id,
                        "reason_code": reason_code,
                    }
                )
            execution = _capability_execution_readiness(
                domain,
                compatible,
                workflow_ids=workflow_ids,
                mode=mode,
            )
            bindings.append(
                {
                    "domain_id": domain_id,
                    "capability_id": capability_id,
                    "workflow_ids": workflow_ids[:8],
                    "plan_mode": mode,
                    "reason_code": reason_code,
                    **execution,
                }
            )

    return {
        "schema_version": PLAN_COMPLETENESS_SCHEMA_VERSION,
        "status": "valid" if not violations else "degraded",
        "capability_count": len(bindings),
        "bound_count": sum(item["plan_mode"] == "task_plan" for item in bindings),
        "unbound_count": sum(item["plan_mode"] == "unbound" for item in bindings),
        "answer_only_count": sum(
            item["plan_mode"] == "answer_only" for item in bindings
        ),
        "bindings": bindings[:_MAX_ITEMS],
        "violations": violations[:_MAX_ITEMS],
    }


def annotate_catalog_capabilities(
    domains: Sequence[Mapping[str, Any]], receipt: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Attach only bounded binding metadata to projected capability entries."""

    index = {
        (str(item.get("domain_id")), str(item.get("capability_id"))): item
        for item in (receipt.get("bindings") or [])
        if isinstance(item, Mapping)
    }
    result: list[dict[str, Any]] = []
    for domain in domains:
        if not isinstance(domain, Mapping):
            continue
        domain_copy = dict(domain)
        capabilities: list[dict[str, Any]] = []
        domain_id = str(domain.get("domain_id") or "")
        for raw in (domain.get("capabilities") or [])[:_MAX_ITEMS]:
            if not isinstance(raw, Mapping):
                continue
            item = dict(raw)
            binding = index.get((domain_id, str(item.get("id") or "")))
            if binding:
                item["workflow_ids"] = [
                    _text(value, 96) for value in binding.get("workflow_ids", [])[:8]
                ]
                item["plan_mode"] = _text(binding.get("plan_mode"), 24)
                if binding.get("plan_mode") == "unbound":
                    item["availability_reason"] = "workflow_not_registered"
                if "execution_readiness" in binding:
                    item["execution_readiness"] = _text(
                        binding.get("execution_readiness"), 32
                    )
                    item["execution_ready"] = bool(binding.get("execution_ready"))
                    item["execution_reason_code"] = _text(
                        binding.get("execution_reason_code"), 96
                    )
                    for key in ("missing_tools", "missing_result_types"):
                        if binding.get(key):
                            item[key] = _strings(binding.get(key))
            capabilities.append(item)
        domain_copy["capabilities"] = capabilities
        result.append(domain_copy)
    return result


def validate_plan_completeness(
    components: Sequence[Mapping[str, Any]],
    *,
    context: Mapping[str, Any],
    task_plan_bridge: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate that every selected component reached an accepted TaskPlan."""

    if not isinstance(components, (list, tuple)) or not components:
        raise PlanCompletenessError(
            "a successful plan requires components", code="plan_components_required"
        )
    if len(components) > _MAX_COMPONENTS:
        raise PlanCompletenessError(
            "plan components exceed the maximum", code="plan_components_limit"
        )

    capability_index = {
        (str(item.get("domain_id")), str(item.get("capability_id"))): item
        for item in (context.get("capability_index") or [])
        if isinstance(item, Mapping)
    }
    component_ids: list[str] = []
    for component in components:
        if not isinstance(component, Mapping):
            raise PlanCompletenessError(
                "component is not an object", code="plan_component_invalid"
            )
        domain_id = _text(component.get("domain_id"), 64)
        capability_id = _text(component.get("capability_id"), 96)
        component_id = _text(component.get("component_id"), 96)
        if not domain_id or not capability_id or not component_id:
            raise PlanCompletenessError(
                "component identity is incomplete", code="plan_component_field_missing"
            )
        if component_id in component_ids:
            raise PlanCompletenessError(
                "component ids must be unique", code="plan_component_duplicate"
            )
        component_ids.append(component_id)
        capability = capability_index.get((domain_id, capability_id))
        if capability is None:
            raise PlanCompletenessError(
                "component capability is not registered",
                code="capability_not_registered",
            )
        if capability.get("plan_mode") == "unbound":
            raise PlanCompletenessError(
                "component capability has no registered workflow",
                code="capability_not_materializable",
            )
        if "execution_ready" in capability and not bool(
            capability.get("execution_ready")
        ):
            raise PlanCompletenessError(
                "component capability is not execution-ready",
                code=_execution_reason_code(capability),
            )
        workflow = component.get("workflow")
        template_id = _text(workflow.get("template_id"), 96) if isinstance(workflow, Mapping) else ""
        workflow_ids = _strings(capability.get("workflow_ids"))
        if template_id and workflow_ids and template_id not in workflow_ids:
            raise PlanCompletenessError(
                "component workflow is not bound to the capability",
                code="capability_workflow_mismatch",
            )

    bridge = task_plan_bridge if isinstance(task_plan_bridge, Mapping) else {}
    bridge_components = [
        item for item in (bridge.get("components") or []) if isinstance(item, Mapping)
    ]
    accepted = [item for item in bridge_components if item.get("state") == "accepted"]
    if (
        str(bridge.get("state") or "") != "accepted"
        or len(accepted) != len(components)
        or int(bridge.get("materialized_count") or 0) != len(components)
    ):
        raise PlanCompletenessError(
            "not every component reached an accepted TaskPlan",
            code="plan_completeness_failed",
        )
    return {
        "schema_version": PLAN_COMPLETENESS_SCHEMA_VERSION,
        "status": "valid",
        "reason_code": "plan_completeness_valid",
        "component_count": len(components),
        "materialized_count": len(accepted),
        "component_ids": component_ids[:_MAX_COMPONENTS],
    }


def _workflow_matches(
    workflow: Mapping[str, Any],
    *,
    capability_id: str,
    explicit_ids: Sequence[str],
    tools: Sequence[str],
    results: Sequence[str],
) -> bool:
    workflow_id = _text(workflow.get("id"), 96)
    if not workflow_id:
        return False
    if explicit_ids:
        return workflow_id in explicit_ids
    if workflow_id == capability_id:
        return _policy_subset(workflow, tools=tools, results=results)
    return _policy_subset(workflow, tools=tools, results=results)


def _capability_execution_readiness(
    domain: Mapping[str, Any],
    workflows: Sequence[Mapping[str, Any]],
    *,
    workflow_ids: Sequence[str],
    mode: str,
) -> dict[str, Any]:
    """Check the catalog against the actual Tool/Result contract.

    A missing contract is intentionally represented as ``unknown`` and does
    not receive ``execution_ready``.  This preserves compatibility with old
    custom Domain test doubles while ensuring the production Runtime never
    treats an unknown contract as ready.  Once a contract is declared, every
    workflow tool and result type must be present in the already validated
    registries.
    """

    if mode == "answer_only":
        return {
            "execution_readiness_schema_version": EXECUTION_READINESS_SCHEMA_VERSION,
            "execution_readiness": "not_applicable",
            "execution_ready": True,
            "execution_reason_code": "answer_only_capability",
        }
    if not workflow_ids:
        return {
            "execution_readiness_schema_version": EXECUTION_READINESS_SCHEMA_VERSION,
            "execution_readiness": "workflow_unbound",
            "execution_ready": False,
            "execution_reason_code": "workflow_unbound",
        }

    contract = domain.get("execution_contract")
    # The public catalog projection keeps an empty object as a stable shape
    # when a legacy Domain does not expose execution_contract().  Treat that
    # the same as an omitted contract: it is unknown to the planner, not an
    # explicitly invalid contract.  Production Domains still publish a
    # non-empty, status-bearing contract and are checked strictly below.
    if not isinstance(contract, Mapping) or not contract:
        return {
            "execution_readiness_schema_version": EXECUTION_READINESS_SCHEMA_VERSION,
            "execution_readiness": "unknown",
            "execution_reason_code": "execution_contract_unknown",
        }
    if str(contract.get("status") or "") != "valid":
        return {
            "execution_readiness_schema_version": EXECUTION_READINESS_SCHEMA_VERSION,
            "execution_readiness": "schema_invalid",
            "execution_ready": False,
            "execution_reason_code": "execution_contract_invalid",
        }

    tool_definitions = contract.get("tool_definitions")
    tool_names = set(_strings(contract.get("tool_names")))
    if isinstance(tool_definitions, Mapping):
        tool_names.update(_text(key, 96) for key in tool_definitions if _text(key, 96))
    result_types = set(_strings(contract.get("result_type_ids")))
    missing_tools: list[str] = []
    missing_results: list[str] = []
    invalid_steps: list[str] = []
    for workflow in workflows:
        allowed_tools = _strings(workflow.get("allowed_tools"))
        declared_results = _strings(workflow.get("result_types"))
        missing_tools.extend(item for item in allowed_tools if item not in tool_names)
        missing_results.extend(item for item in declared_results if item not in result_types)
        for step in (workflow.get("step_blueprint") or workflow.get("steps") or ()):
            if not isinstance(step, Mapping):
                invalid_steps.append("step")
                continue
            tool = _text(step.get("tool"), 96)
            if not tool or tool not in allowed_tools:
                invalid_steps.append(tool or "step_tool_missing")
    missing_tools = _unique(missing_tools)
    missing_results = _unique(missing_results)
    invalid_steps = _unique(invalid_steps)
    if missing_tools or missing_results or invalid_steps:
        return {
            "execution_readiness_schema_version": EXECUTION_READINESS_SCHEMA_VERSION,
            "execution_readiness": "schema_invalid",
            "execution_ready": False,
            "execution_reason_code": "schema_invalid",
            "missing_tools": missing_tools[:8],
            "missing_result_types": missing_results[:8],
            "invalid_steps": invalid_steps[:8],
        }
    return {
        "execution_readiness_schema_version": EXECUTION_READINESS_SCHEMA_VERSION,
        "execution_readiness": "ready",
        "execution_ready": True,
        "execution_reason_code": "execution_contract_valid",
    }


def _execution_reason_code(value: Mapping[str, Any]) -> str:
    return _text(
        value.get("execution_reason_code") or value.get("execution_readiness"),
        96,
    ) or "execution_readiness_unknown"


def _unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _policy_subset(
    workflow: Mapping[str, Any], *, tools: Sequence[str], results: Sequence[str]
) -> bool:
    workflow_tools = _strings(workflow.get("allowed_tools"))
    workflow_results = _strings(workflow.get("result_types"))
    return bool(workflow_tools and workflow_results) and set(workflow_tools).issubset(
        set(tools)
    ) and set(workflow_results).issubset(set(results))


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, 96)
        if text and text not in result:
            result.append(text)
    return result[:24]


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = [
    "EXECUTION_READINESS_SCHEMA_VERSION",
    "PLAN_COMPLETENESS_SCHEMA_VERSION",
    "PlanCompletenessError",
    "annotate_catalog_capabilities",
    "assess_catalog_consistency",
    "validate_plan_completeness",
]
