"""Bounded Planner-facing projection for cross-Domain Composite requests.

This module only reads the public Domain Host and Service catalog seams.  It
does not choose a planner, execute a component, inspect private adapters, or
carry Domain-specific policy.  The projection is intentionally smaller than a
runtime capability snapshot so it can be passed to a Rule or LLM planner.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.application.composite_contract import (
    inherit_composite_runtime_selection,
    normalize_composite_request,
)
from agent.application.composite_request_context import (
    COMPOSITE_REQUEST_CONTEXT_MAX_BYTES,
    CompositeRequestContextBuilder,
    CompositeRequestContextError,
)
from agent.application.composite_planner import CompositePlannerError
from agent.analysis_intent import AnalysisIntentError, normalize_analysis_intent
from agent.failure_contract import build_failure_evidence
from agent.planner_repair import (
    build_planner_repair_request,
    build_repair_lineage,
    is_repairable_planner_error,
)
from agent.integration.provider_structured_output import project_structured_output_evidence
from agent.request_requirements import project_request_requirements
from agent.data_readiness import project_data_readiness
from agent.integration.provider_runtime import (
    build_planner_attempt_receipt,
    project_planner_attempt_receipt,
    project_provider_runtime_evidence,
)
from agent.runtime_core.composite_taskplan import (
    CompositeTaskPlanBridge,
    CompositeTaskPlanBridgeError,
    project_task_plan_bridge,
)
from agent.runtime_core.execution_binding import (
    ExecutionBindingError,
    build_execution_binding,
    project_execution_binding,
)
from agent.runtime_core.plan_completeness import (
    annotate_catalog_capabilities,
    assess_catalog_consistency,
    validate_plan_completeness,
    PlanCompletenessError,
)
from agent.runtime_core.plan_receipt import build_canonical_plan_receipt
from agent.runtime_core.selection_evidence import project_selection_evidence
from agent.runtime_core.clarification_continuation import (
    ClarificationContinuationError,
    consume_fact_continuation,
)
from agent.runtime_core.planner_envelope import (
    PlannerEnvelopeError,
    build_execution_planner_envelope,
    project_planner_envelope_evidence,
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
    "analysis_operations",
    "available",
    "availability_mode",
    "availability_reason",
    "missing_datasets",
    "derived_datasets",
    "data_layer",
    "capability_status",
    "workflow_ids",
    "plan_mode",
    "output_profiles",
)
class _PreparedComposite(dict):
    """Public mapping plus a non-serialized binding for the submit seam."""

    def __init__(self, value: Mapping[str, Any], *, execution_binding: Mapping[str, Any] | None = None):
        super().__init__(value)
        self.execution_binding = dict(execution_binding) if isinstance(execution_binding, Mapping) else None


class CompositeCapabilityProjector:
    """Build one bounded, domain-neutral capability context."""

    def __init__(
        self,
        host: Any,
        *,
        max_domains: int = 8,
        max_capabilities: int = 32,
        max_workflows: int = 32,
        # This projector builds the internal catalog context.  The provider
        # envelope has a separate, smaller budget and is built later.
        max_context_bytes: int = COMPOSITE_REQUEST_CONTEXT_MAX_BYTES,
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
            execution_contract = _call_execution_contract(
                service, planner=planner, backend=backend
            )
            runtime_capabilities = _call_runtime_capabilities(
                service, planner=planner, backend=backend
            )
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
            runtime_readiness = _project_readiness(
                runtime_capabilities.get("data_readiness")
                if isinstance(runtime_capabilities, Mapping)
                else None
            )
            if runtime_readiness.get("status") not in {"unknown", "not_evaluated"}:
                # Static catalogs describe capability declarations.  When a
                # Domain exposes runtime evidence, its current data status is
                # the authoritative planning input.
                readiness_value = runtime_readiness
            readiness[domain_id] = str(readiness_value.get("status") or "unknown")
            result_profiles = _project_result_profiles(execution_contract.get("result_profiles"))
            for capability in capabilities:
                capability["output_profiles"] = _profiles_for_results(
                    capability.get("result_types"), result_profiles
                )
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
                    "execution_contract": _project_execution_contract(
                        execution_contract
                    ),
                    "known_tools": _bounded_strings(workflow.get("known_tools")),
                    "known_result_types": _bounded_strings(
                        workflow.get("known_result_types")
                    ),
                    "result_profiles": result_profiles,
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
                        "output_profiles": item.get("output_profiles", []),
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
            if "execution_readiness" in binding:
                item["execution_readiness"] = _bounded_text(
                    binding.get("execution_readiness")
                )
                item["execution_ready"] = bool(binding.get("execution_ready"))
                item["execution_reason_code"] = _bounded_text(
                    binding.get("execution_reason_code")
                )
                for key in ("missing_tools", "missing_result_types"):
                    if binding.get(key):
                        item[key] = _bounded_strings(binding.get(key))
            if isinstance(binding.get("operation_binding"), Mapping):
                item["operation_binding"] = _project_operation_binding(
                    binding.get("operation_binding")
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
        continuation_token: str | None = None,
        fact_supplement: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve catalog, plan, validate, and return no-execution output."""
        text = str(request or "").strip()[:2000]
        if not text:
            return self._clarification(
                "请提供要分析的问题。", "request_required", planner_name
            )
        context: Mapping[str, Any] = {}
        selected_planner: Any = None
        continuation: Mapping[str, Any] | None = None
        try:
            if continuation_token is not None:
                continuation = consume_fact_continuation(
                    continuation_token,
                    fact_supplement,
                )
                token_domain_list = [
                    str(value).strip()
                    for value in (continuation.get("domain_ids") or [continuation.get("domain_id")])
                    if str(value).strip()
                ]
                token_domains = set(token_domain_list)
                if domain_ids is not None and {
                    str(value).strip() for value in domain_ids if str(value).strip()
                } != token_domains:
                    raise ClarificationContinuationError(
                        "continuation domain selection does not match",
                        code="continuation_domain_mismatch",
                    )
                domain_ids = token_domain_list
            context_kwargs: dict[str, Any] = {
                "planner": planner_name,
                "backend": backend,
                "domain_ids": domain_ids,
            }
            if continuation is not None:
                context_kwargs["fact_overrides"] = continuation.get(
                    "fact_overrides"
                ) or {
                    str(continuation["domain_id"]): continuation["facts"]
                }
            context = self._context_builder.build(text, **context_kwargs)
            if continuation is not None and str(
                context.get("request_fingerprint") or ""
            ) != str(continuation.get("request_fingerprint") or ""):
                raise ClarificationContinuationError(
                    "continuation request fingerprint does not match",
                    code="continuation_request_mismatch",
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
                continuation=continuation,
            )
            result = self._attach_context(candidate, context)
            if continuation is not None:
                result["continuation"] = _continuation_evidence(continuation)
                evidence = dict(result.get("planner_evidence") or {})
                evidence["continuation"] = _continuation_evidence(continuation)
                result["planner_evidence"] = evidence
            return result
        except ClarificationContinuationError as exc:
            return self._attach_context(
                {
                    "schema_version": self.schema_version,
                    "status": "REJECTED",
                    "planner_source": planner_name[:32],
                    "message": "澄清续接无效，请重新提交原问题。",
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
                        requested_planner=planner_name,
                        selection_state="rejected",
                        selection_reason=exc.code,
                    ),
                },
                context,
            )
        except CompositeRequestContextError as exc:
            return self._context_error(exc, planner_name)
        except CompositePlannerError as exc:
            details = getattr(exc, "details", None)
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
                        continuation=continuation,
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
            provider_failed = exc.code == "planner_provider_failed"
            provider_failure = (
                details.get("provider_failure")
                if isinstance(details, Mapping)
                and isinstance(details.get("provider_failure"), Mapping)
                else {}
            )
            provider_failure_code = str(
                provider_failure.get("code") or exc.code
            )[:96]
            provider_failure_retryable = (
                provider_failure.get("retryable")
                if isinstance(provider_failure.get("retryable"), bool)
                else True
            )
            status = "FAILED" if provider_failed else "NEEDS_CLARIFICATION" if exc.code in {
                "planner_provider_failed",
                "planner_context_too_large",
                "plan_components_required",
                "capability_unavailable",
                "taskplan_component_clarification",
                "taskplan_composite_clarification",
                "component_facts_missing",
            } else "REJECTED"
            message = (
                "模型服务暂时不可用，尚未创建执行任务，请稍后重试。"
                if provider_failed
                else "无法安全生成可执行的组合计划，请补充信息或调整问题。"
            )
            next_actions = (
                ["稍后重试"]
                if provider_failed and provider_failure_retryable
                else ["检查模型配置"]
                if provider_failed
                else ["补充信息后重新提交"]
            )
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
            result = {
                "schema_version": self.schema_version,
                "status": status,
                "planner_source": planner_name[:32],
                "message": message,
                "error_code": exc.code,
                "components": [],
                "request": None,
                "validation": {"status": "failed", "reason_code": exc.code},
                "planner_evidence": failure_evidence,
                "repair_lineage": repair_lineage,
                "next_actions": next_actions,
            }
            if provider_failed:
                result["failure"] = build_failure_evidence(
                    status="FAILED",
                    category="provider",
                    code=provider_failure_code,
                    phase="planning",
                    retryable=provider_failure_retryable,
                )
            if isinstance(details, Mapping):
                composite_handoff = details.get("composite_fact_handoff")
                if isinstance(composite_handoff, Mapping):
                    result["composite_fact_handoff"] = dict(composite_handoff)
                    if isinstance(composite_handoff.get("continuation"), Mapping):
                        result["continuation"] = _continuation_descriptor(composite_handoff)
                    result["clarification"] = {
                        "schema_version": "spatial-agent.composite-clarification.v1",
                        "state": "composite_facts_required",
                        "reason_code": exc.code,
                        "component_ids": list(composite_handoff.get("component_ids") or [])[:8],
                        "missing_fields": list(composite_handoff.get("missing_fields") or [])[:64],
                        "next_actions": ["provide_facts"],
                    }
                handoff = details.get("component_fact_handoff")
                if isinstance(handoff, Mapping) and "clarification" not in result:
                    result["component_fact_handoff"] = dict(handoff)
                    if isinstance(handoff.get("continuation"), Mapping):
                        result["continuation"] = _continuation_descriptor(handoff)
                    result["clarification"] = {
                        "schema_version": "spatial-agent.component-clarification.v1",
                        "state": "component_facts_required",
                        "reason_code": exc.code,
                        "component_id": handoff.get("component_id"),
                        "domain_id": handoff.get("domain_id"),
                        "capability_id": handoff.get("capability_id"),
                        "missing_fields": list(handoff.get("missing_fields") or [])[:8],
                        "next_actions": ["provide_facts"],
                    }
            planning_failure = _planning_failure_projection(
                exc.code,
                status=status,
            )
            result["planning_failure"] = planning_failure
            failure_evidence["planning_failure"] = planning_failure
            if not provider_failed:
                result["failure"] = build_failure_evidence(
                    status=status,
                    code=exc.code,
                    phase="planning",
                    retryable=False,
                )
            if isinstance(result.get("continuation"), Mapping):
                failure_evidence["continuation"] = _continuation_evidence(
                    result["continuation"]
                )
                result["planner_evidence"] = failure_evidence
            return self._attach_context(result, context)
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
        continuation_token: str | None = None,
        fact_supplement: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        prepared = self.prepare(
            request,
            planner_name=planner_name,
            backend=backend,
            domain_ids=domain_ids,
            continuation_token=continuation_token,
            fact_supplement=fact_supplement,
        )
        if prepared.get("status") != "PLANNED":
            return prepared
        canonical = prepared.get("request")
        execution_binding = getattr(prepared, "execution_binding", None)
        if asynchronous:
            submit_with_evidence = getattr(
                self._composite_runs, "submit_async_with_planning", None
            )
            if callable(submit_with_evidence):
                execution = _call_optional_binding(
                    submit_with_evidence,
                    canonical,
                    execution_binding=execution_binding,
                    session_id=str(session_id or "default")[:120],
                    idempotency_key=idempotency_key,
                    export_artifact=bool(export_artifact),
                    planner_evidence=prepared.get("planner_evidence"),
                )
            else:
                execution = _call_optional_binding(
                    self._composite_runs.submit_async,
                    canonical,
                    execution_binding=execution_binding,
                    session_id=str(session_id or "default")[:120],
                    idempotency_key=idempotency_key,
                    export_artifact=bool(export_artifact),
                )
        else:
            run_with_evidence = getattr(self._composite_runs, "run_with_planning", None)
            if callable(run_with_evidence):
                execution = _call_optional_binding(
                    run_with_evidence,
                    canonical,
                    execution_binding=execution_binding,
                    session_id=str(session_id or "default")[:120],
                    export_artifact=bool(export_artifact),
                    planner_evidence=prepared.get("planner_evidence"),
                )
            else:
                execution = _call_optional_binding(
                    self._composite_runs.run,
                    canonical,
                    execution_binding=execution_binding,
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
        continuation: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(candidate, Mapping):
            raise CompositePlannerError("planner output must be an object", code="plan_object_required")
        status = str(candidate.get("status") or "").upper()
        if status != "PLANNED":
            planner_source = str(candidate.get("planner_source") or planner_name)[:32]
            result = {
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
            if result["status"] == "NEEDS_CLARIFICATION":
                raw_clarification = candidate.get("clarification")
                raw_clarification = (
                    raw_clarification
                    if isinstance(raw_clarification, Mapping)
                    else {}
                )
                result["clarification"] = {
                    "schema_version": "spatial-agent.selection-clarification.v1",
                    "state": "needs_clarification",
                    "reason_code": str(
                        raw_clarification.get("reason_code")
                        or _selection_reason_for_candidate(candidate, status)
                    )[:96],
                    "message": str(
                        raw_clarification.get("message")
                        or candidate.get("message")
                        or "请补充任务信息。"
                    )[:640],
                    "missing_fields": [
                        str(item)[:160]
                        for item in (raw_clarification.get("missing_fields") or [])[:8]
                        if str(item).strip()
                    ],
                    "next_actions": ["补充信息后重新提交"],
                }
            return result
        raw_request = inherit_composite_runtime_selection(
            candidate.get("request"),
            planner=planner_name,
            backend=backend,
        )
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
                "candidate TaskPlan failed the execution gate",
                code=exc.code,
                details=exc.details,
            ) from exc
        _validate_continuation_selection(
            continuation,
            context=context,
            components=projected,
            task_plan_bridge=task_plan_bridge,
        )
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
        try:
            execution_binding = build_execution_binding(
                canonical,
                projected,
                task_plan_bridge=task_plan_bridge,
                planner_name=planner_name,
                backend=backend,
            )
        except ExecutionBindingError as exc:
            raise CompositePlannerError(
                "candidate execution binding is invalid",
                code=exc.code,
                details=exc.details,
            ) from exc
        try:
            execution_envelope = build_execution_planner_envelope(
                context,
                components=projected,
                execution_binding=execution_binding,
            )
        except PlannerEnvelopeError as exc:
            raise CompositePlannerError(
                "candidate execution projection is invalid",
                code=exc.code,
            ) from exc
        planner_source = str(candidate.get("planner_source") or planner_name)[:32]
        compatibility = _safe_compatibility(candidate.get("compatibility"))
        result = _PreparedComposite({
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
            "execution_binding": project_execution_binding(execution_binding),
            "canonical_plan": build_canonical_plan_receipt(
                task_plan_bridge, execution_binding
            ),
        }, execution_binding=execution_binding)
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
        result["planner_evidence"]["execution_binding"] = project_execution_binding(
            execution_binding
        )
        result["planner_evidence"]["canonical_plan"] = result["canonical_plan"]
        result["planner_evidence"]["execution_projection"] = (
            project_planner_envelope_evidence(execution_envelope)
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
            if capability.get("plan_mode") == "unbound":
                raise CompositePlannerError(
                    "capability has no registered workflow",
                    code="capability_not_materializable",
                )
            discovery = context.get("discovery")
            if isinstance(discovery, Mapping):
                discovery_item = next(
                    (
                        value
                        for value in (discovery.get("candidates") or [])
                        if isinstance(value, Mapping)
                        and str(value.get("domain_id")) == domain_id
                        and str(value.get("capability_id")) == capability_id
                    ),
                    None,
                )
                if isinstance(discovery_item, Mapping) and not bool(
                    discovery_item.get("execution_ready")
                ):
                    state = str(discovery_item.get("state") or "unavailable")
                    code = (
                        "data_unavailable"
                        if state == "data_unavailable"
                        else str(
                            discovery_item.get("execution_reason_code")
                            or discovery_item.get("execution_readiness")
                            or "capability_unavailable"
                        )[:96]
                    )
                    raise CompositePlannerError(
                        "discovery candidate is not execution-ready", code=code
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
        binding = getattr(result, "execution_binding", None)
        projected = _PreparedComposite(
            dict(result),
            execution_binding=binding,
        ) if binding is not None else dict(result)
        projected["request_context"] = dict(context)
        evidence = dict(projected.get("planner_evidence") or {})
        evidence["context_fingerprint"] = str(
            context.get("request_fingerprint") or ""
        )[:128] or None
        evidence["context_schema_version"] = str(
            context.get("schema_version") or ""
        )[:96] or None
        discovery = context.get("discovery")
        if isinstance(discovery, Mapping):
            evidence["discovery"] = _project_discovery_evidence(discovery)
        analysis_intents = _project_analysis_intents(context)
        if analysis_intents:
            evidence["analysis_intents"] = analysis_intents
        envelope = context.get("planner_envelope")
        if isinstance(envelope, Mapping):
            limits = envelope.get("limits")
            selection = envelope.get("selection")
            evidence["planner_envelope"] = {
                "schema_version": str(envelope.get("schema_version") or "")[:96],
                "context_projection_stage": str(
                    envelope.get("projection_stage") or "unknown"
                )[:24],
                "provider_projection_stage": _provider_projection_stage(
                    evidence, envelope
                ),
                "layers": [
                    str(item)[:64]
                    for item in (envelope.get("layers") or [])[:8]
                    if str(item).strip()
                ],
                "max_bytes": (
                    limits.get("max_bytes")
                    if isinstance(limits, Mapping)
                    else None
                ),
                "candidate_count": (
                    selection.get("candidate_count")
                    if isinstance(selection, Mapping)
                    else None
                ),
                "redacted": bool(
                    (envelope.get("redaction") or {}).get("applied")
                    if isinstance(envelope.get("redaction"), Mapping)
                    else False
                ),
            }
            attempt = evidence.get("planner_attempt")
            if isinstance(attempt, Mapping):
                attempt_value = dict(attempt)
                budget = dict(attempt_value.get("budget") or {})
                encoded = json.dumps(
                    envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                budget.setdefault("envelope_bytes", len(encoded.encode("utf-8")))
                if isinstance(limits, Mapping):
                    budget.setdefault("envelope_max_bytes", limits.get("max_bytes"))
                attempt_value["budget"] = budget
                lineage = projected.get("repair_lineage")
                if isinstance(lineage, Mapping):
                    attempt_value["repair"] = lineage
                projected_attempt = project_planner_attempt_receipt(attempt_value)
                if projected_attempt is not None:
                    evidence["planner_attempt"] = projected_attempt
        evidence["selection_evidence"] = project_selection_evidence(
            context,
            existing_selection=(
                evidence.get("selection")
                if isinstance(evidence.get("selection"), Mapping)
                else None
            ),
            existing_clarification=(
                projected.get("clarification")
                if isinstance(projected.get("clarification"), Mapping)
                else None
            ),
        )
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




from agent.application.composite_planning_projection import (
    _aggregate_readiness,
    _bounded_strings,
    _bounded_text,
    _call_catalog,
    _call_execution_contract,
    _call_optional_binding,
    _call_runtime_capabilities,
    _call_workflow,
    _capability_keys,
    _context_candidate_count,
    _continuation_descriptor,
    _continuation_evidence,
    _planner_attempt_outcome,
    _planner_evidence,
    _planner_selection_evidence,
    _planning_failure_projection,
    _positive_limit,
    _profiles_for_results,
    _project_analysis_intents,
    _project_capability,
    _project_discovery_evidence,
    _project_execution_contract,
    _project_operation_binding,
    _project_profile_list,
    _project_readiness,
    _project_requirements,
    _project_result_profiles,
    _project_workflow,
    _provider_projection_stage,
    _safe_compatibility,
    _safe_planner_metrics,
    _selected_domain_ids,
    _selection_reason_for_candidate,
    _selection_state_for_status,
    _validate_continuation_selection,
)
