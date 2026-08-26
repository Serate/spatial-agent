"""Bounded discovery receipt for open, cross-domain analysis requests.

This module owns the public *discovery* boundary, not Domain policy.  Domain
Packs still extract facts, match their declared capabilities and report
readiness.  The gateway only combines those projections into one versioned
receipt that a Planner, continuation, Result and UI can safely reference.

Discovery is advisory and never authorizes execution.  A candidate must still
be materialized as a valid TaskPlan and pass the canonical execution-binding
gate before a run can be created.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


ANALYSIS_DISCOVERY_SCHEMA_VERSION = "spatial-agent.analysis-discovery.v1"
ANALYSIS_DISCOVERY_EVIDENCE_SCHEMA_VERSION = (
    "spatial-agent.analysis-discovery-evidence.v1"
)
_MAX_DOMAINS = 8
_MAX_CANDIDATES = 16
_MAX_DATA_REQUIREMENTS = 64
_MAX_FIELDS = 8
_MAX_BYTES = 64_000
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
_READY_STATUSES = {"ready", "external_source_bound", "not_applicable"}
_UNAVAILABLE_STATUSES = {"unavailable", "not_ready"}


class AnalysisDiscoveryError(ValueError):
    """A discovery receipt cannot be projected within the public contract."""

    def __init__(self, message: str, *, code: str = "discovery_invalid") -> None:
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


class AnalysisDiscoveryGateway:
    """Aggregate already-declared Domain observations into one safe receipt.

    ``domain_contexts`` and ``candidate_index`` are intentionally plain
    mappings.  This keeps the seam usable by Rule, Replay and LLM planners and
    prevents this public module from importing GIS or Economic code.
    """

    def __init__(
        self,
        *,
        max_domains: int = _MAX_DOMAINS,
        max_candidates: int = _MAX_CANDIDATES,
        max_data_requirements: int = _MAX_DATA_REQUIREMENTS,
        max_fields: int = _MAX_FIELDS,
        max_bytes: int = _MAX_BYTES,
    ) -> None:
        self._max_domains = _positive_limit(max_domains, "max_domains")
        self._max_candidates = _positive_limit(max_candidates, "max_candidates")
        self._max_data_requirements = _positive_limit(
            max_data_requirements, "max_data_requirements"
        )
        self._max_fields = _positive_limit(max_fields, "max_fields")
        self._max_bytes = _positive_limit(max_bytes, "max_bytes")

    def discover(
        self,
        request: str,
        *,
        planner: str,
        backend: str,
        domain_ids: Sequence[str],
        domain_contexts: Sequence[Mapping[str, Any]],
        candidate_index: Sequence[Mapping[str, Any]],
        missing_by_domain: Sequence[Mapping[str, Any]] = (),
        catalog_consistency: Mapping[str, Any] | None = None,
        request_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        """Build one bounded receipt without retaining the original prompt."""

        text = str(request or "").strip()[:2000]
        if not text:
            raise AnalysisDiscoveryError("request is required", code="request_required")
        domains = _domain_ids(domain_ids, self._max_domains)
        contexts = _domain_projections(domain_contexts, domains, self._max_domains)
        candidates = _candidate_projections(
            candidate_index, self._max_candidates
        )
        missing = _missing_projections(
            missing_by_domain,
            contexts,
            max_domains=self._max_domains,
            max_fields=self._max_fields,
        )
        readiness_by_domain = {
            str(item.get("domain_id")): item.get("data_readiness") or {}
            for item in contexts
        }
        data_requirements = _data_requirements(
            candidates,
            readiness_by_domain,
            max_items=self._max_data_requirements,
        )
        candidates = [
            _with_candidate_state(item, data_requirements)
            for item in candidates
        ]
        state, reason_code = _state(
            contexts,
            candidates,
            missing,
        )
        clarification = _clarification(
            state,
            reason_code,
            missing,
            candidates,
            contexts,
        )
        fingerprint = str(request_fingerprint or "").strip()[:128]
        if not fingerprint:
            fingerprint = discovery_request_fingerprint(
                text, domains, planner, backend
            )
        receipt: dict[str, Any] = {
            "schema_version": ANALYSIS_DISCOVERY_SCHEMA_VERSION,
            "request_fingerprint": fingerprint,
            "discovery_fingerprint": "",
            "planner": _text(planner, 32),
            "backend": _text(backend, 32),
            "state": state,
            "reason_code": reason_code,
            "domain_ids": domains,
            "domains": contexts,
            "candidates": candidates,
            "data_requirements": data_requirements,
            "missing_facts": missing,
            "clarification": clarification,
            "next_actions": _next_actions(state, reason_code),
            "evidence": {
                "schema_version": ANALYSIS_DISCOVERY_EVIDENCE_SCHEMA_VERSION,
                "sources": [
                    "request_facts",
                    "domain_discovery",
                    "capability_catalog",
                    "workflow_catalog",
                    "data_readiness",
                ],
                "catalog_consistency": _catalog_summary(catalog_consistency),
                "domain_count": len(contexts),
                "candidate_count": len(candidates),
                "data_requirement_count": len(data_requirements),
            },
            "limits": {
                "max_domains": self._max_domains,
                "max_candidates": self._max_candidates,
                "max_data_requirements": self._max_data_requirements,
                "max_fields": self._max_fields,
                "max_bytes": self._max_bytes,
            },
        }
        receipt["discovery_fingerprint"] = _receipt_fingerprint(receipt)
        _assert_budget(receipt, self._max_bytes)
        return receipt


def discovery_request_fingerprint(
    request: str,
    domains: Sequence[str],
    planner: str,
    backend: str,
) -> str:
    """Return the canonical request identity shared by context and receipt."""

    encoded = json.dumps(
        {
            "request": str(request or "").strip()[:2000],
            "domains": [str(item)[:64] for item in domains[:_MAX_DOMAINS]],
            "planner": _text(planner, 32),
            "backend": _text(backend, 32),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _domain_projections(
    values: Sequence[Mapping[str, Any]],
    domain_ids: Sequence[str],
    limit: int,
) -> list[dict[str, Any]]:
    by_id = {
        str(item.get("domain_id")): item
        for item in values
        if isinstance(item, Mapping) and str(item.get("domain_id") or "").strip()
    }
    result: list[dict[str, Any]] = []
    for domain_id in domain_ids[:limit]:
        source = by_id.get(domain_id)
        if source is None:
            raise AnalysisDiscoveryError(
                "domain context is missing", code="discovery_domain_missing"
            )
        discovery = source.get("discovery")
        workflow = source.get("workflow")
        readiness = source.get("data_readiness")
        clarification = source.get("clarification")
        clarification_fields = (
            clarification.get("missing_fields")
            if isinstance(clarification, Mapping)
            else None
        )
        # Some older Domain Packs expose missing public facts through workflow
        # selection rather than the capability-requirements projection.  Both
        # are declarations, so the gateway may merge them without knowing
        # their domain vocabulary.
        if not clarification_fields and isinstance(workflow, Mapping):
            clarification_fields = _workflow_missing_fields(
                source, workflow.get("missing_fields")
            )
        result.append(
            {
                "domain_id": domain_id,
                "fact_schema_version": _text(
                    (source.get("facts") or {}).get("schema_version")
                    if isinstance(source.get("facts"), Mapping)
                    else None,
                    96,
                ),
                "discovery": _discovery_summary(discovery, domain_id),
                "workflow": _workflow_summary(workflow),
                "data_readiness": _readiness(readiness),
                "candidate_ids": _strings(
                    (discovery or {}).get("candidate_ids")
                    if isinstance(discovery, Mapping)
                    else None,
                    16,
                ),
                "missing_fields": _fields(
                    clarification_fields,
                    8,
                ),
            }
        )
    return result


def _candidate_projections(
    values: Sequence[Mapping[str, Any]], limit: int
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in values:
        if not isinstance(raw, Mapping):
            raise AnalysisDiscoveryError(
                "candidate is not an object", code="discovery_candidate_invalid"
            )
        domain_id = _text(raw.get("domain_id"), 64)
        capability_id = _text(raw.get("capability_id"), 96)
        if not domain_id or not capability_id:
            raise AnalysisDiscoveryError(
                "candidate identity is incomplete", code="discovery_candidate_invalid"
            )
        identity = (domain_id, capability_id)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(
            {
                "domain_id": domain_id,
                "capability_id": capability_id,
                "selection_key": _text(raw.get("selection_key"), 140)
                or f"{domain_id}::{capability_id}"[:140],
                "label": _text(raw.get("label"), 160),
                "description": _text(raw.get("description"), 320),
                "available": bool(raw.get("available")),
                "availability_reason": _text(raw.get("availability_reason"), 160),
                "datasets": _strings(raw.get("datasets"), 8),
                "missing_datasets": _strings(raw.get("missing_datasets"), 8),
                "tools": _strings(raw.get("tools"), 8),
                "result_types": _strings(raw.get("result_types"), 8),
                "workflow_ids": _strings(raw.get("workflow_ids"), 8),
                "plan_mode": _text(raw.get("plan_mode"), 24) or None,
                "execution_readiness": _text(
                    raw.get("execution_readiness"), 32
                ) or None,
                "execution_ready": (
                    bool(raw.get("execution_ready"))
                    if "execution_ready" in raw
                    else None
                ),
                "execution_reason_code": _text(
                    raw.get("execution_reason_code"), 96
                ) or None,
                "missing_tools": _strings(raw.get("missing_tools"), 8),
                "missing_result_types": _strings(
                    raw.get("missing_result_types"), 8
                ),
                "required_fact_ids": _requirement_ids(
                    raw.get("request_requirements")
                ),
            }
        )
        if len(result) >= limit:
            break
    return result


def _with_candidate_state(
    candidate: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result = dict(candidate)
    identity = (
        str(candidate.get("domain_id")),
        str(candidate.get("capability_id")),
    )
    related = [
        item
        for item in requirements
        if (str(item.get("domain_id")), str(item.get("capability_id"))) == identity
    ]
    if not bool(candidate.get("available")):
        state = "data_unavailable" if (
            candidate.get("missing_datasets")
            or _data_reason(candidate.get("availability_reason"))
        ) else "capability_unavailable"
        execution_ready = False
    elif str(candidate.get("execution_readiness") or "") in {
        "workflow_unbound",
        "schema_invalid",
    }:
        state = str(candidate.get("execution_readiness"))
        execution_ready = False
    elif str(candidate.get("plan_mode") or "") == "unbound":
        state = "workflow_unbound"
        execution_ready = False
    else:
        unavailable = any(
            str(item.get("status")) in {"missing", "unavailable"}
            for item in related
        )
        unknown = any(str(item.get("status")) == "unknown" for item in related)
        if unavailable:
            state = "data_unavailable"
            execution_ready = False
            result["execution_readiness"] = "data_unavailable"
            result["execution_reason_code"] = "data_readiness_unavailable"
        elif unknown:
            # Unknown is not proof of usable data.  Keep the candidate visible
            # for recovery/diagnostics, but never let it cross the execution
            # gate as if its data had been checked.
            state = "data_unavailable"
            execution_ready = False
            result["execution_readiness"] = "data_unavailable"
            result["execution_reason_code"] = "data_readiness_unknown"
        else:
            state = "available"
            execution_ready = not unavailable
    result["state"] = state
    result["execution_ready"] = execution_ready
    result["data_requirement_ids"] = [
        _text(item.get("requirement_id"), 140) for item in related
    ][:8]
    return result


def _data_requirements(
    candidates: Sequence[Mapping[str, Any]],
    readiness_by_domain: Mapping[str, Any],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        domain_id = str(candidate.get("domain_id"))
        capability_id = str(candidate.get("capability_id"))
        missing = set(candidate.get("missing_datasets") or ())
        readiness = readiness_by_domain.get(domain_id) or {}
        readiness_status = _readiness_status(readiness)
        for dataset in candidate.get("datasets") or ():
            dataset_id = _text(dataset, 96)
            if not dataset_id:
                continue
            identity = (domain_id, capability_id, dataset_id)
            if identity in seen:
                continue
            seen.add(identity)
            if dataset_id in missing:
                status, reason = "missing", "required_data_missing"
            elif readiness_status in _UNAVAILABLE_STATUSES:
                status, reason = "unavailable", "data_readiness_unavailable"
            elif readiness_status in {"degraded", "partial"}:
                status, reason = "degraded", "data_readiness_degraded"
            elif readiness_status in _READY_STATUSES:
                status, reason = "ready", "data_readiness_ready"
            else:
                status, reason = "unknown", "data_readiness_unknown"
            requirement_id = f"{domain_id}::{capability_id}::{dataset_id}"[:140]
            result.append(
                {
                    "requirement_id": requirement_id,
                    "domain_id": domain_id,
                    "capability_id": capability_id,
                    "dataset": dataset_id,
                    "required": True,
                    "status": status,
                    "reason_code": reason,
                    "readiness": _readiness(readiness),
                }
            )
            if len(result) >= max_items:
                return result
    return result


def _state(
    contexts: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    missing: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    if missing:
        return "needs_facts", "needs_facts"
    if not candidates:
        return "capability_unavailable", "capability_unavailable"
    discovery_states = {
        str((item.get("discovery") or {}).get("state") or "")
        for item in contexts
    }
    if any(value in {"unavailable", "not_declared"} for value in discovery_states):
        return "data_unavailable", "data_unavailable"
    if any(item.get("execution_ready") for item in candidates):
        return "ready", "discovery_ready"
    if any(item.get("state") == "data_unavailable" for item in candidates):
        return "data_unavailable", "data_unavailable"
    if any(item.get("state") == "schema_invalid" for item in candidates):
        return "capability_unavailable", "schema_invalid"
    if any(item.get("state") == "workflow_unbound" for item in candidates):
        return "capability_unavailable", "workflow_unbound"
    return "capability_unavailable", "capability_unavailable"


def _clarification(
    state: str,
    reason_code: str,
    missing: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    contexts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if missing:
        return {
            "state": "required",
            "reason_code": "request_facts_missing",
            "missing_by_domain": list(missing),
            "message": "请补充分析范围、指标、时间或其他必要条件。",
        }
    if not candidates:
        return {
            "state": "ambiguous",
            "reason_code": "no_capability_match",
            "missing_by_domain": [],
            "message": "当前能力目录没有找到明确匹配，请说明希望分析的对象或结果类型。",
        }
    if state == "data_unavailable":
        domain_unavailable = any(
            str((item.get("discovery") or {}).get("state") or "")
            in {"unavailable", "not_declared"}
            for item in contexts
        )
        return {
            "state": "unavailable",
            "reason_code": "discovery_unavailable" if domain_unavailable else "data_unavailable",
            "missing_by_domain": [],
            "message": "匹配到能力，但所需数据或后端当前不可用，请检查就绪状态后重试。",
        }
    if state == "capability_unavailable":
        return {
            "state": "unavailable",
            "reason_code": reason_code or "capability_unavailable",
            "missing_by_domain": [],
            "message": (
                "匹配到能力，但工作流或工具契约尚未闭合，请稍后重试。"
                if reason_code in {"workflow_unbound", "schema_invalid"}
                else "匹配到的能力当前没有可执行工作流，请选择其他能力或补充条件。"
            ),
        }
    return {
        "state": "not_required",
        "reason_code": "facts_and_candidates_available",
        "missing_by_domain": [],
        "message": "已形成可供 Planner 选择的能力与数据上下文。",
    }


def _discovery_summary(value: Any, domain_id: str) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "state": _text(source.get("state"), 32) or "unknown",
        "schema_version": _text(source.get("schema_version"), 96),
        "selection_state": _text(source.get("selection_state"), 32),
        "selected_capability_id": _text(source.get("selected_capability_id"), 96) or None,
        "candidate_ids": _strings(source.get("candidate_ids"), 16),
        "reason_code": _text(source.get("reason_code"), 96),
        "domain_id": domain_id,
    }


def _workflow_summary(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "state": _text(source.get("state"), 32) or "unknown",
        "source": _text(source.get("source"), 32),
        "selected_by": _text(source.get("selected_by"), 32),
        "selected_capability_id": _text(source.get("selected_capability_id"), 96) or None,
        "workflow_template_id": _text(source.get("workflow_template_id"), 96) or None,
        "workflow_template_version": _text(source.get("workflow_template_version"), 48) or None,
        "missing_fields": _strings(source.get("missing_fields"), _MAX_FIELDS),
    }


def _readiness(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {"status": value}
    result: dict[str, Any] = {}
    for key in (
        "status",
        "coverage",
        "time_range",
        "crs",
        "resolution",
        "availability_reason",
    ):
        if source.get(key) is not None:
            result[key] = _safe_value(source.get(key), depth=0)
    return result or {"status": "unknown"}


def _readiness_status(value: Any) -> str:
    source = value if isinstance(value, Mapping) else {}
    return _text(source.get("status"), 32).lower() or "unknown"


def _missing_projections(
    values: Sequence[Mapping[str, Any]],
    contexts: Sequence[Mapping[str, Any]],
    *,
    max_domains: int,
    max_fields: int,
) -> list[dict[str, Any]]:
    source = [item for item in values if isinstance(item, Mapping)]
    if not source:
        source = [
            {
                "domain_id": item.get("domain_id"),
                "fields": item.get("missing_fields") or [],
            }
            for item in contexts
            if item.get("missing_fields")
        ]
    result: list[dict[str, Any]] = []
    for item in source[:max_domains]:
        domain_id = _text(item.get("domain_id"), 64)
        fields = _fields(item.get("fields"), max_fields)
        if domain_id and fields:
            result.append({"domain_id": domain_id, "fields": fields})
    return result


def _fields(value: Any, limit: int) -> list[dict[str, Any]]:
    values = value if isinstance(value, (list, tuple)) else []
    result: list[dict[str, Any]] = []
    for raw in values[:limit]:
        if isinstance(raw, Mapping):
            field_id = _text(raw.get("id") or raw.get("key"), 80)
            label = _text(raw.get("label") or field_id, 120)
            kind = _text(raw.get("kind"), 32) or "fact"
        else:
            field_id = _text(raw, 80)
            label, kind = field_id, "fact"
        if field_id:
            result.append({"id": field_id, "label": label, "kind": kind})
    return result


def _workflow_missing_fields(source: Mapping[str, Any], value: Any) -> list[Any]:
    """Decorate legacy workflow field IDs with catalog-declared labels."""

    definitions: dict[str, Mapping[str, Any]] = {}
    for candidate in source.get("capability_candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        requirements = candidate.get("request_requirements")
        fields = requirements.get("clarification_fields") if isinstance(requirements, Mapping) else ()
        for field in fields or ():
            if isinstance(field, Mapping):
                field_id = _text(field.get("id") or field.get("key"), 80)
                if field_id and field_id not in definitions:
                    definitions[field_id] = field
    values = value if isinstance(value, (list, tuple)) else []
    result: list[Any] = []
    for raw in values[:_MAX_FIELDS]:
        field_id = _text(raw.get("id") if isinstance(raw, Mapping) else raw, 80)
        declared = definitions.get(field_id)
        if declared is not None:
            result.append(
                {
                    "id": field_id,
                    "label": _text(declared.get("label") or field_id, 120),
                    "kind": _text(declared.get("kind"), 32) or "fact",
                }
            )
        elif field_id:
            result.append(field_id)
    return result


def _requirement_ids(value: Any) -> list[str]:
    source = value if isinstance(value, Mapping) else {}
    fields = source.get("clarification_fields") or []
    return [
        _text(item.get("id") or item.get("key"), 80)
        for item in fields[:_MAX_FIELDS]
        if isinstance(item, Mapping) and _text(item.get("id") or item.get("key"), 80)
    ]


def _catalog_summary(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "schema_version": _text(source.get("schema_version"), 96),
        "status": _text(source.get("status"), 32),
        "capability_count": _bounded_int(source.get("capability_count")),
        "bound_count": _bounded_int(source.get("bound_count")),
        "unbound_count": _bounded_int(source.get("unbound_count")),
    }


def _receipt_fingerprint(value: Mapping[str, Any]) -> str:
    identity = {
        "request_fingerprint": value.get("request_fingerprint"),
        "domain_ids": value.get("domain_ids"),
        "state": value.get("state"),
        "reason_code": value.get("reason_code"),
        "candidates": [
            {
                "domain_id": item.get("domain_id"),
                "capability_id": item.get("capability_id"),
                "state": item.get("state"),
                "execution_ready": item.get("execution_ready"),
            }
            for item in value.get("candidates") or []
            if isinstance(item, Mapping)
        ],
        "data_requirements": [
            {
                "requirement_id": item.get("requirement_id"),
                "status": item.get("status"),
            }
            for item in value.get("data_requirements") or []
            if isinstance(item, Mapping)
        ],
        "missing_facts": value.get("missing_facts"),
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _next_actions(state: str, reason_code: str) -> list[str]:
    if state == "needs_facts":
        return ["补充缺失事实后继续规划"]
    if reason_code == "data_unavailable":
        return ["检查数据覆盖、字段和后端就绪状态", "数据恢复后重新发现"]
    if state == "capability_unavailable":
        return ["补充任务目标或选择可执行能力"]
    return ["由 Planner 组合已注册能力并生成计划"]


def _data_reason(value: Any) -> bool:
    text = _text(value, 160).lower()
    return any(
        token in text
        for token in (
            "data",
            "backend",
            "dataset",
            "readiness",
            "missing",
            "unavailable",
            "not_supported",
        )
    )


def _domain_ids(value: Any, limit: int) -> list[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise AnalysisDiscoveryError("domain_ids must be a list", code="discovery_domain_invalid")
    result: list[str] = []
    for item in value:
        domain_id = _text(item, 64)
        if domain_id and domain_id not in result:
            result.append(domain_id)
    if not result:
        raise AnalysisDiscoveryError("at least one domain is required", code="discovery_domain_invalid")
    if len(result) > limit:
        raise AnalysisDiscoveryError("domain_ids exceed limit", code="discovery_domain_limit")
    return result


def _assert_budget(value: Mapping[str, Any], limit: int) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > limit:
        raise AnalysisDiscoveryError("discovery receipt exceeds max_bytes", code="discovery_budget_exceeded")


def _safe_value(value: Any, *, depth: int) -> Any:
    if depth >= 3:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _safe_value(item, depth=depth + 1)
            for key, item in list(value.items())[:24]
            if not _private(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:16]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:320] if isinstance(value, str) else value
    return str(value)[:120]


def _strings(value: Any, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in list(value)[:limit]:
        text = _text(item, 160)
        if text and text not in result:
            result.append(text)
    return result


def _positive_limit(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(name + " must be positive") from exc
    if result < 1:
        raise ValueError(name + " must be positive")
    return result


def _bounded_int(value: Any) -> int:
    try:
        return max(0, min(int(value), 1_000_000))
    except (TypeError, ValueError):
        return 0


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _private(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_")
    return normalized in _PRIVATE_KEYS or normalized.endswith("_path") or normalized.endswith("_token")


__all__ = [
    "ANALYSIS_DISCOVERY_EVIDENCE_SCHEMA_VERSION",
    "ANALYSIS_DISCOVERY_SCHEMA_VERSION",
    "AnalysisDiscoveryError",
    "AnalysisDiscoveryGateway",
    "discovery_request_fingerprint",
]
