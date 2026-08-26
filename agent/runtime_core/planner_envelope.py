"""Small, versioned context envelope sent to a Planner provider.

The Composite request context is intentionally richer than the provider
payload: Runtime validation and recovery need the full receipt, while an LLM
only needs request facts, registered choices, and the execution closure for
those choices.  This module is a domain-neutral projection seam; it never
selects a tool or interprets a Domain field.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.request_understanding import normalize_request_understanding_guidance
from agent.runtime_core.request_fact_readiness import project_request_fact_readiness


PLANNER_ENVELOPE_SCHEMA_VERSION = "spatial-agent.planner-envelope.v1"
PLANNER_ENVELOPE_MAX_BYTES = 96_000
PLANNER_EXECUTION_IDENTITY_SCHEMA_VERSION = (
    "spatial-agent.planner-execution-identity.v1"
)
PLANNER_PROJECTION_STAGES = (
    "discovery",
    "selection",
    "execution",
    "repair",
)
# Keep the public helper backward compatible for callers that construct an
# envelope directly.  Runtime request construction explicitly uses
# ``discovery`` and the LLM adapter explicitly re-projects to ``selection``.
PLANNER_ENVELOPE_DEFAULT_STAGE = "selection"
PLANNER_ENVELOPE_LAYERS = (
    "request_facts",
    "capability_index",
    "selection",
    "execution_contract",
)

_MAX_DOMAINS = 8
_MAX_CANDIDATES = 16
_MAX_WORKFLOWS = 24
_MAX_FIELDS = 8
_MAX_LIST = 16
_PRIVATE_KEYS = {
    "api_key",
    "credential",
    "messages",
    "model_response",
    "password",
    "private_payload",
    "prompt",
    "raw_response",
    "secret",
    "source_path",
    "token",
}
_PROJECTED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "projection_stage",
    "source_context_schema_version",
    "planner",
    "backend",
    "request_fingerprint",
    "request_summary",
    "layers",
    "redaction",
    "request_facts",
    "capability_index",
    "selection",
    "execution_contract",
    "discovery",
    "clarification",
    "data_readiness",
    "selected_components",
    "fact_handoff",
    "execution_identity",
    "planner_repair",
    "repair_boundary",
    "limits",
}


class PlannerEnvelopeError(ValueError):
    """A provider-facing planner envelope cannot be safely projected."""

    def __init__(self, message: str, *, code: str = "planner_envelope_invalid") -> None:
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def build_planner_envelope(
    context: Mapping[str, Any] | None,
    *,
    max_bytes: int = PLANNER_ENVELOPE_MAX_BYTES,
    max_candidates: int = _MAX_CANDIDATES,
    max_workflows: int = _MAX_WORKFLOWS,
    projection_stage: str = PLANNER_ENVELOPE_DEFAULT_STAGE,
    selected_components: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project only the context required by one Planner decision stage.

    The Runtime keeps the complete request context for validation, recovery,
    and evidence.  This function is the provider boundary: every projection
    is rebuilt from the trusted context, and execution/repair projections are
    restricted to explicitly selected component identities.
    """

    if not isinstance(context, Mapping):
        context = {}
    stage = normalize_projection_stage(projection_stage)
    byte_limit = _positive_limit(max_bytes, "max_bytes")
    candidate_limit = _positive_limit(max_candidates, "max_candidates")
    workflow_limit = _positive_limit(max_workflows, "max_workflows")
    selected_keys = _selected_capability_keys(context, selected_components)
    # A repair may be requested because the provider response was malformed
    # before any component could be validated.  In that case there is no
    # trusted selection to filter to; retain the bounded selection catalog so
    # the one repair attempt can reconstruct a legal choice.  Once selection
    # exists, repair is as narrow as execution.
    selected_filter = (
        selected_keys
        if stage == "execution" or (stage == "repair" and selected_keys)
        else None
    )
    candidates = _candidate_index(
        context.get("capability_index"),
        candidate_limit,
        selected_keys=selected_filter,
        compact=stage == "discovery",
    )
    selected_domains = {
        key.split("::", 1)[0]
        for key in selected_keys
        if "::" in key
    }
    request_facts = _request_facts(
        context,
        domain_ids=selected_domains
        if stage in {"execution", "repair"} and selected_domains
        else None,
        compact=stage == "discovery",
    )
    envelope: dict[str, Any] = {
        "schema_version": PLANNER_ENVELOPE_SCHEMA_VERSION,
        "projection_stage": stage,
        "source_context_schema_version": _text(context.get("schema_version"), 96)
        or None,
        "planner": _text(context.get("planner"), 32) or None,
        "backend": _text(context.get("backend"), 32) or None,
        "request_fingerprint": _text(context.get("request_fingerprint"), 128) or None,
        "request_summary": _text(context.get("request_summary"), 640),
        "layers": list(PLANNER_ENVELOPE_LAYERS),
        "redaction": {
            "applied": True,
            "private_fields_removed": True,
        },
        "request_facts": request_facts,
        "capability_index": candidates,
        "selection": _selection_projection(
            context, candidates, selected_keys=selected_keys
        ),
        "limits": {
            "max_bytes": byte_limit,
            "max_candidates": candidate_limit,
            "max_workflows": workflow_limit,
        },
    }
    if stage == "discovery":
        # Discovery answers “what may be relevant?”  Workflow bindings and
        # diagnostic consistency details stay inside Runtime until selection.
        envelope["discovery"] = _discovery_projection(context.get("discovery"))
        envelope["clarification"] = _clarification_projection(
            context.get("clarification")
        )
        envelope["data_readiness"] = _readiness_projection(
            context.get("data_readiness")
        )
    elif stage == "selection":
        # Selection needs the minimum closure required to choose registered
        # capabilities, but does not need the full internal catalog.
        envelope["execution_contract"] = _execution_projection(
            context, candidates, workflow_limit, include_profiles=False
        )
        envelope["discovery"] = _discovery_projection(context.get("discovery"))
        envelope["clarification"] = _clarification_projection(
            context.get("clarification")
        )
    else:
        # Execution and repair are continuation stages.  They never expose an
        # unbounded catalog: only selected component identities, their
        # registered workflow/result closure, and declared fact gaps survive.
        envelope["execution_contract"] = _execution_projection(
            context,
            candidates,
            workflow_limit,
            selected_keys=selected_filter,
        )
        envelope["selected_components"] = _selected_components_projection(
            context, selected_components, selected_keys
        )
        envelope["fact_handoff"] = _fact_handoff_projection(context, selected_keys)
        envelope["clarification"] = _clarification_projection(
            context.get("clarification"), selected_domains=selected_domains or None
        )
        if stage == "repair":
            repair = context.get("planner_repair")
            if isinstance(repair, Mapping):
                envelope["planner_repair"] = _repair_projection(repair)
                envelope["repair_boundary"] = {
                    "preserve": [
                        "request_fingerprint",
                        "selected_components",
                        "facts",
                        "execution_contract",
                        "result_profiles",
                    ],
                    "allowed_outcome": "success|needs_clarification|rejected",
                    "max_attempts": 1,
                }
    _assert_budget(envelope, byte_limit)
    return envelope


def normalize_planner_envelope(
    value: Mapping[str, Any], *, max_bytes: int = PLANNER_ENVELOPE_MAX_BYTES
) -> dict[str, Any]:
    """Validate an already projected envelope without accepting new fields."""

    if not isinstance(value, Mapping):
        raise PlannerEnvelopeError(
            "planner envelope must be an object",
            code="planner_envelope_object_required",
        )
    if str(value.get("schema_version") or "") != PLANNER_ENVELOPE_SCHEMA_VERSION:
        raise PlannerEnvelopeError(
            "planner envelope schema is unsupported",
            code="planner_envelope_schema_invalid",
        )
    unknown = sorted(
        str(key) for key in set(value) - _PROJECTED_TOP_LEVEL_FIELDS
    )
    if unknown:
        raise PlannerEnvelopeError(
            "planner envelope contains unsupported fields",
            code="planner_envelope_field_invalid",
        )
    stage = normalize_projection_stage(
        value.get("projection_stage", PLANNER_ENVELOPE_DEFAULT_STAGE)
    )
    envelope = {
        str(key): _safe_envelope_value(item)
        for key, item in value.items()
        if str(key) in _PROJECTED_TOP_LEVEL_FIELDS
        and str(key).strip().lower().replace("-", "_") not in _PRIVATE_KEYS
    }
    envelope["schema_version"] = PLANNER_ENVELOPE_SCHEMA_VERSION
    envelope["projection_stage"] = stage
    envelope["source_context_schema_version"] = _text(
        value.get("source_context_schema_version"), 96
    ) or None
    if "capability_index" not in envelope or not isinstance(
        envelope.get("capability_index"), list
    ):
        raise PlannerEnvelopeError(
            "planner envelope capability_index is invalid",
            code="planner_envelope_field_invalid",
        )
    _assert_budget(envelope, _positive_limit(max_bytes, "max_bytes"))
    return envelope


def normalize_projection_stage(value: Any) -> str:
    """Validate the finite provider projection vocabulary."""

    stage = str(value or "").strip().lower()
    if stage not in PLANNER_PROJECTION_STAGES:
        raise PlannerEnvelopeError(
            "planner projection stage is unsupported",
            code="planner_envelope_stage_invalid",
        )
    return stage


def build_execution_planner_envelope(
    context: Mapping[str, Any] | None,
    *,
    components: Sequence[Mapping[str, Any]],
    execution_binding: Mapping[str, Any],
    max_bytes: int = PLANNER_ENVELOPE_MAX_BYTES,
) -> dict[str, Any]:
    """Build an execution projection from one validated binding.

    This is deliberately a narrow seam.  It does not authorize execution and
    it does not replace :mod:`execution_binding`; it proves that the
    stage-aware projection describes exactly the component set that already
    crossed the TaskPlan/DAG and binding gates.
    """

    if not isinstance(execution_binding, Mapping):
        raise PlannerEnvelopeError(
            "execution projection requires a binding",
            code="planner_execution_binding_invalid",
        )
    try:
        from agent.runtime_core.execution_binding import validate_execution_binding

        binding = validate_execution_binding(execution_binding)
    except Exception as exc:
        raise PlannerEnvelopeError(
            "execution projection binding is not validated",
            code="planner_execution_binding_invalid",
        ) from exc
    if not isinstance(components, (list, tuple)) or not components:
        raise PlannerEnvelopeError(
            "execution projection components are required",
            code="planner_execution_components_invalid",
        )

    selected: list[dict[str, Any]] = []
    for raw in components[:8]:
        if not isinstance(raw, Mapping):
            raise PlannerEnvelopeError(
                "execution projection component is invalid",
                code="planner_execution_components_invalid",
            )
        component = {
            "component_id": _text(raw.get("component_id"), 48),
            "domain_id": _text(raw.get("domain_id"), 64),
            "capability_id": _text(raw.get("capability_id"), 96),
            "depends_on": _strings(raw.get("depends_on"), 8),
            "required": bool(raw.get("required", True)),
        }
        if not component["component_id"] or not component["domain_id"] or not component["capability_id"]:
            raise PlannerEnvelopeError(
                "execution projection component identity is incomplete",
                code="planner_execution_components_invalid",
            )
        selected.append(component)

    binding_ids = [
        _text(value, 48) for value in (binding.get("component_ids") or [])
    ]
    selected_ids = [item["component_id"] for item in selected]
    if selected_ids != binding_ids:
        raise PlannerEnvelopeError(
            "execution projection component set does not match binding",
            code="planner_execution_binding_mismatch",
        )
    binding_components = {
        _text(item.get("component_id"), 48): item
        for item in (binding.get("components") or [])
        if isinstance(item, Mapping)
    }
    for item in selected:
        bound = binding_components.get(item["component_id"])
        if not isinstance(bound, Mapping):
            raise PlannerEnvelopeError(
                "execution projection component identity does not match binding",
                code="planner_execution_binding_mismatch",
            )
        if (
            _text(bound.get("domain_id"), 64) != item["domain_id"]
            or _text(bound.get("capability_id"), 96) != item["capability_id"]
            or _strings(bound.get("depends_on"), 8) != item["depends_on"]
            or bool(bound.get("required", True)) != item["required"]
        ):
            raise PlannerEnvelopeError(
                "execution projection component identity does not match binding",
                code="planner_execution_binding_mismatch",
            )

    projected_context = dict(context) if isinstance(context, Mapping) else {}
    projected_context["selected_components"] = selected
    envelope = build_planner_envelope(
        projected_context,
        max_bytes=max_bytes,
        projection_stage="execution",
        selected_components=selected,
    )
    envelope["execution_identity"] = {
        "schema_version": PLANNER_EXECUTION_IDENTITY_SCHEMA_VERSION,
        "context_request_fingerprint": envelope.get("request_fingerprint"),
        "binding_request_fingerprint": _text(
            binding.get("request_fingerprint"), 128
        )
        or None,
        "binding_fingerprint": _text(binding.get("binding_fingerprint"), 128)
        or None,
        "component_ids": selected_ids,
        "components": [
            {
                "component_id": item["component_id"],
                "domain_id": item["domain_id"],
                "capability_id": item["capability_id"],
                "plan_fingerprint": _text(
                    binding_components[item["component_id"]].get(
                        "plan_fingerprint"
                    ),
                    128,
                )
                or None,
            }
            for item in selected
        ],
    }
    _assert_budget(envelope, _positive_limit(max_bytes, "max_bytes"))
    return envelope


def project_planner_envelope_evidence(value: Any) -> dict[str, Any]:
    """Return a small, transport-safe receipt for a stage projection."""

    if not isinstance(value, Mapping):
        return {
            "schema_version": PLANNER_ENVELOPE_SCHEMA_VERSION,
            "stage": "unavailable",
            "request_fingerprint": None,
        }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity = value.get("execution_identity")
    result = {
        "schema_version": _text(value.get("schema_version"), 96)
        or PLANNER_ENVELOPE_SCHEMA_VERSION,
        "stage": _text(value.get("projection_stage"), 24) or "unknown",
        "request_fingerprint": _text(value.get("request_fingerprint"), 128)
        or None,
        "byte_size": len(encoded.encode("utf-8")),
        "candidate_count": len(_sequence(value.get("capability_index"))),
        "selected_component_ids": [
            _text(item.get("component_id"), 48)
            for item in _sequence(value.get("selected_components"))
            if isinstance(item, Mapping) and _text(item.get("component_id"), 48)
        ][:8],
    }
    if isinstance(identity, Mapping):
        result["execution_identity"] = {
            "schema_version": _text(identity.get("schema_version"), 96),
            "binding_request_fingerprint": _text(
                identity.get("binding_request_fingerprint"), 128
            )
            or None,
            "binding_fingerprint": _text(
                identity.get("binding_fingerprint"), 128
            )
            or None,
            "component_ids": [
                _text(item, 48)
                for item in _sequence(identity.get("component_ids"))
                if _text(item, 48)
            ][:8],
        }
    return result


def _request_facts(
    context: Mapping[str, Any],
    *,
    domain_ids: set[str] | None = None,
    compact: bool = False,
) -> dict[str, Any]:
    domains: list[dict[str, Any]] = []
    for raw in _sequence(context.get("domain_contexts"))[:_MAX_DOMAINS]:
        if not isinstance(raw, Mapping):
            continue
        domain_id = _text(raw.get("domain_id"), 64)
        if domain_ids is not None and domain_id not in domain_ids:
            continue
        facts = raw.get("facts") if isinstance(raw.get("facts"), Mapping) else {}
        projected_facts = {
            "schema_version": _text(facts.get("schema_version"), 96) or None,
            "admin_name": _text(facts.get("admin_name"), 120) or None,
            "entities": _safe_value(facts.get("entities") or {}, depth=0),
            "tasks": _strings(facts.get("tasks"), 8),
            "datasets": _strings(facts.get("datasets"), 16),
            "constraints": _safe_value(facts.get("constraints") or {}, depth=0),
        }
        if not compact:
            projected_facts["evidence"] = _strings(facts.get("evidence"), 8)
        domains.append(
            {
                "domain_id": domain_id,
                "facts": projected_facts,
                "understanding": _understanding_projection(
                    raw.get("request_understanding"),
                    domain_id=raw.get("domain_id"),
                ),
                "data_readiness": _readiness(raw.get("data_readiness")),
                "fact_readiness": project_request_fact_readiness(
                    raw.get("fact_readiness")
                ),
                "clarification": _small_clarification(raw.get("clarification")),
            }
        )
    if not domains:
        facts = context.get("facts")
        if domain_ids is None:
            domains.append(
                {
                    "domain_id": None,
                    "facts": _safe_value(facts or {}, depth=0),
                    "data_readiness": {},
                    "clarification": {},
                }
            )
    return {"domains": domains}


def _understanding_projection(value: Any, *, domain_id: Any = None) -> dict[str, Any]:
    """Keep Domain-owned request hints bounded in the provider envelope."""

    return normalize_request_understanding_guidance(
        value,
        domain_id=str(domain_id or "unknown")[:80],
    )


def _candidate_index(
    value: Any,
    limit: int,
    *,
    selected_keys: set[str] | None = None,
    compact: bool = False,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in _sequence(value):
        if not isinstance(raw, Mapping):
            continue
        domain_id = _text(raw.get("domain_id"), 64)
        capability_id = _text(raw.get("capability_id"), 96)
        if not domain_id or not capability_id:
            continue
        identity = (domain_id, capability_id)
        if identity in seen:
            continue
        selection_key = _text(raw.get("selection_key"), 140) or (
            f"{domain_id}::{capability_id}"[:140]
        )
        canonical_key = f"{domain_id}::{capability_id}"[:140]
        if selected_keys is not None and not (
            selection_key in selected_keys or canonical_key in selected_keys
        ):
            continue
        seen.add(identity)
        item: dict[str, Any] = {
            "domain_id": domain_id,
            "capability_id": capability_id,
            "selection_key": selection_key,
            "label": _text(raw.get("label"), 160),
            "description": _text(raw.get("description"), 320),
            "available": bool(raw.get("available")),
            "availability_reason": _text(raw.get("availability_reason"), 160),
            "datasets": _strings(raw.get("datasets"), 8),
            "missing_datasets": _strings(raw.get("missing_datasets"), 8),
            "result_types": _strings(raw.get("result_types"), 16),
            "output_profiles": _profiles(raw.get("output_profiles")),
            "missing_fact_ids": _strings(raw.get("missing_fact_ids"), 8),
            "missing_facts": _fact_fields(raw.get("missing_facts")),
        }
        if not compact:
            item["request_requirements"] = _requirements(
                raw.get("request_requirements")
            )
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _selection_projection(
    context: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    selected_keys: Sequence[str] = (),
) -> dict[str, Any]:
    discovery = context.get("discovery")
    discovery = discovery if isinstance(discovery, Mapping) else {}
    selected: list[str] = [
        _text(value, 140) for value in sorted(selected_keys) if _text(value, 140)
    ]
    for raw in _sequence(context.get("domain_contexts")):
        if not isinstance(raw, Mapping):
            continue
        domain_id = _text(raw.get("domain_id"), 64)
        local_discovery = raw.get("discovery")
        local_discovery = (
            local_discovery if isinstance(local_discovery, Mapping) else {}
        )
        value = local_discovery.get("selected_capability_id")
        if value:
            key = f"{domain_id}::{_text(value, 96)}"[:140]
            if key not in selected:
                selected.append(key)
    if not selected:
        for raw in _sequence(discovery.get("candidates")):
            if not isinstance(raw, Mapping):
                continue
            if str(raw.get("state") or "") not in {"available", "selected"}:
                continue
            key = f"{_text(raw.get('domain_id'), 64)}::{_text(raw.get('capability_id'), 96)}"[:140]
            if key not in selected:
                selected.append(key)
    candidate_keys = [
        _text(item.get("selection_key"), 140)
        for item in candidates
        if _text(item.get("selection_key"), 140)
    ]
    return {
        "state": _text(discovery.get("state"), 32) or "unknown",
        "reason_code": _text(discovery.get("reason_code"), 96) or "unknown",
        "candidate_count": len(candidate_keys),
        "candidate_keys": candidate_keys[:_MAX_CANDIDATES],
        "selected_capability_keys": selected[:_MAX_CANDIDATES],
    }


def _execution_projection(
    context: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    workflow_limit: int,
    *,
    selected_keys: set[str] | None = None,
    include_profiles: bool = True,
) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = []
    workflow_ids: set[tuple[str, str]] = set()
    candidate_identities = {
        (str(item.get("domain_id")), str(item.get("capability_id")))
        for item in candidates
        if isinstance(item, Mapping)
    }
    for raw in _sequence(context.get("capability_index")):
        if not isinstance(raw, Mapping):
            continue
        identity = {
            "domain_id": _text(raw.get("domain_id"), 64),
            "capability_id": _text(raw.get("capability_id"), 96),
        }
        if not identity["domain_id"] or not identity["capability_id"]:
            continue
        if (identity["domain_id"], identity["capability_id"]) not in candidate_identities:
            continue
        raw_key = _text(raw.get("selection_key"), 140) or (
            f"{identity['domain_id']}::{identity['capability_id']}"[:140]
        )
        canonical_key = (
            f"{identity['domain_id']}::{identity['capability_id']}"[:140]
        )
        if selected_keys is not None and not (
            raw_key in selected_keys or canonical_key in selected_keys
        ):
            continue
        allowed = {
            **identity,
            "workflow_ids": _strings(raw.get("workflow_ids"), 8),
            "plan_mode": _text(raw.get("plan_mode"), 32) or None,
            "tools": _strings(raw.get("tools"), 24),
            "result_types": _strings(raw.get("result_types"), 16),
            "execution_readiness": _text(raw.get("execution_readiness"), 32)
            or None,
            "execution_ready": (
                bool(raw.get("execution_ready"))
                if "execution_ready" in raw
                else None
            ),
            "execution_reason_code": _text(raw.get("execution_reason_code"), 96)
            or None,
            "missing_tools": _strings(raw.get("missing_tools"), 8),
            "missing_result_types": _strings(raw.get("missing_result_types"), 8),
        }
        if include_profiles:
            allowed["output_profiles"] = _profiles(raw.get("output_profiles"))
        bindings.append(allowed)
        for workflow_id in allowed["workflow_ids"]:
            workflow_ids.add((identity["domain_id"], workflow_id))

    workflows: list[dict[str, Any]] = []
    for raw in _sequence(context.get("workflow_index")):
        if not isinstance(raw, Mapping):
            continue
        identity = (_text(raw.get("domain_id"), 64), _text(raw.get("workflow_id"), 96))
        if identity not in workflow_ids:
            continue
        workflows.append(
            {
                "domain_id": identity[0],
                "workflow_id": identity[1],
                "label": _text(raw.get("label"), 160),
                "allowed_tools": _strings(raw.get("allowed_tools"), 24),
                "result_types": _strings(raw.get("result_types"), 16),
            }
        )
        if len(workflows) >= workflow_limit:
            break
    return {
        "capabilities": bindings[: len(candidates)],
        "workflows": workflows,
        "data_readiness": _readiness_projection(
            context.get("data_readiness"),
            domain_contexts=context.get("domain_contexts"),
            selected_domains=(
                {
                    str(item.get("domain_id"))
                    for item in candidates
                    if isinstance(item, Mapping)
                }
                if selected_keys is not None
                else None
            ),
        ),
    }


def _selected_capability_keys(
    context: Mapping[str, Any],
    selected_components: Sequence[Mapping[str, Any]] | None,
) -> set[str]:
    """Resolve selected identities from trusted internal continuation data."""

    sources: list[Any] = []
    if isinstance(selected_components, Sequence) and not isinstance(
        selected_components, (str, bytes)
    ):
        sources.append(selected_components)
    for key in ("selected_components", "components"):
        value = context.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            sources.append(value)
    for key in ("task_plan_bridge", "execution_binding"):
        value = context.get(key)
        if isinstance(value, Mapping):
            components = value.get("components")
            if isinstance(components, Sequence) and not isinstance(
                components, (str, bytes)
            ):
                sources.append(components)

    result: set[str] = set()
    for source in sources:
        for raw in source:
            if not isinstance(raw, Mapping):
                continue
            domain_id = _text(raw.get("domain_id"), 64)
            capability_id = _text(raw.get("capability_id"), 96)
            if domain_id and capability_id:
                result.add(f"{domain_id}::{capability_id}"[:140])
    for raw in _sequence(context.get("selected_capability_keys")):
        key = _text(raw, 140)
        if "::" in key:
            result.add(key)
    return result


def _selected_components_projection(
    context: Mapping[str, Any],
    selected_components: Sequence[Mapping[str, Any]] | None,
    selected_keys: set[str],
) -> list[dict[str, Any]]:
    sources: list[Any] = []
    if isinstance(selected_components, Sequence) and not isinstance(
        selected_components, (str, bytes)
    ):
        sources.append(selected_components)
    for key in ("selected_components", "components"):
        value = context.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            sources.append(value)
    for key in ("task_plan_bridge", "execution_binding"):
        value = context.get(key)
        if isinstance(value, Mapping):
            components = value.get("components")
            if isinstance(components, Sequence) and not isinstance(
                components, (str, bytes)
            ):
                sources.append(components)

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        for raw in source:
            if not isinstance(raw, Mapping):
                continue
            domain_id = _text(raw.get("domain_id"), 64)
            capability_id = _text(raw.get("capability_id"), 96)
            key = f"{domain_id}::{capability_id}"[:140]
            if not domain_id or not capability_id or key not in selected_keys:
                continue
            component_id = _text(raw.get("component_id"), 96)
            if not component_id or component_id in seen:
                continue
            seen.add(component_id)
            result.append(
                {
                    "component_id": component_id,
                    "domain_id": domain_id,
                    "capability_id": capability_id,
                    "depends_on": _strings(raw.get("depends_on"), 8),
                    "required": bool(raw.get("required", True)),
                }
            )
            if len(result) >= 8:
                return result
    return result


def _fact_handoff_projection(
    context: Mapping[str, Any], selected_keys: set[str]
) -> dict[str, Any]:
    """Expose only declared fact gaps at continuation stages."""

    values: list[Any] = []
    for key in ("fact_handoff", "component_fact_handoff", "composite_fact_handoff"):
        value = context.get(key)
        if isinstance(value, Mapping):
            values.append(value)
    task_plan = context.get("task_plan_bridge")
    if isinstance(task_plan, Mapping) and isinstance(
        task_plan.get("fact_handoff"), Mapping
    ):
        values.append(task_plan["fact_handoff"])

    projected: list[dict[str, Any]] = []
    for value in values:
        components = value.get("components") if isinstance(value, Mapping) else None
        components = components if isinstance(components, Sequence) else [value]
        for raw in components:
            if not isinstance(raw, Mapping):
                continue
            domain_id = _text(raw.get("domain_id"), 64)
            capability_id = _text(raw.get("capability_id"), 96)
            key = f"{domain_id}::{capability_id}"[:140]
            if selected_keys and key not in selected_keys:
                continue
            projected.append(
                {
                    "component_id": _text(raw.get("component_id"), 96) or None,
                    "domain_id": domain_id or None,
                    "capability_id": capability_id or None,
                    "state": _text(raw.get("state"), 24) or "unknown",
                    "reason_code": _text(raw.get("reason_code"), 96) or None,
                    "missing_fields": _missing_field_projection(
                        raw.get("missing_fields")
                    ),
                    "next_actions": _strings(raw.get("next_actions"), 4),
                }
            )
            if len(projected) >= 8:
                break
        if len(projected) >= 8:
            break
    return {
        "schema_version": "spatial-agent.planner-fact-handoff.v1",
        "components": projected,
        "missing_field_count": sum(
            len(item.get("missing_fields") or []) for item in projected
        ),
    }


def _missing_field_projection(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in _sequence(value)[:_MAX_FIELDS]:
        if isinstance(raw, Mapping):
            item = {
                "id": _text(raw.get("id"), 80),
                "label": _text(raw.get("label"), 120),
                "kind": _text(raw.get("kind"), 32),
                "required": bool(raw.get("required", True)),
            }
        else:
            item = {"id": _text(raw, 80), "label": _text(raw, 120), "kind": "fact", "required": True}
        if item["id"]:
            result.append(item)
    return result


def _discovery_projection(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    candidates = _sequence(source.get("candidates"))
    states: dict[str, int] = {}
    for raw in candidates:
        if isinstance(raw, Mapping):
            state = _text(raw.get("state"), 32) or "unknown"
            states[state] = states.get(state, 0) + 1
    return {
        "schema_version": _text(source.get("schema_version"), 96) or None,
        "state": _text(source.get("state"), 32) or "unknown",
        "reason_code": _text(source.get("reason_code"), 96) or "unknown",
        "candidate_states": states,
        "data_requirement_count": len(_sequence(source.get("data_requirements"))),
        "next_actions": _strings(source.get("next_actions"), 4),
    }


def _clarification_projection(
    value: Any, *, selected_domains: set[str] | None = None
) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    missing = source.get("missing_by_domain") or []
    if selected_domains is not None:
        missing = [
            item
            for item in _sequence(missing)
            if isinstance(item, Mapping)
            and _text(item.get("domain_id"), 64) in selected_domains
        ]
    return {
        "state": _text(source.get("state"), 32) or "not_required",
        "reason_code": _text(source.get("reason_code"), 96) or "unknown",
        "message": _text(source.get("message"), 640),
        "missing_by_domain": _safe_value(missing, depth=0),
        "next_actions": _strings(source.get("next_actions"), 4),
    }


def _small_clarification(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "state": _text(source.get("state"), 32) or "not_required",
        "missing_fields": _safe_value(source.get("missing_fields") or [], depth=0),
    }


def _readiness(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "status": _text(source.get("status"), 32) or "unknown",
        "reason_code": _text(source.get("reason_code"), 96) or None,
    }


def _readiness_projection(
    value: Any,
    *,
    domain_contexts: Any = None,
    selected_domains: set[str] | None = None,
) -> dict[str, Any]:
    """Keep readiness useful while dropping verbose catalog diagnostics."""

    source = value if isinstance(value, Mapping) else {}
    domains_source = source.get("domains")
    if not isinstance(domains_source, Mapping):
        domains_source = {}
        for raw in _sequence(domain_contexts):
            if not isinstance(raw, Mapping):
                continue
            domain_id = _text(raw.get("domain_id"), 64)
            if domain_id:
                domains_source[domain_id] = raw.get("data_readiness")
    domains: dict[str, dict[str, Any]] = {}
    for key, raw in list(domains_source.items())[:_MAX_DOMAINS]:
        domain_id = _text(key, 64)
        if not domain_id or (
            selected_domains is not None and domain_id not in selected_domains
        ):
            continue
        domains[domain_id] = _readiness(raw)
    result = _readiness(source)
    if domains:
        result["domains"] = domains
    return result


def _repair_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": _text(value.get("schema_version"), 96),
        "reason_code": _text(value.get("reason_code"), 96),
        "attempt": value.get("attempt") if isinstance(value.get("attempt"), int) else 1,
        "max_attempts": value.get("max_attempts")
        if isinstance(value.get("max_attempts"), int)
        else 1,
    }


def _requirements(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    fields = []
    for raw in _sequence(source.get("clarification_fields"))[:_MAX_FIELDS]:
        if not isinstance(raw, Mapping):
            continue
        field_id = _text(raw.get("id"), 80)
        label = _text(raw.get("label"), 120)
        if not field_id or not label:
            continue
        fields.append(
            {
                "id": field_id,
                "label": label,
                "kind": _text(raw.get("kind"), 32),
                "required": bool(raw.get("required", True)),
            }
        )
    return {"clarification_fields": fields}


def _fact_fields(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for raw in _sequence(value)[:8]:
        if not isinstance(raw, Mapping):
            continue
        field_id = _text(raw.get("id"), 80)
        if not field_id:
            continue
        result.append(
            {
                "id": field_id,
                "label": _text(raw.get("label") or field_id, 120),
                "kind": _text(raw.get("kind"), 32) or "fact",
            }
        )
    return result


def _profiles(value: Any) -> list[dict[str, Any]]:
    result = []
    for raw in _sequence(value)[:24]:
        if not isinstance(raw, Mapping):
            continue
        result_type = _text(raw.get("result_type"), 96)
        kinds = _strings(raw.get("kinds"), 8)
        if not result_type or not kinds:
            continue
        result.append(
            {
                "result_type": result_type,
                "schema_version": _text(raw.get("schema_version"), 96) or None,
                "primary": _text(raw.get("primary"), 32) or kinds[0],
                "kinds": kinds,
            }
        )
    return result


def _safe_value(value: Any, *, depth: int) -> Any:
    if depth >= 3:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _safe_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
            if str(key).strip().lower().replace("-", "_") not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:_MAX_LIST]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:640] if isinstance(value, str) else value
    return str(value)[:160]


def _safe_envelope_value(value: Any, *, depth: int = 0) -> Any:
    """Sanitize an existing projected envelope without re-projecting it."""

    if depth >= 6:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _safe_envelope_value(item, depth=depth + 1)
            for key, item in list(value.items())[:64]
            if str(key).strip().lower().replace("-", "_") not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_envelope_value(item, depth=depth + 1) for item in list(value)[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:1000] if isinstance(value, str) else value
    return str(value)[:240]


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    return list(value)


def _strings(value: Any, limit: int) -> list[str]:
    values = [value] if isinstance(value, str) else _sequence(value)
    result = []
    for item in values[:limit]:
        text = _text(item, 160)
        if text and text not in result:
            result.append(text)
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _positive_limit(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PlannerEnvelopeError(name + " must be positive") from exc
    if result <= 0:
        raise PlannerEnvelopeError(name + " must be positive")
    return result


def _assert_budget(value: Mapping[str, Any], limit: int) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > limit:
        raise PlannerEnvelopeError(
            "planner envelope exceeds max_bytes", code="planner_envelope_too_large"
        )


__all__ = [
    "PLANNER_EXECUTION_IDENTITY_SCHEMA_VERSION",
    "PLANNER_ENVELOPE_DEFAULT_STAGE",
    "PLANNER_ENVELOPE_LAYERS",
    "PLANNER_ENVELOPE_MAX_BYTES",
    "PLANNER_ENVELOPE_SCHEMA_VERSION",
    "PLANNER_PROJECTION_STAGES",
    "PlannerEnvelopeError",
    "build_planner_envelope",
    "build_execution_planner_envelope",
    "normalize_projection_stage",
    "normalize_planner_envelope",
    "project_planner_envelope_evidence",
]
