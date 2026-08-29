"""Canonical Domain action application use case.

This module owns the transport-neutral action lifecycle: bounded dispatch,
idempotent replay, artifact publication, execution records and observability.
The selected Domain Pack remains behind the Runtime adapter supplied by the
caller.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Mapping, Optional

from agent.action_contract import ActionContractError
from agent.action_effect import project_action_effect
from agent.action_identity import (
    build_action_receipt_identity_linkage,
    build_action_transition_identity_from_linkages,
)
from agent.action_lineage import append_action_lineage
from agent.action_precondition import project_action_preconditions
from agent.persistence.artifact_store import ArtifactStore
from agent.evidence.revalidation import build_evidence_revalidation
from agent.execution_contract import build_execution_record
from agent.execution_timeline import attach_action_receipt_timeline
from agent.recovery_action import action_input_fingerprint
from agent.transition_evidence import (
    build_transition_evidence,
    project_transition_evidence,
)
from agent.recovery_action import project_action_receipt, project_legacy_interaction_receipt
from result_contract import build_action_result_contract


def _runtime_result_registry(runtime: Any) -> Any:
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


def _action_result_type(runtime: Any, action_id: str) -> str:
    """Resolve a declared action result type without reflecting methods."""
    resolver = getattr(runtime, "domain_actions", None)
    catalog = resolver() if callable(resolver) else {}
    for item in (catalog.get("actions", []) if isinstance(catalog, dict) else []):
        if isinstance(item, dict) and str(item.get("id") or "") == action_id:
            return str(item.get("result_type") or "action_result")[:96]
    return "action_result"


def _action_response_from_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    response = dict(artifact.get("action_result") or {})
    response.update(
        {
            "action_id": artifact.get("action_id"),
            "domain_id": artifact.get("domain_id"),
            "runtime_context": artifact.get("runtime_context"),
            "status": artifact.get("status"),
            "action_execution_id": artifact.get("action_execution_id"),
            "action_execution": artifact.get("action_execution"),
            "idempotency_key": artifact.get("idempotency_key"),
            "trace_summary": artifact.get("trace_summary") or [],
            "artifact_ref": artifact.get("artifact_ref"),
            "result": artifact.get("result"),
            "idempotency_reused": True,
            "execution_record": artifact.get("execution_record")
            or build_execution_record(artifact, kind="action"),
        }
    )
    if artifact.get("error"):
        response["error"] = artifact["error"]
    if artifact.get("action_error_code"):
        response["action_error_code"] = artifact["action_error_code"]
    return response


class ActionApplication:
    """Execute declared Domain actions through one deep application seam."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        state: Any,
        runtime_provider: Callable[[str, str], Any],
        runtime_context_provider: Callable[[str, str], Optional[Dict[str, Any]]],
        domain_id_provider: Callable[[str, str], str],
        resolved_domain_id: Callable[[], Optional[str]],
        action_context_provider: Callable[[], Any],
        get_run_provider: Callable[[str, str, str], Dict[str, Any]],
        memory_result_provider: Callable[[str], Any],
    ) -> None:
        self._artifact_store = artifact_store
        self._state = state
        self._runtime_provider = runtime_provider
        self._runtime_context_provider = runtime_context_provider
        self._domain_id_provider = domain_id_provider
        self._resolved_domain_id = resolved_domain_id
        self._action_context_provider = action_context_provider
        self._get_run_provider = get_run_provider
        self._memory_result_provider = memory_result_provider

    def execute(
        self,
        action_id: str,
        payload: Dict[str, Any],
        planner: str = "rule",
        backend: str = "local",
        idempotency_key: str = None,
    ) -> Dict[str, Any]:
        """Execute and durably observe one declared Domain action."""
        runtime = self._runtime_provider(planner, backend)
        resolver = getattr(runtime, "execute_domain_action", None)
        if not callable(resolver):
            raise ValueError("domain action execution is unavailable")
        domain_id = self._domain_id_provider(planner, backend)
        runtime_context = self._runtime_context_provider(planner, backend)
        action_id = str(action_id or "")[:96]
        action_payload = dict(payload) if isinstance(payload, dict) else payload
        if isinstance(action_payload, dict):
            action_payload.pop("idempotency_key", None)
        if idempotency_key is None and isinstance(payload, dict):
            idempotency_key = payload.get("idempotency_key")
        if idempotency_key is not None:
            idempotency_key = str(idempotency_key).strip()
            if (
                not idempotency_key
                or len(idempotency_key) > 128
                or "/" in idempotency_key
                or "\\" in idempotency_key
            ):
                raise ValueError("idempotency_key must be a safe non-empty value")
        input_fingerprint = action_input_fingerprint(action_id, action_payload)
        if idempotency_key:
            existing = self._artifact_store.find_action_by_idempotency_key(
                idempotency_key, domain_id=domain_id
            )
            if existing is not None:
                if existing.get("input_fingerprint") != input_fingerprint:
                    raise ActionContractError(
                        "idempotency_key conflicts with a previous action input",
                        action_id=action_id,
                        code="idempotency_conflict",
                    )
                if existing.get("status") == "FAILED":
                    error = ActionContractError(
                        str(existing.get("error") or "action execution failed"),
                        action_id=action_id,
                        code=str(
                            existing.get("action_error_code")
                            or "action_execution_failed"
                        ),
                    )
                    error.action_execution_id = existing.get("action_execution_id")
                    error.artifact_ref = existing.get("artifact_ref")
                    error.action_execution = existing.get("action_execution")
                    error.execution_record = existing.get("execution_record") or build_execution_record(
                        existing, kind="action"
                    )
                    raise error
                return _action_response_from_artifact(existing)

        execution_id = "action-" + uuid.uuid4().hex
        catalog = runtime.capability_catalog()
        domain_id = str(catalog.get("domain_id") or domain_id)[:80]
        result_type = _action_result_type(runtime, action_id)
        started = time.perf_counter()
        try:
            result = resolver(
                action_id,
                action_payload,
                context=self._action_context_provider(),
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            action_error_code = str(
                getattr(exc, "code", "action_execution_failed")
            )[:96]
            try:
                setattr(exc, "action_id", action_id)
                if not getattr(exc, "code", None):
                    setattr(exc, "code", action_error_code)
            except Exception:
                pass
            record = {
                "action_execution_id": execution_id,
                "action_id": action_id,
                "domain_id": domain_id,
                "runtime_context": runtime_context,
                "idempotency_key": idempotency_key,
                "input_fingerprint": input_fingerprint,
                "status": "FAILED",
                "result_type": result_type,
                "error": str(exc),
                "error_code": "action_execution_failed",
                "action_error_code": action_error_code,
                "action_result": {},
                "action_execution": {
                    "schema_version": "spatial-agent.action-execution.v1",
                    "status": "FAILED",
                    "action_id": action_id,
                    "input_validated": action_error_code != "action_invalid_input",
                    "error_code": action_error_code,
                    "duration_ms": duration_ms,
                },
                "trace_summary": [
                    "Received action: " + action_id,
                    "Action " + action_id + " failed: " + str(exc),
                ],
            }
            record["result"] = build_action_result_contract(
                record,
                registry=_runtime_result_registry(runtime),
            )
            artifact_ref = self._artifact_store.write_action(record)
            record["artifact_ref"] = artifact_ref
            record["execution_record"] = build_execution_record(record, kind="action")
            record["result"] = build_action_result_contract(
                record,
                registry=_runtime_result_registry(runtime),
            )
            self._artifact_store.write_action(record)
            self._state.observability.emit_action(
                execution_id=execution_id,
                action_id=action_id,
                domain_id=domain_id,
                status="FAILED",
                duration_ms=duration_ms,
                attributes={
                    "action_error_code": action_error_code,
                    "input_validated": action_error_code != "action_invalid_input",
                    "artifact_available": True,
                },
            )
            for name, value in {
                "action_id": action_id,
                "action_execution_id": execution_id,
                "artifact_ref": artifact_ref,
                "action_execution": record["action_execution"],
                "execution_record": record["execution_record"],
            }.items():
                try:
                    setattr(exc, name, value)
                except Exception:
                    pass
            raise

        if not isinstance(result, dict):
            raise ValueError("domain action must return an object")
        action_result = dict(result)
        response = dict(action_result)
        response.setdefault("action_id", action_id)
        response.setdefault("action_schema_version", "spatial-agent.actions.v1")
        response.setdefault("domain_id", domain_id)
        response.setdefault("status", "COMPLETED")
        action_execution = {
            "schema_version": "spatial-agent.action-execution.v1",
            "status": "COMPLETED",
            "action_id": action_id,
            "input_validated": True,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        record = {
            "action_execution_id": execution_id,
            "action_id": action_id,
            "domain_id": domain_id,
            "runtime_context": runtime_context,
            "idempotency_key": idempotency_key,
            "input_fingerprint": input_fingerprint,
            "status": "COMPLETED",
            "result_type": str(action_result.get("result_type") or result_type),
            "action_result": action_result,
            "action_execution": action_execution,
            "trace_summary": [
                "Received action: " + action_id,
                "Action " + action_id + " completed.",
            ],
        }
        record["result"] = build_action_result_contract(
            record,
            registry=_runtime_result_registry(runtime),
        )
        artifact_ref = self._artifact_store.write_action(record)
        record["artifact_ref"] = artifact_ref
        record["execution_record"] = build_execution_record(record, kind="action")
        record["result"] = build_action_result_contract(
            record,
            registry=_runtime_result_registry(runtime),
        )
        self._artifact_store.write_action(record)
        self._state.observability.emit_action(
            execution_id=execution_id,
            action_id=action_id,
            domain_id=domain_id,
            status="COMPLETED",
            duration_ms=action_execution["duration_ms"],
            attributes={
                "result_type": record["result_type"],
                "input_validated": True,
                "artifact_available": True,
            },
        )
        response.update(
            {
                "action_execution_id": execution_id,
                "action_execution": action_execution,
                "runtime_context": runtime_context,
                "idempotency_key": idempotency_key,
                "idempotency_reused": False,
                "trace_summary": list(record["trace_summary"]),
                "artifact_ref": artifact_ref,
                "result": record["result"],
                "execution_record": record["execution_record"],
            }
        )
        return response

    def get(self, execution_id: str) -> Dict[str, Any]:
        """Recover one action result from its artifact without dispatching it."""
        value = self._artifact_store.read_action(
            execution_id, domain_id=self._resolved_domain_id()
        )
        if value is None:
            raise ValueError("action execution not found: " + str(execution_id))
        value.setdefault(
            "execution_record", build_execution_record(value, kind="action")
        )
        return value

    def reserve_receipt(
        self,
        *,
        source_run_id: str,
        action: str,
        payload: Dict[str, Any],
        planner: str,
        backend: str,
        fingerprint_namespace: str = "",
        auto_key: bool = True,
    ) -> tuple[Dict[str, Any], bool]:
        """Reserve one lifecycle action and replay a completed receipt."""
        data = dict(payload)
        explicit_key = data.pop("idempotency_key", None)
        had_explicit_key = explicit_key is not None
        input_fingerprint = action_input_fingerprint(
            fingerprint_namespace + action,
            {"planner": planner, "backend": backend, "payload": data},
        )
        if explicit_key is None and auto_key:
            explicit_key = (
                "action:"
                + str(source_run_id)[:48]
                + ":"
                + action[:24]
                + ":"
                + input_fingerprint.rsplit(":", 1)[-1][:20]
            )
        if explicit_key is None:
            explicit_key = "action:" + uuid.uuid4().hex
        explicit_key = str(explicit_key).strip()
        if (
            not explicit_key
            or len(explicit_key) > 128
            or "/" in explicit_key
            or "\\" in explicit_key
        ):
            raise ValueError("action idempotency_key must be a safe non-empty value")
        domain_id = self._domain_id_provider(planner, backend)
        receipt = self._state.reserve_interaction(
            domain_id=domain_id,
            run_id=str(source_run_id),
            action=action,
            idempotency_key=explicit_key,
            input_fingerprint=input_fingerprint,
        )
        if not receipt.get("created"):
            if (
                receipt.get("status") == "FAILED"
                and not had_explicit_key
                and not auto_key
            ):
                reopened = self._state.reopen_interaction(
                    domain_id=domain_id,
                    run_id=str(source_run_id),
                    action=action,
                    idempotency_key=explicit_key,
                    input_fingerprint=input_fingerprint,
                )
                if reopened.get("reopened"):
                    reopened["idempotency_key"] = explicit_key
                    reopened["input_fingerprint"] = input_fingerprint
                    return reopened, False
            same_input = receipt.get("input_fingerprint") == input_fingerprint
            same_subject = (
                receipt.get("domain_id") == domain_id
                and receipt.get("run_id") == str(source_run_id)
                and receipt.get("action") == action
            )
            if not same_input or not same_subject:
                raise ValueError("action idempotency key conflicts with a previous input")
            if receipt.get("status") == "COMPLETED":
                replay = None
                if isinstance(receipt.get("response_payload"), dict):
                    replay = dict(receipt["response_payload"])
                result_run_id = receipt.get("result_run_id")
                if replay is None and result_run_id:
                    replay = self._get_run_provider(
                        str(result_run_id), planner, backend
                    )
                if replay is None:
                    raise ValueError("action receipt result is unavailable")
                replay_receipt = dict(receipt)
                stored_receipt = replay.get("action_receipt")
                if isinstance(stored_receipt, Mapping):
                    replay_receipt["identity_linkage"] = stored_receipt.get(
                        "identity_linkage"
                    )
                    for key in (
                        "preconditions",
                        "transition_identity",
                        "transition_evidence",
                        "evidence_revalidation",
                    ):
                        if key in stored_receipt:
                            replay_receipt[key] = stored_receipt.get(key)
                replay["action_receipt"] = project_action_receipt(
                    replay_receipt, reused=True
                )
                return replay, True
            if receipt.get("status") == "FAILED":
                raise ValueError(
                    "action previously failed: "
                    + str(receipt.get("error_code") or "action_failed")
                )
            raise ValueError("action is already in progress")
        receipt["idempotency_key"] = explicit_key
        receipt["input_fingerprint"] = input_fingerprint
        source_payload = self._action_identity_source(
            receipt,
            planner=planner,
            backend=backend,
        )
        source_identity_linkage = build_action_receipt_identity_linkage(
            source_payload or {}
        )
        if source_identity_linkage.get("available"):
            receipt["source_identity_linkage"] = source_identity_linkage
        receipt["source_transition_evidence"] = project_transition_evidence(
            source_payload or {}
        )
        return receipt, False

    def complete_receipt(
        self,
        receipt: Dict[str, Any],
        response: Optional[Dict[str, Any]],
        *,
        status: str,
        error_code: Optional[str] = None,
        result_run_id: Optional[str] = None,
        response_payload: Optional[Dict[str, Any]] = None,
        include_legacy: bool = False,
    ) -> Dict[str, Any]:
        """Complete one lifecycle receipt and persist its bounded projection."""
        response = response if isinstance(response, dict) else {}
        if result_run_id is None and status == "COMPLETED":
            result_run_id = response.get("run_id")
        if response_payload is None and status == "COMPLETED" and not result_run_id:
            response_payload = response
        identity_payload = response
        if not isinstance(response.get("result"), Mapping):
            identity_payload = self._action_identity_source(
                receipt, planner=None, backend=None
            ) or response
        receipt = dict(receipt)
        receipt.update(
            {
                "status": status,
                "result_run_id": result_run_id,
                "response_payload": response_payload,
                "error_code": error_code,
            }
        )
        identity_linkage = build_action_receipt_identity_linkage(identity_payload)
        if identity_linkage.get("available"):
            receipt["identity_linkage"] = identity_linkage
        action_preconditions = project_action_preconditions(
            identity_payload, action=receipt.get("action")
        )
        effect_receipt = dict(receipt)
        effect_receipt.pop("effect", None)
        effect_payload = dict(identity_payload)
        effect_payload.pop("action_effect", None)
        effect_result = effect_payload.get("result")
        if isinstance(effect_result, Mapping):
            effect_result = dict(effect_result)
            effect_result.pop("action_effect", None)
            effect_payload["result"] = effect_result
        receipt["preconditions"] = action_preconditions
        receipt["effect"] = project_action_effect(
            {**effect_payload, "action_receipt": effect_receipt},
            action=receipt.get("action"),
        )
        prior_source = identity_payload
        if not isinstance(prior_source.get("action_receipt"), Mapping):
            prior_source = self._action_identity_source(
                receipt, planner=None, backend=None
            ) or prior_source
        prior_receipt = prior_source.get("action_receipt")
        prior_result = prior_source.get("result")
        if not isinstance(prior_receipt, Mapping) and isinstance(prior_result, Mapping):
            prior_receipt = prior_result.get("action_receipt")
        prior_lineage = prior_source.get("transition_lineage")
        if not isinstance(prior_lineage, Mapping) and isinstance(prior_result, Mapping):
            prior_lineage = prior_result.get("transition_lineage")
        if not isinstance(prior_lineage, Mapping) and isinstance(prior_receipt, Mapping):
            prior_lineage = prior_receipt.get("transition_lineage")
        receipt["transition_lineage"] = append_action_lineage(
            prior_lineage
            or ([prior_receipt] if isinstance(prior_receipt, Mapping) else []),
            receipt,
        )
        result_identity_linkage = build_action_receipt_identity_linkage(identity_payload)
        source_identity_linkage = receipt.get("source_identity_linkage")
        if (
            isinstance(source_identity_linkage, Mapping)
            and result_identity_linkage.get("available")
        ):
            receipt["transition_identity"] = build_action_transition_identity_from_linkages(
                source_identity_linkage, result_identity_linkage
            )
        source_evidence = receipt.get("source_transition_evidence")
        if not isinstance(source_evidence, Mapping):
            source_evidence = project_transition_evidence(prior_source or {})
        receipt["transition_evidence"] = build_transition_evidence(
            source_evidence, project_transition_evidence(identity_payload)
        )
        receipt["evidence_revalidation"] = build_evidence_revalidation(
            receipt["transition_evidence"]
        )
        action_preconditions = project_action_preconditions(
            {**identity_payload, "action_receipt": receipt},
            action=receipt.get("action"),
        )
        receipt["preconditions"] = action_preconditions
        action_receipt = project_action_receipt(receipt, reused=False)
        response["action_preconditions"] = action_preconditions
        response = attach_action_receipt_timeline(response, action_receipt)
        stored_response_payload = response_payload
        if not result_run_id:
            stored_response_payload = dict(response_payload or response)
            stored_response_payload["action_preconditions"] = action_preconditions
            stored_response_payload = attach_action_receipt_timeline(
                stored_response_payload, action_receipt
            )
        elif isinstance(response_payload, dict):
            stored_response_payload = dict(response_payload)
            stored_response_payload["action_preconditions"] = action_preconditions
            stored_response_payload = attach_action_receipt_timeline(
                stored_response_payload, action_receipt
            )
        self._state.complete_interaction(
            domain_id=str(receipt.get("domain_id") or self._resolved_domain_id()),
            run_id=str(receipt.get("run_id") or ""),
            action=str(receipt.get("action") or ""),
            input_fingerprint=str(receipt.get("input_fingerprint") or ""),
            status=status,
            result_run_id=str(result_run_id) if result_run_id else None,
            response_payload=stored_response_payload,
            error_code=error_code,
        )
        if result_run_id:
            self.persist_receipt(result_run_id, action_receipt)
        if include_legacy:
            response["interaction_receipt"] = project_legacy_interaction_receipt(
                receipt, reused=False
            )
        response["action_receipt"] = action_receipt
        return response

    def persist_receipt(
        self, result_run_id: str, action_receipt: Dict[str, Any]
    ) -> None:
        """Attach a bounded receipt to the child run and its artifact."""
        domain_id = self._resolved_domain_id() or self._configured_domain_id()
        result = (
            self._state.get_run(result_run_id, domain_id=domain_id)
            if self._state.persistent
            else None
        )
        if result is None and not self._state.persistent:
            result = self._memory_result_provider(result_run_id)
        if result is None:
            return
        if hasattr(result, "action_receipt"):
            result.action_receipt = dict(action_receipt)
        if self._state.persistent:
            self._state.save_run(result)
        if result.artifact_ref:
            try:
                self._artifact_store.attach_action_receipt(
                    result_run_id, action_receipt, domain_id=domain_id
                )
            except (OSError, TypeError, ValueError):
                pass

    def _action_identity_source(
        self,
        receipt: Mapping[str, Any],
        *,
        planner: Optional[str],
        backend: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        source_run_id = receipt.get("run_id") if isinstance(receipt, Mapping) else None
        if not source_run_id:
            return None
        try:
            return self._get_run_provider(
                str(source_run_id), planner or "rule", backend or "memory"
            )
        except (LookupError, RuntimeError, TypeError, ValueError, OSError):
            return None

    def list(self, limit: int = 20) -> Dict[str, Any]:
        """Return bounded action history for Console and operational clients."""
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        return {
            "schema_version": "spatial-agent.action-history.v1",
            "actions": self._artifact_store.list_actions(
                limit=limit, domain_id=self._resolved_domain_id()
            ),
        }
