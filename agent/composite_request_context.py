"""Bounded, domain-neutral context for open Composite requests.

The builder coordinates existing Domain Pack seams only: request-facts
extraction, capability discovery, workflow selection, and the public catalog
projection.  It does not choose a tool, execute a component, or interpret
domain-specific fields in the shared Runtime.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.capability_catalog import project_clarification_requirements
from agent.domain_contract import (
    discovery_context,
    extract_request_facts,
    select_workflow,
)
from agent.request_model import RequestFacts
from agent.runtime_core.analysis_discovery import (
    AnalysisDiscoveryError,
    AnalysisDiscoveryGateway,
    discovery_request_fingerprint,
)
from agent.runtime_core.planner_envelope import (
    PLANNER_ENVELOPE_MAX_BYTES,
    PlannerEnvelopeError,
    build_planner_envelope,
)


COMPOSITE_REQUEST_CONTEXT_SCHEMA_VERSION = "spatial-agent.composite-request-context.v2"
_MAX_DOMAINS = 8
_MAX_CANDIDATES = 16
_MAX_FIELDS = 8
# Tool and result allowlists are execution-boundary data.  Truncating them
# below the public bridge limit can turn a valid workflow into a false
# ``not allowlisted`` failure, so keep the same bounded capacity as the
# TaskPlan bridge instead of using the smaller display-list limit.
_MAX_TOOLS = 24
_MAX_RESULT_TYPES = 24
# A multi-Domain planner needs the bounded candidate catalog, discovery
# receipt, and per-domain fact handoff in one context.  Keep the projection
# finite while leaving enough room for the supported GIS + Economic pair.
_MAX_BYTES = PLANNER_ENVELOPE_MAX_BYTES
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


class CompositeRequestContextError(ValueError):
    """A request context cannot be projected within the public contract."""

    def __init__(self, message: str, *, code: str = "request_context_invalid") -> None:
        super().__init__(message)
        self.code = code


class CompositeRequestContextBuilder:
    """Build one bounded context from the enabled Domain Packs."""

    def __init__(
        self,
        *,
        host: Any,
        catalog_projector: Any,
        max_domains: int = _MAX_DOMAINS,
        max_candidates: int = _MAX_CANDIDATES,
        max_bytes: int = _MAX_BYTES,
        discovery_gateway: Any = None,
    ) -> None:
        if host is None or not callable(getattr(host, "catalog", None)):
            raise ValueError("host must expose catalog()")
        if catalog_projector is None or not callable(
            getattr(catalog_projector, "project", None)
        ):
            raise ValueError("catalog_projector must expose project()")
        self._host = host
        self._catalog_projector = catalog_projector
        self._max_domains = _positive_limit(max_domains, "max_domains")
        self._max_candidates = _positive_limit(max_candidates, "max_candidates")
        self._max_bytes = _positive_limit(max_bytes, "max_bytes")
        self._discovery_gateway = discovery_gateway or AnalysisDiscoveryGateway(
            max_domains=self._max_domains,
            max_candidates=self._max_candidates,
            max_bytes=max_bytes,
        )
        if not callable(getattr(self._discovery_gateway, "discover", None)):
            raise ValueError("discovery_gateway must expose discover()")

    def build(
        self,
        request: str,
        *,
        planner: str = "rule",
        backend: str = "memory",
        domain_ids: Sequence[str] | None = None,
        fact_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = str(request or "").strip()[:2000]
        if not text:
            raise CompositeRequestContextError(
                "request must be a non-empty string", code="request_required"
            )

        catalog = self._catalog_projector.project(
            planner=planner,
            backend=backend,
            domain_ids=domain_ids,
        )
        if not isinstance(catalog, Mapping):
            raise CompositeRequestContextError(
                "planner catalog projection is invalid", code="catalog_invalid"
            )
        selected_ids = _selected_domain_ids(catalog, domain_ids, self._max_domains)
        catalog_domains = {
            str(item.get("domain_id")): item
            for item in (catalog.get("domains") or [])
            if isinstance(item, Mapping) and item.get("domain_id")
        }
        domain_contexts: list[dict[str, Any]] = []
        candidate_index: list[dict[str, Any]] = []
        missing_by_domain: list[dict[str, Any]] = []

        for domain_id in selected_ids:
            domain_catalog = catalog_domains.get(domain_id, {})
            service = self._host.service(self._host.select(domain_id, source="automatic"))
            try:
                facts = extract_request_facts(service, text)
                facts = _merge_fact_override(
                    facts,
                    fact_overrides.get(domain_id)
                    if isinstance(fact_overrides, Mapping)
                    else None,
                )
                safe_facts = _facts_projection(facts)
            except Exception as exc:
                raise CompositeRequestContextError(
                    "domain request facts are unavailable",
                    code="facts_extraction_failed",
                ) from exc
            discovery_state, discovery = _discover(service, text, facts, domain_id)
            candidate_ids = _candidate_ids(discovery)
            definitions = _catalog_capabilities(domain_catalog)
            # A missing discovery selection is allowed to expose the bounded
            # catalog to a Planner.  An explicit, but unknown, discovery ID
            # remains present and therefore stays fail-closed below.
            if not candidate_ids:
                candidate_ids = [str(item.get("id")) for item in definitions if item.get("id")]
            requirements = project_clarification_requirements(
                _requirement_candidate_ids(discovery, candidate_ids),
                safe_facts,
                capability_definitions=definitions,
                max_fields=_MAX_FIELDS,
            )
            workflow_state, workflow = _workflow_selection(
                service, discovery, facts, domain_id
            )
            safe_candidates = _candidate_projection(
                definitions, candidate_ids, domain_id=domain_id
            )
            domain_context = {
                "domain_id": domain_id,
                "facts": safe_facts,
                "discovery": {
                    "state": discovery_state,
                    **_safe_discovery(discovery, domain_id),
                },
                "capability_candidates": safe_candidates,
                "workflow": {
                    "state": workflow_state,
                    **_safe_workflow(workflow),
                },
                "clarification": requirements,
                "data_readiness": _safe_value(
                    domain_catalog.get("data_readiness") or {}, depth=0
                ),
            }
            domain_contexts.append(domain_context)
            candidate_index.extend(
                {**item, "domain_id": domain_id} for item in safe_candidates
            )
            if requirements.get("missing_fields"):
                missing_by_domain.append(
                    {
                        "domain_id": domain_id,
                        "fields": requirements["missing_fields"][:_MAX_FIELDS],
                    }
                )

        candidate_index = _unique_candidates(candidate_index, self._max_candidates)
        request_fingerprint = _fingerprint(text, selected_ids, planner, backend)
        try:
            discovery_receipt = self._discovery_gateway.discover(
                text,
                planner=planner,
                backend=backend,
                domain_ids=selected_ids,
                domain_contexts=domain_contexts,
                candidate_index=candidate_index,
                missing_by_domain=missing_by_domain,
                catalog_consistency=catalog.get("catalog_consistency") or {},
                request_fingerprint=request_fingerprint,
            )
        except AnalysisDiscoveryError as exc:
            raise CompositeRequestContextError(
                "analysis discovery receipt is invalid",
                code=(
                    "context_budget_exceeded"
                    if exc.code == "discovery_budget_exceeded"
                    else exc.code
                ),
            ) from exc
        clarification = discovery_receipt.get("clarification") or _clarification_projection(
            domain_contexts, missing_by_domain, candidate_index
        )
        context = {
            "schema_version": COMPOSITE_REQUEST_CONTEXT_SCHEMA_VERSION,
            "planner": _text(planner, 32),
            "backend": _text(backend, 32),
            "request_fingerprint": request_fingerprint,
            "request_summary": text[:320],
            "domain_ids": selected_ids,
            "domain_contexts": domain_contexts,
            "capability_index": candidate_index,
            "workflow_index": _workflow_index_projection(
                catalog.get("workflow_index"), selected_ids
            ),
            "discovery": discovery_receipt,
            "clarification": clarification,
            "catalog_consistency": _safe_value(
                catalog.get("catalog_consistency") or {}, depth=0
            ),
            "evidence": {
                "schema_version": "spatial-agent.composite-request-context-evidence.v1",
                "sources": [
                    "domain_facts",
                    "capability_catalog",
                    "catalog_consistency",
                    "discovery",
                ],
                "domain_count": len(domain_contexts),
                "candidate_count": len(candidate_index),
                "discovery_fingerprint": discovery_receipt.get(
                    "discovery_fingerprint"
                ),
            },
            "limits": {
                "max_domains": self._max_domains,
                "max_candidates": self._max_candidates,
                "max_bytes": self._max_bytes,
            },
        }
        try:
            context["planner_envelope"] = build_planner_envelope(
                context, max_bytes=self._max_bytes
            )
        except PlannerEnvelopeError as exc:
            raise CompositeRequestContextError(
                "planner envelope is invalid",
                code=(
                    "context_budget_exceeded"
                    if exc.code == "planner_envelope_too_large"
                    else exc.code
                ),
            ) from exc
        _assert_budget(context, self._max_bytes)
        return context


def _selected_domain_ids(
    catalog: Mapping[str, Any], requested: Sequence[str] | None, limit: int
) -> list[str]:
    available = [
        str(value)
        for value in (catalog.get("domain_ids") or [])
        if str(value).strip()
    ]
    if requested is None:
        return available[:limit]
    allowed = set(available)
    selected: list[str] = []
    for value in requested:
        domain_id = str(value or "").strip()
        if not domain_id or domain_id not in allowed or domain_id in selected:
            continue
        selected.append(domain_id)
    return selected[:limit]


def _discover(service: Any, request: str, facts: Any, domain_id: str) -> tuple[str, dict[str, Any]]:
    method = getattr(service, "discover", None)
    if not callable(method):
        return "not_declared", {"domain_id": domain_id, "reason_code": "discover_not_declared"}
    try:
        return "available", discovery_context(method(request, facts), domain_id=domain_id)
    except Exception:
        return "unavailable", {"domain_id": domain_id, "reason_code": "discover_failed"}


def _workflow_selection(
    service: Any, discovery: Mapping[str, Any], facts: Any, domain_id: str
) -> tuple[str, dict[str, Any]]:
    method = getattr(service, "select_workflow", None)
    if not callable(method):
        return "unavailable", {"domain_id": domain_id, "reason_code": "workflow_unavailable"}
    try:
        return "available", _safe_workflow(select_workflow(service, discovery, facts))
    except Exception:
        return "unavailable", {"domain_id": domain_id, "reason_code": "workflow_failed"}


def _facts_projection(facts: Any) -> dict[str, Any]:
    source: Mapping[str, Any] = {}
    for name in ("as_context_dict", "as_dict"):
        method = getattr(facts, name, None)
        value = method() if callable(method) else None
        if isinstance(value, Mapping):
            source = value
            break
    if not source and isinstance(facts, Mapping):
        source = facts
    return {
        "schema_version": _text(source.get("schema_version"), 96),
        "admin_name": _text(source.get("admin_name"), 120) or None,
        "entities": _safe_value(source.get("entities") or {}, depth=0),
        "tasks": _safe_strings(source.get("tasks"), 8),
        "datasets": _safe_strings(source.get("datasets"), 16),
        "constraints": _safe_value(source.get("constraints") or {}, depth=0),
        "evidence": _safe_strings(source.get("evidence"), 8),
    }


def _merge_fact_override(facts: Any, override: Any) -> Any:
    """Merge already validated continuation facts before Domain discovery."""

    if not isinstance(override, Mapping):
        return facts
    base = _facts_projection(facts)
    entities = dict(base.get("entities") or {})
    entities.update(
        _safe_value(override.get("entities") or {}, depth=0)
        if isinstance(override.get("entities"), Mapping)
        else {}
    )
    datasets = list(base.get("datasets") or [])
    for value in _safe_strings(override.get("datasets"), 16):
        if value not in datasets:
            datasets.append(value)
    constraints = dict(base.get("constraints") or {})
    if isinstance(override.get("constraints"), Mapping):
        constraints.update(_safe_value(override["constraints"], depth=0))
    evidence = list(base.get("evidence") or [])
    if "user_supplement" not in evidence:
        evidence.append("user_supplement")
    return RequestFacts(
        text=str(base.get("text") or "")[:2000],
        admin_name=str(entities.get("admin_name") or "").strip() or None,
        tasks=tuple(base.get("tasks") or ()),
        datasets=tuple(datasets[:24]),
        constraints=constraints,
        evidence=tuple(evidence[:16]),
        entities=entities,
    )


def _catalog_capabilities(domain: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in (domain.get("capabilities") or [])
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    ]


def _candidate_ids(discovery: Mapping[str, Any]) -> list[str]:
    values = []
    selected = discovery.get("selected_capability_id")
    if selected:
        values.append(selected)
    values.extend(discovery.get("candidate_ids") or [])
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result[:_MAX_CANDIDATES]


def _requirement_candidate_ids(
    discovery: Mapping[str, Any], candidate_ids: Sequence[str]
) -> list[str]:
    """Use only an authoritative candidate when projecting missing facts.

    For an ambiguous discovery result, unioning every candidate's required
    fields would ask for facts that may be irrelevant to the eventual plan.
    Leave that choice to the Planner; a single candidate can still provide a
    useful, domain-declared clarification.
    """
    selected = str(discovery.get("selected_capability_id") or "").strip()
    if selected:
        return [selected]
    bounded = [str(value).strip() for value in candidate_ids if str(value).strip()]
    return bounded[:1] if len(bounded) == 1 else []


def _candidate_projection(
    definitions: Sequence[Mapping[str, Any]],
    candidate_ids: Sequence[str],
    *,
    domain_id: str,
) -> list[dict[str, Any]]:
    by_id = {str(item.get("id")): item for item in definitions}
    result = []
    for capability_id in candidate_ids:
        item = by_id.get(str(capability_id))
        if not item:
            continue
        safe_domain_id = _text(domain_id, 32)
        safe_capability_id = str(item.get("id"))[:96]
        result.append(
            {
                "domain_id": safe_domain_id,
                "capability_id": safe_capability_id,
                "selection_key": f"{safe_domain_id}::{safe_capability_id}"[:140],
                "label": _text(item.get("label"), 160),
                "description": _text(item.get("description"), 320),
                "available": bool(item.get("available")),
                "availability_mode": _text(item.get("availability_mode"), 24),
                "availability_reason": _text(item.get("availability_reason"), 160),
                "dataset_gate": _text(item.get("dataset_gate"), 24),
                "capability_status": _text(item.get("capability_status"), 32),
                "missing_datasets": _safe_strings(item.get("missing_datasets"), 8),
                "datasets": _safe_strings(item.get("datasets"), 8),
                "tools": _safe_strings(item.get("tools"), _MAX_TOOLS),
                "result_types": _safe_strings(
                    item.get("result_types"), _MAX_RESULT_TYPES
                ),
                "output_profiles": _safe_profiles(item.get("output_profiles")),
                "workflow_ids": _safe_strings(item.get("workflow_ids"), 16),
                "plan_mode": _text(item.get("plan_mode"), 24) or None,
                "request_requirements": _safe_requirements(
                    item.get("request_requirements")
                ),
            }
        )
        if "execution_readiness" in item:
            result[-1]["execution_readiness"] = _text(
                item.get("execution_readiness"), 32
            )
            result[-1]["execution_ready"] = bool(item.get("execution_ready"))
            result[-1]["execution_reason_code"] = _text(
                item.get("execution_reason_code"), 96
            )
            for key in ("missing_tools", "missing_result_types"):
                if item.get(key):
                    result[-1][key] = _safe_strings(item.get(key), 8)
    return result[:_MAX_CANDIDATES]


def _safe_profiles(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for raw in list(value)[:_MAX_RESULT_TYPES]:
        if not isinstance(raw, Mapping):
            continue
        result_type = _text(raw.get("result_type"), 96)
        kinds = _safe_strings(raw.get("kinds"), 8)
        if not result_type or not kinds:
            continue
        result.append(
            {
                "result_type": result_type,
                "schema_version": _text(raw.get("schema_version"), 96),
                "primary": _text(raw.get("primary"), 32) or kinds[0],
                "kinds": kinds,
            }
        )
    return result


def _workflow_index_projection(
    value: Any, selected_domain_ids: Sequence[str]
) -> list[dict[str, Any]]:
    """Carry the bounded registered workflow index into planner context."""

    allowed_domains = {str(item) for item in selected_domain_ids}
    result: list[dict[str, Any]] = []
    for raw in value if isinstance(value, Sequence) and not isinstance(value, str) else ():
        if not isinstance(raw, Mapping):
            continue
        domain_id = _text(raw.get("domain_id"), 64)
        workflow_id = _text(raw.get("workflow_id") or raw.get("id"), 96)
        if not domain_id or domain_id not in allowed_domains or not workflow_id:
            continue
        result.append(
            {
                "domain_id": domain_id,
                "workflow_id": workflow_id,
                "label": _text(raw.get("label"), 160),
                "allowed_tools": _safe_strings(raw.get("allowed_tools"), 24),
                "result_types": _safe_strings(raw.get("result_types"), 16),
            }
        )
        if len(result) >= _MAX_CANDIDATES * 2:
            break
    return result


def _unique_candidates(values: Sequence[Mapping[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Deduplicate while keeping a bounded candidate share for each Domain.

    A simple first-N slice lets an early Domain exhaust the global context
    budget and silently hides every later Domain from an open Composite
    Planner.  Round-robin projection keeps single-Domain ordering unchanged
    while ensuring multi-Domain planning retains at least one candidate from
    each selected Domain (subject to the global limit).
    """

    groups: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    order: list[str] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        identity = (str(value.get("domain_id")), str(value.get("capability_id")))
        if identity in seen:
            continue
        seen.add(identity)
        domain_id = identity[0]
        if domain_id not in groups:
            groups[domain_id] = []
            order.append(domain_id)
        groups[domain_id].append(dict(value))

    result: list[dict[str, Any]] = []
    depth = 0
    while len(result) < limit:
        added = False
        for domain_id in order:
            candidates = groups[domain_id]
            if depth >= len(candidates):
                continue
            result.append(candidates[depth])
            added = True
            if len(result) >= limit:
                break
        if not added:
            break
        depth += 1
    return result


def _clarification_projection(
    domains: Sequence[Mapping[str, Any]],
    missing: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if missing:
        fields = [
            {"domain_id": item["domain_id"], "fields": item["fields"]}
            for item in missing[:_MAX_DOMAINS]
        ]
        return {
            "state": "required",
            "reason_code": "request_facts_missing",
            "missing_by_domain": fields,
            "message": "请补充分析范围、指标、时间或其他必要条件。",
        }
    if not candidates:
        return {
            "state": "ambiguous",
            "reason_code": "no_capability_match",
            "missing_by_domain": [],
            "message": "当前能力目录没有找到明确匹配，请说明希望分析的对象或结果类型。",
        }
    available = [item for item in candidates if item.get("available") is not False]
    if not available:
        return {
            "state": "unavailable",
            "reason_code": "capability_unavailable",
            "missing_by_domain": [],
            "message": "匹配到的能力当前不可用，请检查数据就绪状态或稍后重试。",
        }
    states = [str((item.get("discovery") or {}).get("state")) for item in domains]
    if any(state == "unavailable" for state in states):
        return {
            "state": "unavailable",
            "reason_code": "discovery_unavailable",
            "missing_by_domain": [],
            "message": "能力发现暂不可用，请稍后重试。",
        }
    return {
        "state": "not_required",
        "reason_code": "facts_and_candidates_available",
        "missing_by_domain": [],
        "message": "已形成可供 Planner 选择的能力上下文。",
    }


def _safe_discovery(value: Mapping[str, Any], domain_id: str) -> dict[str, Any]:
    allowed = (
        "schema_version",
        "selected_capability_id",
        "candidate_ids",
        "candidate_count",
        "selection_state",
        "reason_code",
        "domain_id",
    )
    result = {key: _safe_value(value.get(key), depth=0) for key in allowed if key in value}
    result["domain_id"] = domain_id
    result["candidate_ids"] = _safe_strings(result.get("candidate_ids"), 8)
    return result


def _safe_workflow(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source",
        "selected_by",
        "selected_capability_id",
        "candidate_ids",
        "candidate_count",
        "workflow_template_id",
        "workflow_template_version",
        "missing_fields",
        "constraints",
    )
    result = {key: _safe_value(value.get(key), depth=0) for key in allowed if key in value}
    result["candidate_ids"] = _safe_strings(result.get("candidate_ids"), 8)
    result["missing_fields"] = _safe_strings(result.get("missing_fields"), _MAX_FIELDS)
    return result


def _safe_requirements(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    fields: list[dict[str, Any]] = []
    for raw in (source.get("clarification_fields") or [])[:_MAX_FIELDS]:
        if not isinstance(raw, Mapping):
            continue
        field_id = _text(raw.get("id"), 80)
        kind = _text(raw.get("kind"), 32)
        label = _text(raw.get("label"), 120)
        if not field_id or not label or kind not in {"entity", "dataset", "constraint"}:
            continue
        field = {
            "id": field_id,
            "label": label,
            "kind": kind,
            "required": bool(raw.get("required", True)),
            "source": "catalog",
            "mode": _text(raw.get("mode"), 8)
            if str(raw.get("mode") or "") in {"any", "all"}
            else "any",
        }
        key = raw.get("key") or raw.get("fact")
        if key:
            field["key"] = _text(key, 80)
        keys = _safe_strings(raw.get("keys"), _MAX_FIELDS)
        values = _safe_strings(raw.get("values"), _MAX_FIELDS)
        if keys:
            field["keys"] = keys
        if values:
            field["values"] = values
        fields.append(field)
    return {
        "schema_version": _text(source.get("schema_version"), 96),
        "entities": _safe_strings(source.get("entities"), 16),
        "datasets": _safe_strings(source.get("datasets"), 16),
        "constraints": _safe_strings(source.get("constraints"), 16),
        "clarification_fields": fields,
    }


def _safe_value(value: Any, *, depth: int) -> Any:
    if depth >= 4:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _safe_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
            if not _is_private_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:64]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:640] if isinstance(value, str) else value
    return str(value)[:160]


def _safe_strings(value: Any, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    return [_text(item, 160) for item in list(value)[:limit] if _text(item, 160)]


def _fingerprint(text: str, domains: Sequence[str], planner: str, backend: str) -> str:
    return discovery_request_fingerprint(text, domains, planner, backend)


def _assert_budget(value: Mapping[str, Any], limit: int) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > limit:
        raise CompositeRequestContextError(
            "composite request context exceeds max_bytes", code="context_budget_exceeded"
        )


def _positive_limit(value: int, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(name + " must be positive") from exc
    if result <= 0:
        raise ValueError(name + " must be positive")
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _is_private_key(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized in _PRIVATE_KEYS or normalized.endswith("_path") or normalized.endswith("_token")


__all__ = [
    "COMPOSITE_REQUEST_CONTEXT_SCHEMA_VERSION",
    "CompositeRequestContextBuilder",
    "CompositeRequestContextError",
]
