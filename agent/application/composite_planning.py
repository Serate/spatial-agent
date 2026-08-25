"""Bounded Planner-facing projection for cross-Domain Composite requests.

This module only reads the public Domain Host and Service catalog seams.  It
does not choose a planner, execute a component, inspect private adapters, or
carry Domain-specific policy.  The projection is intentionally smaller than a
runtime capability snapshot so it can be passed to a Rule or LLM planner.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.composite_contract import normalize_composite_request
from agent.composite_request_context import (
    CompositeRequestContextBuilder,
    CompositeRequestContextError,
)
from agent.composite_planner import CompositePlannerError


COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION = "spatial-agent.composite-planner-context.v1"
COMPOSITE_PLANNER_EVIDENCE_SCHEMA_VERSION = "spatial-agent.composite-planner-evidence.v1"
_SAFE_CAPABILITY_FIELDS = (
    "id",
    "label",
    "description",
    "datasets",
    "tools",
    "result_types",
    "available",
    "availability_mode",
    "availability_reason",
    "missing_datasets",
    "derived_datasets",
    "data_layer",
    "capability_status",
)
_SAFE_READINESS_FIELDS = (
    "status",
    "coverage",
    "time_range",
    "crs",
    "resolution",
    "availability_reason",
)


class CompositeCapabilityProjector:
    """Build one bounded, domain-neutral capability context."""

    def __init__(
        self,
        host: Any,
        *,
        max_domains: int = 8,
        max_capabilities: int = 32,
        max_workflows: int = 32,
        max_context_bytes: int = 64_000,
    ) -> None:
        if host is None or not callable(getattr(host, "catalog", None)):
            raise ValueError("host must expose catalog()")
        self._host = host
        self._max_domains = _positive_limit(max_domains, "max_domains")
        self._max_capabilities = _positive_limit(
            max_capabilities, "max_capabilities"
        )
        self._max_workflows = _positive_limit(max_workflows, "max_workflows")
        self._max_context_bytes = _positive_limit(
            max_context_bytes, "max_context_bytes"
        )

    def project(
        self,
        *,
        planner: str = "rule",
        backend: str = "memory",
        domain_ids: Sequence[str] | None = None,
        max_capabilities: int | None = None,
        max_workflows: int | None = None,
    ) -> dict[str, Any]:
        """Project selected public Domain catalogs for Planner consumption."""

        capability_limit = self._max_capabilities if max_capabilities is None else _positive_limit(
            max_capabilities, "max_capabilities"
        )
        workflow_limit = self._max_workflows if max_workflows is None else _positive_limit(
            max_workflows, "max_workflows"
        )
        host_catalog = self._host.catalog()
        if not isinstance(host_catalog, Mapping):
            raise ValueError("domain host catalog must be an object")
        metadata = {
            str(item.get("id")): item
            for item in (host_catalog.get("domains") or [])
            if isinstance(item, Mapping) and str(item.get("id") or "").strip()
        }
        selected_ids = _selected_domain_ids(
            domain_ids,
            host_catalog,
            max_domains=self._max_domains,
        )

        domains: list[dict[str, Any]] = []
        capability_index: list[dict[str, Any]] = []
        workflow_index: list[dict[str, Any]] = []
        readiness: dict[str, str] = {}
        for domain_id in selected_ids:
            selection = self._host.select(domain_id, source="automatic")
            service = self._host.service(selection)
            catalog = _call_catalog(service, planner=planner, backend=backend)
            workflow = _call_workflow(service, planner=planner, backend=backend)
            actual_domain_id = str(catalog.get("domain_id") or domain_id)
            if actual_domain_id != domain_id:
                raise ValueError("domain catalog identity mismatch: " + domain_id)

            capabilities = [
                _project_capability(item)
                for item in (catalog.get("capabilities") or [])[:capability_limit]
                if isinstance(item, Mapping)
            ]
            workflows = [
                _project_workflow(key, item)
                for key, item in list((workflow.get("catalog") or {}).items())[
                    :workflow_limit
                ]
                if isinstance(item, Mapping)
            ]
            readiness_value = _project_readiness(catalog.get("data_readiness"))
            readiness[domain_id] = str(readiness_value.get("status") or "unknown")
            domains.append(
                {
                    "domain_id": domain_id,
                    "label": _bounded_text(metadata.get(domain_id, {}).get("label")),
                    "description": _bounded_text(
                        metadata.get(domain_id, {}).get("description")
                    ),
                    "environment": _bounded_text(catalog.get("environment")),
                    "data_readiness": readiness_value,
                    "capabilities": capabilities,
                    "workflows": workflows,
                    "known_tools": _bounded_strings(workflow.get("known_tools")),
                    "known_result_types": _bounded_strings(
                        workflow.get("known_result_types")
                    ),
                }
            )
            for item in capabilities:
                capability_index.append(
                    {
                        "domain_id": domain_id,
                        "capability_id": item["id"],
                        "label": item.get("label"),
                        "description": item.get("description"),
                        "available": item.get("available"),
                        "availability_mode": item.get("availability_mode"),
                        "availability_reason": item.get("availability_reason"),
                        "datasets": item.get("datasets", []),
                        "tools": item.get("tools", []),
                        "result_types": item.get("result_types", []),
                    }
                )
            for item in workflows:
                workflow_index.append(
                    {
                        "domain_id": domain_id,
                        "workflow_id": item["id"],
                        "label": item.get("label"),
                        "allowed_tools": item.get("allowed_tools", []),
                        "result_types": item.get("result_types", []),
                    }
                )

        result = {
            "schema_version": COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION,
            "planner": _bounded_text(planner),
            "backend": _bounded_text(backend),
            "domain_ids": selected_ids,
            "domain_count": len(domains),
            "domains": domains,
            "capability_index": capability_index[: self._max_capabilities],
            "workflow_index": workflow_index[: self._max_workflows],
            "data_readiness": {
                "status": _aggregate_readiness(readiness.values()),
                "domains": readiness,
            },
            "limits": {
                "max_domains": self._max_domains,
                "max_capabilities": capability_limit,
                "max_workflows": workflow_limit,
            },
        }
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) > self._max_context_bytes:
            raise ValueError("composite planner context exceeds max_bytes")
        return result


class CompositePlanningApplication:
    """Orchestrate planning and hand a valid request to M278 execution."""

    schema_version = "spatial-agent.composite-planning-response.v1"

    def __init__(
        self,
        *,
        host: Any,
        projector: CompositeCapabilityProjector,
        planner: Any,
        composite_runs: Any,
        repair_planner: Any = None,
        max_repairs: int = 1,
        planner_factory: Any = None,
        context_builder: Any = None,
    ) -> None:
        if host is None or projector is None or planner is None or composite_runs is None:
            raise ValueError("host, projector, planner and composite_runs are required")
        if not callable(getattr(planner, "plan", None)):
            raise ValueError("planner must expose plan()")
        self._host = host
        self._projector = projector
        self._planner = planner
        self._planner_factory = planner_factory
        self._repair_planner = repair_planner
        self._composite_runs = composite_runs
        self._max_repairs = max(0, min(1, int(max_repairs)))
        self._context_builder = context_builder or CompositeRequestContextBuilder(
            host=host,
            catalog_projector=projector,
        )
        if not callable(getattr(self._context_builder, "build", None)):
            raise ValueError("context_builder must expose build()")

    def prepare(
        self,
        request: str,
        *,
        planner_name: str = "rule",
        backend: str = "memory",
        domain_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Resolve catalog, plan, validate, and return no-execution output."""
        text = str(request or "").strip()[:2000]
        if not text:
            return self._clarification(
                "请提供要分析的问题。", "request_required", planner_name
            )
        context: Mapping[str, Any] = {}
        try:
            context = self._context_builder.build(
                text,
                planner=planner_name,
                backend=backend,
                domain_ids=domain_ids,
            )
            context_clarification = context.get("clarification")
            if isinstance(context_clarification, Mapping) and str(
                context_clarification.get("state") or ""
            ) in {"required", "ambiguous", "unavailable"}:
                return self._context_clarification(context, planner_name)
            candidate = self._selected_planner(planner_name, backend).plan(
                text, context=context
            )
            candidate = self._normalize_candidate(
                candidate,
                context=context,
                planner_name=planner_name,
            )
            return self._attach_context(candidate, context)
        except CompositeRequestContextError as exc:
            return self._context_error(exc, planner_name)
        except CompositePlannerError as exc:
            if self._repair_planner is not None and self._max_repairs:
                try:
                    repaired = self._repair_planner.plan(text, context=context)
                    repaired_response = self._normalize_candidate(
                        repaired,
                        context=context,
                        planner_name=planner_name,
                    )
                    repaired_response["repair_lineage"] = {
                        "attempted": True,
                        "count": 1,
                        "reason_code": exc.code,
                        "status": "repaired",
                    }
                    return self._attach_context(repaired_response, context)
                except Exception:
                    pass
            status = "NEEDS_CLARIFICATION" if exc.code in {
                "planner_provider_failed",
                "planner_context_too_large",
                "plan_components_required",
                "capability_unavailable",
            } else "REJECTED"
            return self._attach_context({
                "schema_version": self.schema_version,
                "status": status,
                "planner_source": planner_name[:32],
                "message": "无法安全生成可执行的组合计划，请补充信息或调整问题。",
                "error_code": exc.code,
                "components": [],
                "request": None,
                "validation": {"status": "failed", "reason_code": exc.code},
                "planner_evidence": _planner_evidence(
                    {},
                    planner_source=planner_name,
                    schema_status="failed",
                    component_count=0,
                    request_fingerprint=None,
                ),
                "repair_lineage": {
                    "attempted": bool(self._repair_planner and self._max_repairs),
                    "count": 1 if self._repair_planner and self._max_repairs else 0,
                    "reason_code": exc.code,
                    "status": "failed",
                },
            }, context)
        except Exception as exc:
            return self._attach_context({
                "schema_version": self.schema_version,
                "status": "REJECTED",
                "planner_source": planner_name[:32],
                "message": "组合计划校验失败。",
                "error_code": "planning_application_failed",
                "components": [],
                "request": None,
                "validation": {"status": "failed", "reason_code": "planning_application_failed"},
                "planner_evidence": _planner_evidence(
                    {},
                    planner_source=planner_name,
                    schema_status="failed",
                    component_count=0,
                    request_fingerprint=None,
                ),
            }, context)

    def submit(
        self,
        request: str,
        *,
        session_id: str = "default",
        idempotency_key: str | None = None,
        planner_name: str = "rule",
        backend: str = "memory",
        domain_ids: list[str] | tuple[str, ...] | None = None,
        asynchronous: bool = True,
        export_artifact: bool = False,
    ) -> dict[str, Any]:
        prepared = self.prepare(
            request,
            planner_name=planner_name,
            backend=backend,
            domain_ids=domain_ids,
        )
        if prepared.get("status") != "PLANNED":
            return prepared
        canonical = prepared.get("request")
        if asynchronous:
            execution = self._composite_runs.submit_async(
                canonical,
                session_id=str(session_id or "default")[:120],
                idempotency_key=idempotency_key,
                export_artifact=bool(export_artifact),
            )
        else:
            execution = self._composite_runs.run(
                canonical,
                session_id=str(session_id or "default")[:120],
                export_artifact=bool(export_artifact),
            )
        result = dict(prepared)
        result["status"] = execution.get("status", "SUBMITTED")
        result["execution"] = execution
        result["run_id"] = execution.get("run_id")
        return result

    def _normalize_candidate(
        self,
        candidate: Any,
        *,
        context: Mapping[str, Any],
        planner_name: str,
    ) -> dict[str, Any]:
        if not isinstance(candidate, Mapping):
            raise CompositePlannerError("planner output must be an object", code="plan_object_required")
        status = str(candidate.get("status") or "").upper()
        if status != "PLANNED":
            planner_source = str(candidate.get("planner_source") or planner_name)[:32]
            return {
                "schema_version": self.schema_version,
                "status": status or "NEEDS_CLARIFICATION",
                "planner_source": planner_source,
                "message": str(candidate.get("message") or "需要补充任务信息。")[:640],
                "components": [],
                "request": None,
                "validation": dict(candidate.get("validation") or {"status": "not_run"}),
                "compatibility": _safe_compatibility(candidate.get("compatibility")),
                "planner_evidence": _planner_evidence(
                    candidate,
                    planner_source=planner_source,
                    schema_status="not_run",
                    component_count=0,
                    request_fingerprint=None,
                ),
            }
        raw_request = candidate.get("request")
        try:
            canonical = normalize_composite_request(raw_request)
        except Exception as exc:
            raise CompositePlannerError(
                "candidate composite request is invalid", code="candidate_request_invalid"
            ) from exc
        projected = candidate.get("components")
        if not isinstance(projected, list) or not projected:
            raise CompositePlannerError(
                "planned components are missing", code="plan_components_required"
            )
        self._validate_domains_and_capabilities(projected, context)
        planner_source = str(candidate.get("planner_source") or planner_name)[:32]
        compatibility = _safe_compatibility(candidate.get("compatibility"))
        result = {
            "schema_version": self.schema_version,
            "status": "PLANNED",
            "planner_source": planner_source,
            "goal": str(candidate.get("goal") or "组合分析")[:320],
            "message": str(candidate.get("message") or "")[:640],
            "components": [dict(item) for item in projected[:8] if isinstance(item, Mapping)],
            "request": canonical,
            "request_fingerprint": canonical.get("fingerprint"),
            "validation": {"status": "valid", "reason_code": "allowlist_and_schema_valid"},
            "compatibility": compatibility,
        }
        result["planner_evidence"] = _planner_evidence(
            candidate,
            planner_source=planner_source,
            schema_status="valid",
            component_count=len(result["components"]),
            request_fingerprint=canonical.get("fingerprint"),
        )
        return result

    def _selected_planner(self, planner_name: str, backend: str) -> Any:
        if callable(self._planner_factory):
            selected = self._planner_factory(planner_name, backend)
            if selected is None or not callable(getattr(selected, "plan", None)):
                raise CompositePlannerError(
                    "planner factory returned no planner", code="planner_unavailable"
                )
            return selected
        return self._planner

    def _validate_domains_and_capabilities(
        self, components: list[Any], context: Mapping[str, Any]
    ) -> None:
        index = {
            (str(item.get("domain_id")), str(item.get("capability_id"))): item
            for item in (context.get("capability_index") or [])
            if isinstance(item, Mapping)
        }
        for item in components:
            if not isinstance(item, Mapping):
                raise CompositePlannerError("component is invalid", code="plan_component_invalid")
            domain_id = str(item.get("domain_id") or "")
            capability_id = str(item.get("capability_id") or "")
            try:
                selection = self._host.select(domain_id, source="automatic")
            except Exception as exc:
                raise CompositePlannerError("domain is not allowlisted", code="domain_not_allowlisted") from exc
            if not selection:
                raise CompositePlannerError("domain is not allowlisted", code="domain_not_allowlisted")
            capability = index.get((domain_id, capability_id))
            if capability is None:
                raise CompositePlannerError(
                    "capability is not registered",
                    code="capability_not_registered",
                )
            if capability is not None and capability.get("available") is False:
                raise CompositePlannerError("capability is unavailable", code="capability_unavailable")

    @staticmethod
    def _attach_context(
        result: Mapping[str, Any], context: Mapping[str, Any]
    ) -> dict[str, Any]:
        projected = dict(result)
        projected["request_context"] = dict(context)
        evidence = dict(projected.get("planner_evidence") or {})
        evidence["context_fingerprint"] = str(
            context.get("request_fingerprint") or ""
        )[:128] or None
        evidence["context_schema_version"] = str(
            context.get("schema_version") or ""
        )[:96] or None
        projected["planner_evidence"] = evidence
        return projected

    @classmethod
    def _context_clarification(
        cls, context: Mapping[str, Any], planner_name: str
    ) -> dict[str, Any]:
        clarification = context.get("clarification")
        clarification = clarification if isinstance(clarification, Mapping) else {}
        result = cls._attach_context(
            cls._clarification(
                str(clarification.get("message") or "请补充任务信息。")[:640],
                str(clarification.get("reason_code") or "request_context_clarification")[:96],
                planner_name,
            ),
            context,
        )
        result["clarification"] = dict(clarification)
        return result

    @classmethod
    def _context_error(
        cls, error: CompositeRequestContextError, planner_name: str
    ) -> dict[str, Any]:
        return cls._clarification(
            "无法形成安全的请求上下文，请补充信息或稍后重试。",
            error.code,
            planner_name,
        )

    @staticmethod
    def _clarification(message: str, reason_code: str, planner_name: str) -> dict[str, Any]:
        return {
            "schema_version": "spatial-agent.composite-planning-response.v1",
            "status": "NEEDS_CLARIFICATION",
            "planner_source": str(planner_name)[:32],
            "message": message[:640],
            "error_code": reason_code,
            "components": [],
            "request": None,
            "validation": {"status": "not_run", "reason_code": reason_code},
            "compatibility": _safe_compatibility(None),
            "planner_evidence": _planner_evidence(
                {},
                planner_source=planner_name,
                schema_status="not_run",
                component_count=0,
                request_fingerprint=None,
            ),
        }


def _safe_compatibility(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": "identity", "actions": []}
    status = str(value.get("status") or "identity").strip().lower()
    if status not in {"identity", "normalized"}:
        status = "identity"
    actions = []
    for action in value.get("actions") or []:
        text = str(action or "").strip()[:96]
        if text and text not in actions:
            actions.append(text)
        if len(actions) >= 16:
            break
    return {"status": status, "actions": actions}


def _planner_evidence(
    candidate: Mapping[str, Any],
    *,
    planner_source: str,
    schema_status: str,
    component_count: int,
    request_fingerprint: Any,
) -> dict[str, Any]:
    compatibility = _safe_compatibility(candidate.get("compatibility"))
    fingerprint = str(request_fingerprint or "").strip()[:128] or None
    return {
        "schema_version": COMPOSITE_PLANNER_EVIDENCE_SCHEMA_VERSION,
        "planner_source": str(planner_source or "unknown")[:32],
        "schema_status": str(schema_status or "unknown")[:32],
        "component_count": max(0, min(8, int(component_count))),
        "request_fingerprint": fingerprint,
        "compatibility": compatibility,
    }


def _call_catalog(service: Any, *, planner: str, backend: str) -> Mapping[str, Any]:
    resolver = getattr(service, "capabilities", None)
    if not callable(resolver):
        raise ValueError("Domain service does not expose capabilities()")
    value = resolver(planner=planner, backend=backend)
    if not isinstance(value, Mapping):
        raise ValueError("Domain capability catalog must be an object")
    return value


def _call_workflow(service: Any, *, planner: str, backend: str) -> Mapping[str, Any]:
    resolver = getattr(service, "workflow_contract", None)
    if not callable(resolver):
        return {"catalog": {}, "known_tools": [], "known_result_types": []}
    value = resolver(planner=planner, backend=backend)
    return value if isinstance(value, Mapping) else {}


def _project_capability(value: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for field in _SAFE_CAPABILITY_FIELDS:
        if field not in value:
            continue
        if field in {"datasets", "tools", "result_types", "missing_datasets", "derived_datasets"}:
            projected[field] = _bounded_strings(value.get(field))
        elif field == "available":
            projected[field] = bool(value.get(field))
        else:
            projected[field] = _bounded_text(value.get(field))
    capability_id = str(projected.get("id") or "").strip()
    if not capability_id:
        raise ValueError("capability id is required")
    projected["request_requirements"] = _project_requirements(
        value.get("request_requirements")
    )
    return projected


def _project_workflow(key: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    workflow_id = str(value.get("id") or key or "").strip()
    if not workflow_id:
        raise ValueError("workflow id is required")
    return {
        "id": workflow_id[:96],
        "label": _bounded_text(value.get("label")),
        "description": _bounded_text(value.get("description")),
        "allowed_tools": _bounded_strings(value.get("allowed_tools")),
        "result_types": _bounded_strings(value.get("result_types")),
        "steps": [
            {
                "id": _bounded_text(step.get("id")),
                "tool": _bounded_text(step.get("tool")),
                "depends_on": _bounded_strings(step.get("depends_on")),
            }
            for step in (value.get("step_blueprint") or [])[:16]
            if isinstance(step, Mapping)
        ],
    }


def _project_requirements(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    result = {
        "entities": _bounded_strings(source.get("entities")),
        "datasets": _bounded_strings(source.get("datasets")),
        "constraints": _bounded_strings(source.get("constraints")),
        "clarification_fields": [],
    }
    for field in (source.get("clarification_fields") or [])[:16]:
        if not isinstance(field, Mapping):
            continue
        kind = str(field.get("kind") or "")
        field_id = str(field.get("id") or "").strip()
        if not field_id or kind not in {"entity", "dataset", "constraint"}:
            continue
        result["clarification_fields"].append(
            {
                "id": field_id[:80],
                "label": _bounded_text(field.get("label")),
                "kind": kind,
                "key": _bounded_text(field.get("key") or field.get("fact")),
                "keys": _bounded_strings(field.get("keys")),
                "values": _bounded_strings(field.get("values")),
            }
        )
    return result


def _project_readiness(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            key: _bounded_text(value.get(key))
            for key in _SAFE_READINESS_FIELDS
            if key in value
        } or {"status": "unknown"}
    if isinstance(value, str) and value.strip():
        return {"status": value.strip()[:32]}
    return {"status": "unknown"}


def _selected_domain_ids(
    requested: Sequence[str] | None,
    host_catalog: Mapping[str, Any],
    *,
    max_domains: int,
) -> list[str]:
    source = requested
    if source is None:
        source = host_catalog.get("domain_ids") or [
            item.get("id")
            for item in (host_catalog.get("domains") or [])
            if isinstance(item, Mapping)
        ]
    if isinstance(source, str) or not isinstance(source, Sequence):
        raise ValueError("domain_ids must be a bounded list")
    result: list[str] = []
    for value in source:
        domain_id = str(value or "").strip().lower()
        if not domain_id or domain_id in result:
            continue
        result.append(domain_id)
    if not result:
        raise ValueError("at least one domain is required")
    if len(result) > max_domains:
        raise ValueError("domain_ids exceeds max_domains")
    return sorted(result)


def _aggregate_readiness(values: Any) -> str:
    statuses = {str(value or "unknown") for value in values}
    if statuses and statuses <= {"ready"}:
        return "ready"
    if "partial" in statuses or "ready" in statuses:
        return "partial"
    if "unavailable" in statuses:
        return "unavailable"
    return "unknown"


def _bounded_strings(value: Any, limit: int = 32) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()[:160]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _bounded_text(value: Any, limit: int = 320) -> str:
    return str(value or "").strip()[:limit]


def _positive_limit(value: Any, name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(name + " must be positive") from exc
    if normalized < 1:
        raise ValueError(name + " must be positive")
    return normalized


__all__ = [
    "COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION",
    "CompositeCapabilityProjector",
]
