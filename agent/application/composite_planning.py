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

from agent.composite_contract import (
    inherit_composite_runtime_selection,
    normalize_composite_request,
)
from agent.composite_request_context import (
    COMPOSITE_REQUEST_CONTEXT_MAX_BYTES,
    CompositeRequestContextBuilder,
    CompositeRequestContextError,
)
from agent.composite_planner import CompositePlannerError
from agent.failure_contract import build_failure_evidence
from agent.planner_repair import (
    build_planner_repair_request,
    build_repair_lineage,
    is_repairable_planner_error,
)
from agent.provider_structured_output import project_structured_output_evidence
from agent.provider_runtime import (
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
_SAFE_READINESS_FIELDS = (
    "status",
    "coverage",
    "time_range",
    "crs",
    "resolution",
    "availability_reason",
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


def _project_discovery_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Expose only receipt identity and bounded readiness counts to results."""

    candidates = [
        item for item in (value.get("candidates") or []) if isinstance(item, Mapping)
    ]
    states: dict[str, int] = {}
    for item in candidates:
        state = str(item.get("state") or "unknown")[:32]
        states[state] = states.get(state, 0) + 1
    requirements = [
        item
        for item in (value.get("data_requirements") or [])
        if isinstance(item, Mapping)
    ]
    receipt_evidence = value.get("evidence")
    domain_count = len(value.get("domains") or [])
    if isinstance(receipt_evidence, Mapping):
        try:
            domain_count = int(receipt_evidence.get("domain_count") or domain_count)
        except (TypeError, ValueError):
            pass
    return {
        "schema_version": str(value.get("schema_version") or "")[:96],
        "request_fingerprint": str(value.get("request_fingerprint") or "")[:128],
        "discovery_fingerprint": str(value.get("discovery_fingerprint") or "")[:128],
        "state": str(value.get("state") or "unknown")[:32],
        "reason_code": str(value.get("reason_code") or "unknown")[:96],
        "domain_count": max(0, min(8, domain_count)),
        "candidate_count": max(0, min(16, len(candidates))),
        "data_requirement_count": max(0, min(64, len(requirements))),
        "candidate_states": states,
        "next_actions": [str(item)[:160] for item in (value.get("next_actions") or [])[:4]],
    }


def _validate_continuation_selection(
    continuation: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any],
    components: Sequence[Any],
    task_plan_bridge: Mapping[str, Any],
) -> None:
    """Ensure a resumed request cannot switch component identity silently."""

    if continuation is None:
        return
    if str(continuation.get("schema_version") or "") == "spatial-agent.composite-clarification-continuation.v1":
        expected_components = {
            str(item.get("component_id")): item
            for item in (continuation.get("components") or [])
            if isinstance(item, Mapping) and str(item.get("component_id") or "")
        }
        selected_components = {
            str(item.get("component_id")): item
            for item in components
            if isinstance(item, Mapping) and str(item.get("component_id") or "")
        }
        if set(expected_components) != set(selected_components) or not expected_components:
            raise CompositePlannerError(
                "continuation component set does not match",
                code="continuation_component_mismatch",
            )
        bridge_by_id = {
            str(item.get("component_id")): item
            for item in (task_plan_bridge.get("components") or [])
            if isinstance(item, Mapping) and str(item.get("component_id") or "")
        }
        if set(bridge_by_id) != set(expected_components):
            raise CompositePlannerError(
                "continuation TaskPlan component set is unavailable",
                code="continuation_component_mismatch",
            )
        for component_id, expected_component in expected_components.items():
            actual_component = selected_components[component_id]
            if (
                str(actual_component.get("domain_id") or "")
                != str(expected_component.get("domain_id") or "")
                or str(actual_component.get("capability_id") or "")
                != str(expected_component.get("capability_id") or "")
            ):
                raise CompositePlannerError(
                    "continuation capability identity does not match",
                    code="continuation_capability_mismatch",
                )
        bridge_handoff = task_plan_bridge.get("fact_handoff")
        actual = (
            str(bridge_handoff.get("planner_selection_fingerprint") or "")
            if isinstance(bridge_handoff, Mapping)
            else ""
        )
        expected = str(continuation.get("planner_selection_fingerprint") or "")
        if not expected or actual != expected:
            raise CompositePlannerError(
                "continuation planner selection does not match",
                code="continuation_selection_mismatch",
            )
        if str(context.get("request_fingerprint") or "") != str(
            continuation.get("request_fingerprint") or ""
        ):
            raise CompositePlannerError(
                "continuation request fingerprint does not match",
                code="continuation_request_mismatch",
            )
        return
    component_id = str(continuation.get("component_id") or "")
    domain_id = str(continuation.get("domain_id") or "")
    capability_id = str(continuation.get("capability_id") or "")
    selected = [
        item
        for item in components
        if isinstance(item, Mapping)
        and str(item.get("component_id") or "") == component_id
    ]
    if len(selected) != 1:
        raise CompositePlannerError(
            "continuation component is not selected exactly once",
            code="continuation_component_mismatch",
        )
    component = selected[0]
    if str(component.get("domain_id") or "") != domain_id or str(
        component.get("capability_id") or ""
    ) != capability_id:
        raise CompositePlannerError(
            "continuation capability identity does not match",
            code="continuation_capability_mismatch",
        )
    bridge_components = [
        item
        for item in (task_plan_bridge.get("components") or [])
        if isinstance(item, Mapping)
        and str(item.get("component_id") or "") == component_id
    ]
    if len(bridge_components) != 1:
        raise CompositePlannerError(
            "continuation TaskPlan identity is unavailable",
            code="continuation_component_mismatch",
        )
    handoff = bridge_components[0].get("fact_handoff")
    actual = (
        str(handoff.get("planner_selection_fingerprint") or "")
        if isinstance(handoff, Mapping)
        else ""
    )
    expected = str(continuation.get("planner_selection_fingerprint") or "")
    if not expected or actual != expected:
        raise CompositePlannerError(
            "continuation planner selection does not match",
            code="continuation_selection_mismatch",
        )
    if str(context.get("request_fingerprint") or "") != str(
        continuation.get("request_fingerprint") or ""
    ):
        raise CompositePlannerError(
            "continuation request fingerprint does not match",
            code="continuation_request_mismatch",
        )


def _continuation_descriptor(handoff: Mapping[str, Any]) -> dict[str, Any]:
    continuation = dict(handoff.get("continuation") or {})
    for key in (
        "request_fingerprint",
        "planner_selection_fingerprint",
        "component_id",
        "domain_id",
        "capability_id",
        "component_ids",
        "domain_ids",
    ):
        if key in handoff:
            continuation[key] = handoff[key]
    return continuation


def _continuation_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "schema_version": str(value.get("schema_version") or "")[:96],
        "request_fingerprint": str(value.get("request_fingerprint") or "")[:128],
        "planner_selection_fingerprint": str(
            value.get("planner_selection_fingerprint") or ""
        )[:128],
        "component_id": str(value.get("component_id") or "")[:96],
        "domain_id": str(value.get("domain_id") or "")[:64],
        "capability_id": str(value.get("capability_id") or "")[:96],
        "field_ids": [
            str(item)[:80]
            for item in (value.get("field_ids") or [])[:16]
            if str(item).strip()
        ],
    }
    if result["schema_version"] == "spatial-agent.composite-clarification-continuation.v1":
        result["component_ids"] = [
            str(item)[:96]
            for item in (value.get("component_ids") or [])[:8]
            if str(item).strip()
        ]
        result["domain_ids"] = [
            str(item)[:64]
            for item in (value.get("domain_ids") or [])[:8]
            if str(item).strip()
        ]
        result["components"] = [
            {
                "component_id": str(item.get("component_id") or "")[:96],
                "domain_id": str(item.get("domain_id") or "")[:64],
                "capability_id": str(item.get("capability_id") or "")[:96],
            }
            for item in (value.get("components") or [])[:8]
            if isinstance(item, Mapping)
        ]
        result.pop("component_id", None)
        result.pop("domain_id", None)
        result.pop("capability_id", None)
        result.pop("field_ids", None)
    return result


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
    provider_runtime = project_provider_runtime_evidence(provider_metrics)
    if provider_runtime is not None:
        result["provider_runtime"] = provider_runtime
    provider_stage = (
        provider_metrics.get("projection_stage")
        if isinstance(provider_metrics, Mapping)
        else None
    )
    planner_attempt = build_planner_attempt_receipt(
        provider_metrics,
        stage=provider_stage
        or ("selection" if str(planner_source or "") == "llm" else "discovery"),
        outcome=_planner_attempt_outcome(
            schema_status=schema_status,
            selection_state=selection_state,
            provider_metrics=provider_metrics,
        ),
        reason_code=selection_reason,
    )
    if planner_attempt is not None:
        result["planner_attempt"] = planner_attempt
    return result


def _planner_attempt_outcome(
    *,
    schema_status: Any,
    selection_state: Any,
    provider_metrics: Mapping[str, Any] | None,
) -> str | None:
    """Keep provider completion separate from the planner's semantic outcome."""

    if str(schema_status or "") == "valid":
        return "success"
    state = str(selection_state or "").strip().lower()
    if state == "clarification":
        return "needs_clarification"
    if state in {"rejected", "failed"}:
        metrics = provider_metrics if isinstance(provider_metrics, Mapping) else {}
        if metrics.get("error_type") or str(metrics.get("status") or "").lower() in {
            "error",
            "failed",
            "timed_out",
        }:
            return "provider_failure"
        return "rejected"
    return None


def _provider_projection_stage(
    evidence: Mapping[str, Any], envelope: Mapping[str, Any]
) -> str:
    """Describe the stage actually used by the planner adapter."""

    lineage = evidence.get("repair_lineage")
    if isinstance(lineage, Mapping) and bool(lineage.get("attempted")):
        return "repair"
    if str(evidence.get("planner_source") or "") == "llm":
        return "selection"
    # Rule and Replay are local adapters and do not cross the provider
    # boundary; their shared context was produced from the discovery stage.
    return str(envelope.get("projection_stage") or "discovery")[:24]


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


def _call_execution_contract(
    service: Any, *, planner: str, backend: str
) -> Mapping[str, Any]:
    """Read the optional structural Runtime contract without executing tools."""

    resolver = getattr(service, "execution_contract", None)
    if not callable(resolver):
        return {}
    value = resolver(planner=planner, backend=backend)
    return value if isinstance(value, Mapping) else {}


def _call_runtime_capabilities(
    service: Any, *, planner: str, backend: str
) -> Mapping[str, Any]:
    """Read bounded current data readiness when a Domain exposes it."""

    resolver = getattr(service, "runtime_capabilities", None)
    if not callable(resolver):
        return {}
    try:
        value = resolver(max_files=2, planner=planner, backend=backend)
    except TypeError:
        # Keep compatibility with older services that only accept max_files.
        try:
            value = resolver(max_files=2)
        except Exception:
            return {}
    except Exception:
        return {}
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
        "input_profiles": _project_profile_list(value.get("input_profiles")),
        "output_profiles": _project_profile_list(value.get("output_profiles")),
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


def _project_execution_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the bounded closure facts needed by catalog readiness."""

    if not isinstance(value, Mapping) or not value:
        return {}
    tool_definitions = value.get("tool_definitions")
    tool_names = _bounded_strings(value.get("tool_names"), limit=64)
    if isinstance(tool_definitions, Mapping):
        tool_names = _bounded_strings(
            list(tool_names) + list(tool_definitions.keys()), limit=64
        )
    result = {
        "schema_version": _bounded_text(value.get("schema_version"), 96),
        "status": _bounded_text(value.get("status"), 24) or "unknown",
        "domain_id": _bounded_text(value.get("domain_id"), 64),
        "tool_names": tool_names,
        "result_type_ids": _bounded_strings(value.get("result_type_ids"), limit=64),
    }
    if isinstance(value.get("tool_definitions"), Mapping):
        result["tool_schema_count"] = min(64, len(value["tool_definitions"]))
    result["result_profiles"] = _project_result_profiles(value.get("result_profiles"))
    if value.get("result_registry_schema_version"):
        result["result_registry_schema_version"] = _bounded_text(
            value.get("result_registry_schema_version"), 96
        )
    return result


def _project_result_profiles(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for result_type, raw in list(value.items())[:64]:
        if not isinstance(raw, Mapping):
            continue
        kinds = _bounded_strings(raw.get("kinds"), limit=8)
        primary = _bounded_text(raw.get("primary"), 32)
        if not kinds:
            kinds = [primary or "unknown"]
        if primary not in kinds:
            primary = kinds[0]
        result[_bounded_text(result_type, 96)] = {
            "schema_version": _bounded_text(raw.get("schema_version"), 96)
            or "spatial-agent.data-profile.v1",
            "primary": primary,
            "kinds": kinds,
        }
    return {key: value for key, value in result.items() if key}


def _profiles_for_results(value: Any, profiles: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for result_type in _bounded_strings(value, limit=24):
        profile = profiles.get(result_type)
        if not isinstance(profile, Mapping):
            continue
        result.append({"result_type": result_type, **dict(profile)})
    return result[:24]


def _project_profile_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for raw in list(value)[:24]:
        if not isinstance(raw, Mapping):
            continue
        name = _bounded_text(raw.get("name") or raw.get("input"), 64)
        kinds = _bounded_strings(raw.get("kinds") or raw.get("data_kinds"), limit=8)
        if not kinds:
            continue
        item = {"kinds": kinds}
        if name:
            item["name"] = name
        result.append(item)
    return result


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


def _call_optional_binding(method: Any, value: Any, *, execution_binding: Any, **kwargs: Any) -> Any:
    """Call old injected run ports without weakening the production seam."""

    if execution_binding is not None:
        try:
            parameters = inspect.signature(method).parameters
            accepts = "execution_binding" in parameters or any(
                item.kind == inspect.Parameter.VAR_KEYWORD
                for item in parameters.values()
            )
        except (TypeError, ValueError):
            accepts = True
        if accepts:
            kwargs["execution_binding"] = execution_binding
    return method(value, **kwargs)


__all__ = [
    "COMPOSITE_PLANNER_CONTEXT_SCHEMA_VERSION",
    "CompositeCapabilityProjector",
]
