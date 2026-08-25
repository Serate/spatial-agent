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
from agent.planner_repair import (
    build_planner_repair_request,
    build_repair_lineage,
    is_repairable_planner_error,
)
from agent.provider_structured_output import project_structured_output_evidence
from agent.runtime_core.composite_taskplan import (
    CompositeTaskPlanBridge,
    CompositeTaskPlanBridgeError,
    project_task_plan_bridge,
)
from agent.runtime_core.plan_completeness import (
    annotate_catalog_capabilities,
    assess_catalog_consistency,
    validate_plan_completeness,
    PlanCompletenessError,
)


COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION = "spatial-agent.composite-planner-context.v1"
COMPOSITE_PLANNER_EVIDENCE_SCHEMA_VERSION = "spatial-agent.composite-planner-evidence.v1"
COMPOSITE_PLANNER_SELECTION_SCHEMA_VERSION = "spatial-agent.composite-planner-selection.v1"
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
    "workflow_ids",
    "plan_mode",
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
                        "selection_key": f"{domain_id}::{item['id']}"[:140],
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

        catalog_consistency = assess_catalog_consistency({"domains": domains})
        domains = annotate_catalog_capabilities(domains, catalog_consistency)
        binding_index = {
            (str(item.get("domain_id")), str(item.get("capability_id"))): item
            for item in (catalog_consistency.get("bindings") or [])
            if isinstance(item, Mapping)
        }
        for item in capability_index:
            binding = binding_index.get(
                (str(item.get("domain_id")), str(item.get("capability_id")))
            )
            if not binding:
                continue
            item["workflow_ids"] = [
                _bounded_text(value) for value in binding.get("workflow_ids", [])[:8]
            ]
            item["plan_mode"] = _bounded_text(binding.get("plan_mode"))
            if item["plan_mode"] == "unbound":
                item["availability_reason"] = "workflow_not_registered"

        result = {
            "schema_version": COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION,
            "planner": _bounded_text(planner),
            "backend": _bounded_text(backend),
            "domain_ids": selected_ids,
            "domain_count": len(domains),
            "domains": domains,
            "capability_index": capability_index[: self._max_capabilities],
            "workflow_index": workflow_index[: self._max_workflows],
            "catalog_consistency": catalog_consistency,
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
        repair_planner_factory: Any = None,
        max_repairs: int = 1,
        planner_factory: Any = None,
        context_builder: Any = None,
        taskplan_bridge: Any = None,
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
        self._repair_planner_factory = repair_planner_factory
        self._composite_runs = composite_runs
        self._max_repairs = max(0, min(1, int(max_repairs)))
        self._taskplan_bridge = taskplan_bridge or CompositeTaskPlanBridge(host=host)
        if not callable(getattr(self._taskplan_bridge, "bridge", None)):
            raise ValueError("taskplan_bridge must expose bridge()")
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
        selected_planner: Any = None
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
            selected_planner = self._selected_planner(planner_name, backend)
            candidate = selected_planner.plan(text, context=context)
            candidate = self._normalize_candidate(
                candidate,
                context=context,
                planner_name=planner_name,
                backend=backend,
                provider_metrics=_safe_planner_metrics(selected_planner),
            )
            return self._attach_context(candidate, context)
        except CompositeRequestContextError as exc:
            return self._context_error(exc, planner_name)
        except CompositePlannerError as exc:
            repairable = is_repairable_planner_error(exc.code)
            repair_lineage = build_repair_lineage(
                reason_code=exc.code,
                status="skipped" if not repairable else "not_attempted",
                attempted=False,
                count=0,
                request_fingerprint=context.get("request_fingerprint"),
            )
            repair_planner = self._repair_planner
            repair_factory_failed = False
            if (
                repair_planner is None
                and repairable
                and self._max_repairs
                and callable(self._repair_planner_factory)
            ):
                try:
                    repair_planner = self._repair_planner_factory(
                        planner_name, backend
                    )
                except Exception:
                    repair_factory_failed = True
            if repair_factory_failed:
                repair_lineage = build_repair_lineage(
                    reason_code=exc.code,
                    status="failed",
                    attempted=True,
                    count=1,
                    request_fingerprint=context.get("request_fingerprint"),
                )
            if repair_planner is not None and self._max_repairs and repairable:
                try:
                    repair_request = build_planner_repair_request(
                        exc.code,
                        request_fingerprint=context.get("request_fingerprint"),
                        context_schema_version=context.get("schema_version"),
                    )
                    repair_context = dict(context)
                    repair_context["planner_repair"] = repair_request
                    repaired = repair_planner.plan(
                        text, context=repair_context
                    )
                    repaired_response = self._normalize_candidate(
                        repaired,
                        context=context,
                        planner_name=planner_name,
                        backend=backend,
                        provider_metrics=_safe_planner_metrics(repair_planner),
                    )
                    repair_lineage = build_repair_lineage(
                        reason_code=exc.code,
                        status="repaired",
                        attempted=True,
                        count=1,
                        request_fingerprint=context.get("request_fingerprint"),
                    )
                    repaired_response["repair_lineage"] = repair_lineage
                    planner_evidence = dict(
                        repaired_response.get("planner_evidence") or {}
                    )
                    planner_evidence["repair_lineage"] = repair_lineage
                    repaired_response["planner_evidence"] = planner_evidence
                    return self._attach_context(repaired_response, context)
                except Exception:
                    repair_lineage = build_repair_lineage(
                        reason_code=exc.code,
                        status="failed",
                        attempted=True,
                        count=1,
                        request_fingerprint=context.get("request_fingerprint"),
                    )
            status = "NEEDS_CLARIFICATION" if exc.code in {
                "planner_provider_failed",
                "planner_context_too_large",
                "plan_components_required",
                "capability_unavailable",
                "taskplan_component_clarification",
            } else "REJECTED"
            failure_evidence = _planner_evidence(
                {},
                planner_source=planner_name,
                schema_status="failed",
                component_count=0,
                request_fingerprint=None,
                requested_planner=planner_name,
                selection_state="failed",
                selection_reason=exc.code,
                candidate_count=_context_candidate_count(context),
                provider_metrics=_safe_planner_metrics(repair_planner or selected_planner),
            )
            failure_evidence["repair_lineage"] = repair_lineage
            return self._attach_context({
                "schema_version": self.schema_version,
                "status": status,
                "planner_source": planner_name[:32],
                "message": "无法安全生成可执行的组合计划，请补充信息或调整问题。",
                "error_code": exc.code,
                "components": [],
                "request": None,
                "validation": {"status": "failed", "reason_code": exc.code},
                "planner_evidence": failure_evidence,
                "repair_lineage": repair_lineage,
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
                    requested_planner=planner_name,
                    selection_state="failed",
                    selection_reason="planning_application_failed",
                    candidate_count=_context_candidate_count(context),
                    provider_metrics=_safe_planner_metrics(selected_planner),
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
            submit_with_evidence = getattr(
                self._composite_runs, "submit_async_with_planning", None
            )
            if callable(submit_with_evidence):
                execution = submit_with_evidence(
                    canonical,
                    session_id=str(session_id or "default")[:120],
                    idempotency_key=idempotency_key,
                    export_artifact=bool(export_artifact),
                    planner_evidence=prepared.get("planner_evidence"),
                )
            else:
                execution = self._composite_runs.submit_async(
                    canonical,
                    session_id=str(session_id or "default")[:120],
                    idempotency_key=idempotency_key,
                    export_artifact=bool(export_artifact),
                )
        else:
            run_with_evidence = getattr(self._composite_runs, "run_with_planning", None)
            if callable(run_with_evidence):
                execution = run_with_evidence(
                    canonical,
                    session_id=str(session_id or "default")[:120],
                    export_artifact=bool(export_artifact),
                    planner_evidence=prepared.get("planner_evidence"),
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
        backend: str,
        provider_metrics: Mapping[str, Any] | None = None,
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
                    requested_planner=planner_name,
                    selection_state=_selection_state_for_status(status),
                    selection_reason=_selection_reason_for_candidate(candidate, status),
                    candidate_count=_context_candidate_count(context),
                    provider_metrics=provider_metrics,
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
        try:
            task_plan_bridge = self._taskplan_bridge.bridge(
                projected,
                context=context,
                planner=planner_name,
                backend=backend,
            )
        except CompositeTaskPlanBridgeError as exc:
            raise CompositePlannerError(
                "candidate TaskPlan failed the execution gate", code=exc.code
            ) from exc
        try:
            plan_completeness = validate_plan_completeness(
                projected,
                context=context,
                task_plan_bridge=task_plan_bridge,
            )
        except PlanCompletenessError as exc:
            raise CompositePlannerError(
                "candidate plan is not semantically complete", code=exc.code
            ) from exc
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
            "validation": {
                "status": "valid",
                "reason_code": "allowlist_and_schema_valid",
                "plan_completeness": plan_completeness,
            },
            "compatibility": compatibility,
            "task_plan_bridge": project_task_plan_bridge(task_plan_bridge),
        }
        result["planner_evidence"] = _planner_evidence(
            candidate,
            planner_source=planner_source,
            schema_status="valid",
            component_count=len(result["components"]),
            request_fingerprint=canonical.get("fingerprint"),
            requested_planner=planner_name,
            selection_state="selected",
            selection_reason="planner_selected_registered_capabilities",
            selected_capability_ids=[
                item.get("capability_id")
                for item in result["components"]
                if isinstance(item, Mapping)
            ],
            candidate_count=_context_candidate_count(context),
            task_plan_bridge=task_plan_bridge,
            provider_metrics=provider_metrics,
        )
        result["planner_evidence"]["plan_completeness"] = plan_completeness
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
            if capability.get("plan_mode") == "unbound":
                raise CompositePlannerError(
                    "capability has no registered workflow",
                    code="capability_not_materializable",
                )
            workflow = item.get("workflow")
            template_id = (
                str(workflow.get("template_id") or "").strip()
                if isinstance(workflow, Mapping)
                else ""
            )
            workflow_ids = {
                str(value).strip()
                for value in (capability.get("workflow_ids") or [])
                if str(value).strip()
            }
            if template_id and workflow_ids and template_id not in workflow_ids:
                raise CompositePlannerError(
                    "component workflow is not bound to the capability",
                    code="capability_workflow_mismatch",
                )

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
                requested_planner=planner_name,
                selection_state="clarification",
                selection_reason=reason_code,
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
    requested_planner: Any = None,
    selection_state: str = "unavailable",
    selection_reason: Any = None,
    selected_capability_ids: Any = None,
    candidate_count: int = 0,
    task_plan_bridge: Any = None,
    provider_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    compatibility = _safe_compatibility(candidate.get("compatibility"))
    fingerprint = str(request_fingerprint or "").strip()[:128] or None
    result = {
        "schema_version": COMPOSITE_PLANNER_EVIDENCE_SCHEMA_VERSION,
        "planner_source": str(planner_source or "unknown")[:32],
        "schema_status": str(schema_status or "unknown")[:32],
        "component_count": max(0, min(8, int(component_count))),
        "request_fingerprint": fingerprint,
        "compatibility": compatibility,
        "selection": _planner_selection_evidence(
            requested_planner=requested_planner,
            selected_source=planner_source,
            state=selection_state,
            reason_code=selection_reason,
            selected_capability_ids=selected_capability_ids,
            selected_capability_keys=_capability_keys(candidate.get("components")),
            candidate_count=candidate_count,
        ),
    }
    if isinstance(task_plan_bridge, Mapping):
        result["task_plan_bridge"] = project_task_plan_bridge(task_plan_bridge)
    structured_output = project_structured_output_evidence(provider_metrics)
    if structured_output is not None:
        result["structured_output"] = structured_output
    return result


def _safe_planner_metrics(planner: Any) -> Mapping[str, Any] | None:
    metrics = getattr(planner, "metrics", None)
    if not callable(metrics):
        return None
    try:
        value = metrics()
    except Exception:
        return None
    return value if isinstance(value, Mapping) else None


def _planner_selection_evidence(
    *,
    requested_planner: Any,
    selected_source: Any,
    state: Any,
    reason_code: Any,
    selected_capability_ids: Any,
    selected_capability_keys: Any,
    candidate_count: Any,
) -> dict[str, Any]:
    """Build the bounded planner/source decision shared by every outcome."""

    allowed_states = {"selected", "clarification", "rejected", "failed", "unavailable"}
    normalized_state = str(state or "unavailable").strip().lower()
    if normalized_state not in allowed_states:
        normalized_state = "unavailable"
    capability_ids: list[str] = []
    values = selected_capability_ids if isinstance(selected_capability_ids, (list, tuple, set)) else []
    for value in values:
        text = str(value or "").strip()[:96]
        if text and text not in capability_ids:
            capability_ids.append(text)
        if len(capability_ids) >= 8:
            break
    capability_keys: list[str] = []
    key_values = (
        selected_capability_keys
        if isinstance(selected_capability_keys, (list, tuple, set))
        else []
    )
    for value in key_values:
        text = str(value or "").strip()[:140]
        if text and text not in capability_keys:
            capability_keys.append(text)
        if len(capability_keys) >= 8:
            break
    try:
        bounded_count = max(0, min(64, int(candidate_count)))
    except (TypeError, ValueError):
        bounded_count = 0
    return {
        "schema_version": COMPOSITE_PLANNER_SELECTION_SCHEMA_VERSION,
        "state": normalized_state,
        "requested_planner": str(requested_planner or "unknown").strip()[:32] or "unknown",
        "selected_source": str(selected_source or "unknown").strip()[:32] or "unknown",
        "reason_code": str(reason_code or "planner_selection_unavailable").strip()[:96],
        "selected_capability_ids": capability_ids,
        "selected_capability_keys": capability_keys,
        "candidate_count": bounded_count,
    }


def _capability_keys(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        domain_id = str(item.get("domain_id") or "").strip()
        capability_id = str(item.get("capability_id") or "").strip()
        if not domain_id or not capability_id:
            continue
        key = f"{domain_id}::{capability_id}"[:140]
        if key not in result:
            result.append(key)
        if len(result) >= 8:
            break
    return result


def _selection_state_for_status(status: str) -> str:
    normalized = str(status or "").upper()
    if normalized == "NEEDS_CLARIFICATION":
        return "clarification"
    if normalized == "REJECTED":
        return "rejected"
    return "unavailable"


def _selection_reason_for_candidate(candidate: Mapping[str, Any], status: str) -> str:
    validation = candidate.get("validation") if isinstance(candidate, Mapping) else None
    if isinstance(validation, Mapping) and validation.get("reason_code"):
        return str(validation["reason_code"])[:96]
    return "planner_outcome_" + str(status or "unavailable").lower()[:64]


def _context_candidate_count(context: Mapping[str, Any]) -> int:
    values = context.get("capability_index") if isinstance(context, Mapping) else None
    return len(values) if isinstance(values, list) else 0


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
