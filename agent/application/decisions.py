"""Canonical decision application use case.

Decision resolution is a lifecycle input.  This module owns decision lookup,
artifact recovery, approve/reject transitions and continuation of the stored
run, while Runtime remains responsible for planning and execution.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from agent.artifact_store import ArtifactStore
from agent.decision_lifecycle import DecisionLifecycleError, DecisionRecord
from agent.geojson_exporter import DEFAULT_GEOJSON_MAX_FEATURES
from agent.models import RunStatus
from agent.service_format import format_result
from result_contract import build_result_contract


def _runtime_result_registry(runtime: Any) -> Any:
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


class DecisionApplication:
    """Read and resolve decisions through one transport-neutral interface."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        state: Any,
        runtime_provider: Callable[[str, str], Any],
        run_provider: Callable[..., Dict[str, Any]],
        memory_run_provider: Callable[[str], Any],
        resolved_domain_id: Callable[[], Optional[str]],
        configured_domain_id: Callable[[], Optional[str]],
        legacy_domain_id: str,
        reserve_action_receipt: Callable[..., Any],
        complete_action_receipt: Callable[..., Dict[str, Any]],
    ) -> None:
        self._artifact_store = artifact_store
        self._state = state
        self._runtime_provider = runtime_provider
        self._run_provider = run_provider
        self._memory_run_provider = memory_run_provider
        self._resolved_domain_id = resolved_domain_id
        self._configured_domain_id = configured_domain_id
        self._legacy_domain_id = legacy_domain_id
        self._reserve_action_receipt = reserve_action_receipt
        self._complete_action_receipt = complete_action_receipt

    def get(self, decision_id: str) -> Dict[str, Any]:
        """Read one bounded decision projection in the selected Domain."""
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id must be a non-empty string")
        domain_id = self._current_domain_id()
        record = self._decision_record(decision_id, domain_id)
        if record is None:
            raise ValueError("decision not found: " + decision_id)
        return {
            "schema_version": record.schema_version,
            "decision": record.as_dict(),
            "evidence": record.evidence(),
        }

    def resolve(
        self,
        decision_id: str,
        choice: str,
        expected_version: int = None,
        planner: str = "rule",
        backend: str = "memory",
        idempotency_key: str = None,
    ) -> Dict[str, Any]:
        """Resolve one decision and replay an existing action receipt."""
        aliases = {"accept": "approve", "confirm": "approve", "deny": "reject"}
        normalized_choice = aliases.get(
            str(choice or "").strip().lower(), str(choice or "").strip().lower()
        )
        if normalized_choice not in {"approve", "reject"}:
            return self._resolve_impl(
                decision_id,
                choice,
                expected_version=expected_version,
                planner=planner,
                backend=backend,
            )
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id must be a non-empty string")
        domain_id = self._current_domain_id()
        record = self._decision_record(decision_id, domain_id)
        receipt, reused = self._reserve_action_receipt(
            source_run_id=record.subject_id,
            action=normalized_choice,
            payload={
                "decision_id": decision_id,
                "choice": normalized_choice,
                "expected_version": expected_version,
                "idempotency_key": idempotency_key,
            },
            planner=planner,
            backend=backend,
        )
        if reused:
            return receipt
        try:
            response = self._resolve_impl(
                decision_id,
                choice,
                expected_version=expected_version,
                planner=planner,
                backend=backend,
            )
        except Exception as exc:
            self._complete_action_receipt(
                receipt,
                {"run_id": record.subject_id, "status": "FAILED", "error": str(exc)},
                status="FAILED",
                error_code="decision_resolution_failed",
                response_payload={
                    "run_id": record.subject_id,
                    "status": "FAILED",
                    "error": str(exc),
                },
            )
            raise
        return self._complete_action_receipt(
            receipt,
            response,
            status="COMPLETED",
            result_run_id=response.get("run_id") or record.subject_id,
        )

    def _resolve_impl(
        self,
        decision_id: str,
        choice: str,
        expected_version: int = None,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Approve/reject a waiting run and resume only its persisted plan."""
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id must be a non-empty string")
        domain_id = self._current_domain_id()
        self._decision_record(decision_id, domain_id)
        try:
            record = self._state.decision_store.resolve(
                decision_id,
                choice=choice,
                expected_version=expected_version,
                domain_id=domain_id,
            )
        except DecisionLifecycleError:
            raise
        result = (
            self._state.get_run(record.subject_id, domain_id=domain_id)
            if self._state.persistent
            else self._memory_run_provider(record.subject_id)
        )
        if result is None:
            artifact = self._artifact_store.read_run(
                record.subject_id, domain_id=domain_id
            )
            if isinstance(artifact, dict):
                from agent.sqlite_store import _result_from_dict

                restored = _result_from_dict(
                    artifact,
                    legacy_domain_id=self._legacy_domain_id,
                )
                context = (
                    restored.runtime_context
                    if isinstance(restored.runtime_context, dict)
                    else {}
                )
                runtime = self._runtime_provider(
                    str(context.get("planner") or planner),
                    str(context.get("backend") or backend),
                )
                runtime._state_store.save(restored)
                result = restored
        if result is None:
            raise ValueError("decision subject run not found: " + record.subject_id)
        if record.status == "REJECTED":
            result.status = RunStatus.REJECTED
            result.error = "用户拒绝执行当前计划。"
            result.answer = "已拒绝执行当前计划。"
            result.decision_evidence = record.evidence()
            if self._state.persistent:
                self._state.save_run(result)
            else:
                runtime = self._runtime_provider(planner, backend)
                runtime._state_store.save(result)
            payload = format_result(
                result,
                {},
                result_registry=_runtime_result_registry(
                    self._runtime_provider(planner, backend)
                ),
            )
            payload["decision"] = record.as_dict()
            return payload

        context = result.runtime_context if isinstance(result.runtime_context, dict) else {}
        selected_planner = str(context.get("planner") or planner)
        selected_backend = str(context.get("backend") or backend)
        options = record.input_data if isinstance(record.input_data, dict) else {}
        payload = self._run_provider(
            request=result.request,
            session_id=result.session_id or "default",
            planner=selected_planner,
            backend=selected_backend,
            export_artifact=bool(options.get("export_artifact")),
            export_geojson=bool(options.get("export_geojson")),
            geojson_max_features=int(
                options.get("geojson_max_features", DEFAULT_GEOJSON_MAX_FEATURES)
            ),
            workflow=result.workflow,
            run_id=result.run_id,
            preview_fingerprint=record.subject_fingerprint,
            decision_id=record.decision_id,
            decision_version=record.version,
            _force_run_id=True,
        )
        payload["decision"] = record.as_dict()
        return payload

    def _current_domain_id(self) -> str:
        return (
            self._resolved_domain_id()
            or self._configured_domain_id()
            or "unknown"
        )

    def _decision_record(self, decision_id: str, domain_id: str) -> DecisionRecord:
        record = self._state.decision_store.get(decision_id, domain_id=domain_id)
        if record is not None:
            return record
        artifact = self._artifact_store.find_decision(
            decision_id, domain_id=domain_id
        )
        if not isinstance(artifact, dict):
            raise ValueError("decision not found: " + decision_id)
        try:
            record = DecisionRecord.from_dict(artifact)
        except (DecisionLifecycleError, TypeError, ValueError) as exc:
            raise ValueError("decision artifact is invalid: " + decision_id) from exc
        restore = getattr(self._state.decision_store, "restore", None)
        if callable(restore):
            restore(record)
        return record
