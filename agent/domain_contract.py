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
DOMAIN_WORKFLOW_SEAM_SCHEMA_VERSION = "spatial-agent.domain-workflow-seam.v1"


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
                    "default",
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

    def tool_provider(self, *, backend_name: str = "memory", root: Any = None) -> Any:
        """Return the domain-owned provider used by the generic Runtime Factory."""

    def tool_provider_info(self, *, backend_name: str = "memory", root: Any = None) -> Mapping[str, Any]:
        """Return provider identity without initializing a backend."""

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

    def evidence_provider(self) -> Any:
        """Return the optional versioned runtime/release evidence provider."""

    def release_evidence(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Return optional domain-owned release/data publication evidence."""

    def extract_request_facts(self, request: str) -> Any:
        """Return the domain-neutral request facts for a request."""

    def analysis_intent(self, request: str, request_facts: Any) -> Any:
        """Optionally return a bounded domain-owned analysis intent.

        The Runtime validates the returned ``analysis-intent.v1`` object but
        does not infer operation semantics from Domain task names.
        """

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        """Return a JSON-safe capability catalog for the runtime context."""

    def discover(self, request: str, request_facts: Any) -> Any:
        """Return a mapping or object exposing ``as_context_dict``."""

    def select_workflow(
        self,
        discovery: Any,
        request_facts: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Return domain-owned metadata for capability/workflow selection."""

    def evidence_action_guidance(
        self,
        selection: Mapping[str, Any],
        *,
        request_facts: Any = None,
    ) -> Mapping[str, Any]:
        """Recommend bounded next actions from Domain-owned evidence status.

        Recommendations are advisory. The generic Runtime still applies the
        lifecycle and interaction gates before exposing an executable action.
        Older Domain Packs may omit this optional seam.
        """

    def normalize_workflow(self, workflow: Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalize one explicit workflow inside the Domain Pack."""

    def validate_workflow_plan(
        self,
        plan: Any,
        workflow: Mapping[str, Any],
    ) -> None:
        """Validate a Domain-owned workflow against a generated plan."""

    def resolve_capability_selection(
        self,
        capability_id: str,
        *,
        request_facts: Any = None,
        selection: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        """Resolve a selected capability into an explicit workflow payload."""

    def workflow_template_context(
        self,
        *,
        include_arg_shape: bool = False,
        compact: bool = True,
    ) -> Mapping[str, Any]:
        """Return the domain-owned planner workflow context."""

    def workflow_template_catalog(self) -> Mapping[str, Mapping[str, Any]]:
        """Return the Domain-owned workflow catalog used for validation."""

    def planner_guidance(self) -> Mapping[str, Any]:
        """Return bounded domain vocabulary and planner policy."""

    def planner_request_hint(
        self,
        request: str,
        workflow: Mapping[str, Any] | None = None,
    ) -> str:
        """Optionally enrich planner input with Domain-owned workflow facts."""

    def validate_plan(self, plan: Any) -> None:
        """Optionally validate a plan against Domain-owned capability policy.

        This is an execution gate, not a second ToolRegistry.  The Runtime
        still performs generic TaskPlan/DAG checks and every step still goes
        through ToolRegistry; a Domain may only reject a plan that exceeds its
        own declared workflow/capability contract.
        """

    def validate_open_react_plan(self, plan: Any) -> None:
        """Optionally validate safety rules for an open ReAct plan.

        ``validate_plan`` remains the explicit workflow/template gate. An
        open ReAct request deliberately does not inherit an automatic
        template's step count or allowlist. Domain Packs with additional
        non-template safety rules may implement this seam; the generic
        Runtime still applies Registry/schema, permission, approval and data
        gates.
        """

    def plan_policy(
        self,
        plan: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Return bounded metadata for the policy used to assess a plan.

        The metadata is evidence only. Runtime validation and ToolRegistry
        dispatch remain the execution gates.
        """

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        """Return domain-owned RequestFacts/discovery interpretation guidance."""

    def clarification_details(self, request: str) -> Any:
        """Return optional structured clarification details for a request."""

    def classify_conversation_turn(
        self,
        request: str,
        *,
        pending_request: str = "",
        pending_error: str = "",
    ) -> Any:
        """Optionally classify a pending input as reply or new request.

        The result is advisory metadata with ``mode`` set to
        ``clarification_reply`` or ``new_request``. Runtime owns the final
        state transition and keeps a legacy fallback for older packs.
        """

    def rule_planner(self) -> Any:
        """Return the deterministic Planner adapter owned by this domain."""


def discovery_context(
    discovery: Any,
    *,
    domain_id: str | None = None,
) -> dict[str, Any]:
    """Normalize a domain discovery result without imposing GIS types."""
    as_context = getattr(discovery, "as_context_dict", None)
    value = as_context() if callable(as_context) else discovery
    if not isinstance(value, Mapping):
        raise TypeError("domain discovery must be a mapping or expose as_context_dict()")
    result = dict(value)
    if domain_id and not result.get("domain_id"):
        result["domain_id"] = str(domain_id)[:80]
    return result


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


def select_workflow(
    domain_pack: DomainPack,
    discovery: Any,
    request_facts: Any,
    *,
    workflow: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve selection metadata without interpreting domain identifiers."""

    method = getattr(domain_pack, "select_workflow", None)
    if callable(method):
        try:
            value = method(discovery, request_facts, workflow=workflow)
        except TypeError:
            value = method(discovery, request_facts)
        if isinstance(value, Mapping):
            return dict(value)
    context = discovery_context(discovery)
    candidates = context.get("candidate_ids")
    return {
        "source": "explicit_workflow" if isinstance(workflow, Mapping) and workflow.get("template_id") else "domain_discovery",
        "selected_capability_id": context.get("selected_capability_id"),
        "candidate_ids": list(candidates) if isinstance(candidates, list) else [],
        "candidate_count": context.get("candidate_count"),
        "selected_by": "user" if isinstance(workflow, Mapping) and workflow.get("template_id") else "domain",
    }


def evidence_action_guidance(
    domain_pack: DomainPack,
    selection: Mapping[str, Any] | None,
    *,
    request_facts: Any = None,
) -> dict[str, Any]:
    """Read and safely normalize optional Domain evidence advice.

    The Runtime owns the lifecycle gate; this adapter only gives Domain Packs
    a narrow, versioned seam for recommending clarification or recovery.
    Provider/Domain exceptions become an unavailable guidance projection and
    never cross the public contract.
    """

    from .workflow_selection import normalize_evidence_action_guidance

    method = getattr(domain_pack, "evidence_action_guidance", None)
    if not callable(method):
        return normalize_evidence_action_guidance(None)
    try:
        try:
            value = method(
                dict(selection) if isinstance(selection, Mapping) else {},
                request_facts=request_facts,
            )
        except TypeError:
            value = method(dict(selection) if isinstance(selection, Mapping) else {})
    except Exception:
        return normalize_evidence_action_guidance(
            {
                "schema_version": "spatial-agent.evidence-action-guidance.v1",
                "state": "unavailable",
                "reason_code": "domain_evidence_action_guidance_failed",
                "source": "none",
            }
        )
    return normalize_evidence_action_guidance(value)


def workflow_seam_summary(domain_pack: DomainPack) -> dict[str, Any]:
    """Describe the Domain-owned workflow seams without exposing implementation.

    This is evidence for selection/recovery compatibility, not an execution
    switch. A legacy Domain can still run through the existing bounded
    fallbacks while the projection makes the missing seam explicit.
    """

    def available(name: str) -> bool:
        return callable(getattr(domain_pack, name, None))

    return {
        "schema_version": DOMAIN_WORKFLOW_SEAM_SCHEMA_VERSION,
        "selection": available("select_workflow"),
        "workflow_normalization": available("normalize_workflow"),
        "plan_validation": available("validate_workflow_plan"),
        "capability_resolution": available("resolve_capability_selection"),
    }


def workflow_context(domain_pack: DomainPack) -> dict[str, Any]:
    """Read workflow context through the domain seam without GIS fallback."""
    method = getattr(domain_pack, "workflow_template_context", None)
    if not callable(method):
        return {}
    value = method(include_arg_shape=False, compact=True)
    return dict(value) if isinstance(value, Mapping) else {}


def workflow_catalog(domain_pack: DomainPack) -> dict[str, dict[str, Any]]:
    """Read an optional Domain-owned workflow catalog without a GIS fallback."""

    method = getattr(domain_pack, "workflow_template_catalog", None)
    if not callable(method):
        return {}
    value = method()
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): deepcopy(dict(item))
        for key, item in value.items()
        if isinstance(item, Mapping)
    }


def planner_guidance(domain_pack: DomainPack) -> dict[str, Any]:
    """Read planner policy through the Domain Pack seam without GIS fallback."""
    from .planner_guidance import normalize_planner_guidance

    method = getattr(domain_pack, "planner_guidance", None)
    value = method() if callable(method) else {}
    return normalize_planner_guidance(value)


def planner_request_hint(domain_pack: DomainPack):
    """Return an optional Domain-owned request hint adapter.

    The generic LLM Planner does not interpret workflow constraints. A Domain
    may provide a bounded formatter; absent that seam, the original request is
    sent unchanged.
    """

    method = getattr(domain_pack, "planner_request_hint", None)
    return method if callable(method) else None


def request_understanding_guidance(domain_pack: DomainPack) -> dict[str, Any]:
    """Read and normalize request-understanding policy through the domain seam."""
    from .request_understanding import normalize_request_understanding_guidance

    method = getattr(domain_pack, "request_understanding_guidance", None)
    value = method() if callable(method) else {}
    return normalize_request_understanding_guidance(
        value,
        domain_id=str(getattr(domain_pack, "domain_id", "unknown")),
    )


def plan_policy(
    domain_pack: DomainPack,
    plan: Any,
    *,
    workflow: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve Domain-owned plan policy metadata without a GIS fallback."""

    from .plan_policy import PLAN_POLICY_SCHEMA_VERSION

    method = getattr(domain_pack, "plan_policy", None)
    if not callable(method):
        return {
            "schema_version": PLAN_POLICY_SCHEMA_VERSION,
            "available": False,
            "domain_id": str(getattr(domain_pack, "domain_id", "unknown"))[:80],
            "source": "none",
            "reason_code": "domain_policy_unavailable",
        }
    try:
        value = method(plan, workflow=workflow)
    except TypeError:
        # Keep older custom Domain Packs compatible with a positional-only
        # optional seam while still keeping the call domain-owned.
        try:
            value = method(plan)
        except Exception:
            value = {}
    except Exception:
        value = {}
    return dict(value) if isinstance(value, Mapping) else {
        "schema_version": PLAN_POLICY_SCHEMA_VERSION,
        "available": False,
        "domain_id": str(getattr(domain_pack, "domain_id", "unknown"))[:80],
        "source": "none",
        "reason_code": "domain_policy_unavailable",
    }


def clarification_details(domain_pack: DomainPack, request: str) -> dict[str, Any]:
    """Read optional Domain-owned clarification details without GIS fallback."""

    method = getattr(domain_pack, "clarification_details", None)
    if not callable(method):
        return {}
    try:
        value = method(str(request or ""))
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def rule_planner(domain_pack: DomainPack) -> Any:
    """Resolve a domain-owned deterministic Planner, if one is declared."""
    method = getattr(domain_pack, "rule_planner", None)
    value = method() if callable(method) else None
    return value if callable(getattr(value, "plan", None)) else None


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
    """Read bounded runtime evidence through the provider compatibility seam."""
    provider = _evidence_provider(domain_pack)
    method = getattr(provider, "snapshot", None) if provider is not None else None
    if callable(method):
        value = method("runtime", max_files=max_files)
    else:
        method = getattr(provider, "runtime_snapshot", None) if provider is not None else None
        if callable(method):
            value = method(max_files=max_files)
            method = None
        else:
            method = getattr(domain_pack, "runtime_evidence", None)
            if not callable(method):
                return {}
            value = method(max_files=max_files)
    if not isinstance(value, Mapping):
        return {}
    from agent.evidence.contract import attach_evidence_contract

    return attach_evidence_contract(
        value,
        domain_id=str(getattr(domain_pack, "domain_id", "unknown")),
        kind="runtime",
    )


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
    provider = _evidence_provider(domain_pack)
    method = getattr(provider, "snapshot", None) if provider is not None else None
    if callable(method):
        value = method("release", config_path=config_path, max_files=max_files)
    else:
        method = getattr(provider, "release_snapshot", None) if provider is not None else None
        if callable(method):
            value = method(config_path=config_path, max_files=max_files)
        else:
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
    if not isinstance(value, Mapping):
        return {}
    from agent.evidence.contract import attach_evidence_contract

    return attach_evidence_contract(
        value,
        domain_id=str(getattr(domain_pack, "domain_id", "unknown")),
        kind="release",
    )


def _evidence_provider(domain_pack: DomainPack) -> Any:
    """Resolve the new provider without breaking older Domain Pack adapters."""
    factory = getattr(domain_pack, "evidence_provider", None)
    if not callable(factory):
        return None
    value = factory()
    return value if value is not None else None


def default_domain_pack() -> DomainPack:
    """Load the GIS pack lazily for backwards-compatible default behavior."""
    from domains.gis import GIS_DOMAIN_PACK

    return GIS_DOMAIN_PACK
