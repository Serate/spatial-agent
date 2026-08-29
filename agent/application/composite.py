"""Transport-neutral execution coordinator for bounded Composite requests.

The coordinator owns only cross-component orchestration.  Each component is
still executed by the Domain Service returned by ``DomainRuntimeHost``; this
module does not plan tools, dispatch tools, or reproduce the Runtime
lifecycle.  HTTP, async and persistence adapters can call this seam later.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from agent.application.composite_contract import (
    CompositeContractError,
    build_composite_result_contract,
    normalize_composite_request,
)
from agent.contract_versions import COMPOSITE_COORDINATOR_SCHEMA_VERSION
from agent.domain_registry import DomainSelectionError
from agent.runtime_core.execution_binding import (
    ExecutionBindingError,
    component_binding,
    project_execution_binding,
    task_plan_from_binding,
    validate_component_result,
    validate_execution_binding,
)
from agent.runtime_core.composition import (
    CompositionError,
    resolve_component_input_handoff,
)


_MAX_RECEIPTS = 8
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_ACTIVE_STATUSES = {"QUEUED", "PLANNING", "EXECUTING"}
_COMPLETED = "COMPLETED"


class CompositeCoordinatorError(ValueError):
    """A Composite request cannot be safely resolved or executed."""

    def __init__(self, message: str, *, code: str = "composite_coordinator_invalid"):
        self.code = str(code)[:96]
        super().__init__(message)


class CompositeApplication:
    """Execute normalized Composite components through an allowlisted Host."""

    schema_version = COMPOSITE_COORDINATOR_SCHEMA_VERSION

    def __init__(self, *, host: Any, require_execution_binding: bool = False) -> None:
        if host is None or not callable(getattr(host, "select", None)) or not callable(
            getattr(host, "service", None)
        ):
            raise ValueError("host must expose select() and service()")
        self._host = host
        # Legacy direct coordinator callers remain supported during the
        # migration. Production HTTP composition enables this gate explicitly;
        # all planner-produced submissions carry a binding.
        self._require_execution_binding = bool(require_execution_binding)

    def run(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str = "default",
        run_id: str | None = None,
        execution_binding: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run components in declaration order and return one bounded result."""

        normalized = normalize_composite_request(request)
        binding = None
        if execution_binding is not None or self._require_execution_binding:
            try:
                binding = validate_execution_binding(
                    execution_binding,
                    request=normalized,
                )
            except ExecutionBindingError as exc:
                raise CompositeCoordinatorError(
                    "composite execution binding was rejected",
                    code=exc.code,
                ) from exc
        parent_session = _bounded_session(session_id)
        receipts: dict[str, dict[str, Any]] = {}
        children: dict[str, dict[str, Any]] = {}

        for component in normalized["components"][:_MAX_RECEIPTS]:
            component_id = component["component_id"]
            dependencies = list(component.get("depends_on") or [])
            blocked_by = [
                dependency
                for dependency in dependencies
                if receipts.get(dependency, {}).get("state") != "completed"
            ]
            if blocked_by:
                child = self._blocked_child(component, blocked_by)
                children[component_id] = child
                receipts[component_id] = self._receipt(
                    component,
                    child,
                    state="blocked",
                    error_code="component_dependency_blocked",
                    dependency_ids=blocked_by,
                )
                continue

            try:
                # Selection errors are request-level authorization failures;
                # they must not be downgraded to a partial execution.
                selection = self._select(component["domain_id"])
            except CompositeCoordinatorError:
                raise

            try:
                component_inputs = resolve_component_input_handoff(
                    component,
                    children,
                )
            except CompositionError as exc:
                child = self._input_blocked_child(component, exc)
                children[component_id] = child
                receipts[component_id] = self._receipt(
                    component,
                    child,
                    state="blocked",
                    error_code=exc.code,
                )
                continue

            try:
                service = self._host.service(selection)
                bound_component = (
                    component_binding(binding, component_id)
                    if binding is not None
                    else None
                )
                child = self._run_service(
                    service,
                    component,
                    binding_component=bound_component,
                    component_inputs=component_inputs,
                    session_id=_component_session(
                        parent_session,
                        normalized["fingerprint"],
                        component_id,
                    ),
                )
                if bound_component is not None:
                    try:
                        validate_component_result(bound_component, child)
                    except ExecutionBindingError as exc:
                        raise CompositeCoordinatorError(
                            "component result did not satisfy execution binding",
                            code=exc.code,
                        ) from exc
                    child = dict(child)
                    child["_execution_evidence"] = {
                        "schema_version": "spatial-agent.execution-binding-evidence.v1",
                        "binding_fingerprint": binding["binding_fingerprint"],
                        "plan_fingerprint": bound_component["plan_fingerprint"],
                        "component_id": component_id,
                        "step_ids": [
                            str(item.get("id") or "")[:48]
                            for item in (bound_component.get("plan", {}).get("steps") or [])
                            if isinstance(item, Mapping)
                        ],
                    }
                state = _child_state(child.get("status"))
                if state == "completed":
                    children[component_id] = child
                    receipts[component_id] = self._receipt(component, child, state=state)
                else:
                    children[component_id] = child
                    receipts[component_id] = self._receipt(
                        component,
                        child,
                        state=state,
                        error_code=_child_error_code(child),
                    )
            except CompositeCoordinatorError:
                raise
            except Exception as exc:
                child = self._failed_child(component, exc)
                children[component_id] = child
                receipts[component_id] = self._receipt(
                    component,
                    child,
                    state="failed",
                    error_code=_safe_error_code(exc),
                )

        effective_run_id = run_id or (
            "composite-" + normalized["fingerprint"].split(":", 1)[-1][:24]
        )
        result = build_composite_result_contract(
            normalized,
            children,
            run_id=effective_run_id,
            execution_binding=project_execution_binding(binding) if binding is not None else None,
        )
        state = str(result.get("composite", {}).get("state") or "failed")
        response = {
            "schema_version": self.schema_version,
            "run_id": effective_run_id,
            "status": _coordinator_status(state),
            "state": state,
            "request_fingerprint": normalized["fingerprint"],
            "components": list(receipts.values())[:_MAX_RECEIPTS],
            "result": result,
        }
        if binding is not None:
            response["execution_binding"] = project_execution_binding(binding)
        return response

    def _select(self, domain_id: str) -> Any:
        """Resolve a Domain only through Host selection and allowlist checks."""

        try:
            return self._host.select(domain_id, source="explicit")
        except DomainSelectionError as exc:
            raise CompositeCoordinatorError(
                "composite domain is not enabled",
                code=str(getattr(exc, "code", "domain_not_allowed"))[:96],
            ) from exc
        except Exception as exc:
            raise CompositeCoordinatorError(
                "composite domain selection failed",
                code="domain_selection_failed",
            ) from exc

    @staticmethod
    def _run_service(
        service: Any,
        component: Mapping[str, Any],
        *,
        binding_component: Mapping[str, Any] | None = None,
        component_inputs: Mapping[str, Any] | None = None,
        session_id: str,
    ) -> dict[str, Any]:
        runner = getattr(service, "run", None)
        if not callable(runner):
            raise CompositeCoordinatorError(
                "selected Domain service cannot run",
                code="domain_service_unavailable",
            )
        kwargs: dict[str, Any] = {
            "request": component["request"],
            "session_id": session_id,
            "planner": component["planner"],
            "backend": component["backend"],
        }
        if binding_component is not None:
            if not _accepts_keyword(runner, "validated_plan"):
                raise CompositeCoordinatorError(
                    "Domain service cannot consume a validated execution plan",
                    code="domain_service_binding_unsupported",
                )
            kwargs["validated_plan"] = task_plan_from_binding(binding_component)
            if isinstance(binding_component.get("workflow"), Mapping):
                kwargs["workflow"] = dict(binding_component["workflow"])
        elif isinstance(component.get("workflow"), Mapping):
            kwargs["workflow"] = dict(component["workflow"])
        input_evidence = {
            "schema_version": "spatial-agent.component-input-evidence.v1",
            "state": "not_required",
            "input_names": [],
        }
        if isinstance(component_inputs, Mapping) and component_inputs.get("state") == "ready":
            items = [
                item
                for item in (component_inputs.get("items") or [])
                if isinstance(item, Mapping)
            ]
            input_evidence["input_names"] = [
                str(item.get("name") or "")[:160]
                for item in items[:8]
                if str(item.get("name") or "").strip()
            ]
            if _accepts_keyword(runner, "component_inputs"):
                kwargs["component_inputs"] = dict(component_inputs)
                input_evidence["state"] = "delivered"
            else:
                # Old Domain services remain callable, but the public receipt
                # must make a missing consumer port visible instead of
                # claiming that a typed input was consumed.
                input_evidence["state"] = "not_consumed"
        value = runner(**kwargs)
        if not isinstance(value, Mapping):
            raise CompositeCoordinatorError(
                "Domain service returned an invalid result",
                code="domain_result_invalid",
            )
        child = dict(value)
        child.setdefault("domain_id", component["domain_id"])
        child["_component_input_evidence"] = input_evidence
        return child

    @staticmethod
    def _input_blocked_child(
        component: Mapping[str, Any], exc: CompositionError
    ) -> dict[str, Any]:
        return {
            "domain_id": component["domain_id"],
            "status": "NEEDS_CLARIFICATION",
            "error_code": str(exc.code)[:96],
            "error": "组件输入尚未满足，无法安全执行该组件。",
        }

    @staticmethod
    def _blocked_child(
        component: Mapping[str, Any],
        blocked_by: list[str],
    ) -> dict[str, Any]:
        return {
            "domain_id": component["domain_id"],
            "status": "NEEDS_CLARIFICATION",
            "error_code": "component_dependency_blocked",
            "error": "组件依赖未完成：" + ", ".join(blocked_by[:_MAX_RECEIPTS]),
        }

    @staticmethod
    def _failed_child(component: Mapping[str, Any], exc: Exception) -> dict[str, Any]:
        return {
            "domain_id": component["domain_id"],
            "status": "FAILED",
            "error_code": _safe_error_code(exc),
            "error": "组件执行失败，详细信息保留在受限执行证据中。",
        }

    @staticmethod
    def _receipt(
        component: Mapping[str, Any],
        child: Mapping[str, Any],
        *,
        state: str,
        error_code: str | None = None,
        dependency_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        nested = child.get("result") if isinstance(child.get("result"), Mapping) else {}
        receipt: dict[str, Any] = {
            "component_id": component["component_id"],
            "domain_id": component["domain_id"],
            "required": bool(component.get("required", True)),
            "state": state,
            "status": str(child.get("status") or "FAILED")[:32],
            "result_type": str(
                nested.get("type") or child.get("result_type") or "unknown"
            )[:96],
        }
        run_id = _safe_name(child.get("run_id"))
        if run_id:
            receipt["run_id"] = run_id
        if error_code:
            receipt["error_code"] = str(error_code)[:96]
        if dependency_ids:
            receipt["blocked_by"] = [str(item)[:48] for item in dependency_ids[:_MAX_RECEIPTS]]
        execution = child.get("_execution_evidence")
        if isinstance(execution, Mapping):
            receipt["execution"] = {
                "schema_version": str(execution.get("schema_version") or "")[:96],
                "binding_fingerprint": str(execution.get("binding_fingerprint") or "")[:128],
                "plan_fingerprint": str(execution.get("plan_fingerprint") or "")[:128],
                "component_id": str(execution.get("component_id") or "")[:48],
                "step_ids": [str(item)[:48] for item in (execution.get("step_ids") or [])[:_MAX_RECEIPTS]],
            }
        input_evidence = child.get("_component_input_evidence")
        if isinstance(input_evidence, Mapping):
            receipt["input_evidence"] = {
                "schema_version": str(input_evidence.get("schema_version") or "")[:96],
                "state": str(input_evidence.get("state") or "unknown")[:32],
                "input_names": [
                    str(item)[:160]
                    for item in (input_evidence.get("input_names") or [])[:8]
                    if isinstance(item, str)
                ],
            }
        return receipt


def _child_state(status: Any) -> str:
    normalized = str(status or "").upper()
    if normalized == _COMPLETED:
        return "completed"
    if normalized in _ACTIVE_STATUSES:
        return "pending"
    if normalized in {"NEEDS_CLARIFICATION", "WAITING_FOR_DECISION", "BLOCKED"}:
        return "blocked"
    return "failed"


def _coordinator_status(state: str) -> str:
    return {
        "completed": "COMPLETED",
        "partial": "PARTIAL",
        "blocked": "BLOCKED",
        "failed": "FAILED",
    }.get(state, "FAILED")


def _child_error_code(child: Mapping[str, Any]) -> str:
    return str(child.get("error_code") or child.get("code") or "component_not_completed")[:96]


def _safe_error_code(exc: Exception) -> str:
    value = getattr(exc, "code", None)
    if value:
        return str(value)[:96]
    return "component_execution_failed"


def _safe_name(value: Any) -> str | None:
    candidate = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    return candidate[:160] if _SAFE_ID.fullmatch(candidate) else None


def _bounded_session(value: Any) -> str:
    session = str(value or "default").strip()
    return session[:120] or "default"


def _component_session(parent: str, fingerprint: str, component_id: str) -> str:
    digest = hashlib.sha256(
        (parent + "|" + fingerprint + "|" + component_id).encode("utf-8")
    ).hexdigest()[:24]
    return "composite-" + digest + "-" + component_id[:40]


def _accepts_keyword(method: Any, name: str) -> bool:
    try:
        import inspect

        parameters = inspect.signature(method).parameters
        return name in parameters or any(
            item.kind == inspect.Parameter.VAR_KEYWORD
            for item in parameters.values()
        )
    except (TypeError, ValueError):
        return False


__all__ = [
    "COMPOSITE_COORDINATOR_SCHEMA_VERSION",
    "CompositeApplication",
    "CompositeCoordinatorError",
]
