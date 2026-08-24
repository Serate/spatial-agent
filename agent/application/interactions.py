"""Canonical run interaction application use case.

This module owns the versioned interaction command, allowlisted lifecycle
dispatch, continuation workflow construction and receipt completion.  Domain
specific capability resolution and Runtime execution are injected ports.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from agent.artifact_store import ArtifactStore
from agent.geojson_exporter import DEFAULT_GEOJSON_MAX_FEATURES
from agent.interaction_contract import (
    INTERACTION_COMMAND_SCHEMA_VERSION,
    project_interaction,
)
from agent.interaction_host import InteractionHost
from agent.recovery_action import action_input_fingerprint
from agent.selection_interaction import normalize_selection_interaction


class InteractionApplication:
    """Apply one canonical interaction against a stored run."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        run_reader: Callable[[str, str, str], Dict[str, Any]],
        runtime_selector: Callable[[str, str, str], tuple[str, str]],
        runtime_provider: Callable[[str, str], Any],
        normalize_workflow: Callable[[Optional[Dict[str, Any]], str, str], Any],
        preview_provider: Callable[..., Dict[str, Any]],
        run_provider: Callable[..., Dict[str, Any]],
        resolve_decision_provider: Callable[..., Dict[str, Any]],
        cancel_provider: Callable[..., Dict[str, Any]],
        retry_provider: Callable[..., Dict[str, Any]],
        reserve_receipt: Callable[..., Any],
        complete_receipt: Callable[..., Dict[str, Any]],
        capability_resolver: Callable[..., Dict[str, Any]],
        request_facts_resolver: Callable[..., Any],
    ) -> None:
        self._artifact_store = artifact_store
        self._run_reader = run_reader
        self._runtime_selector = runtime_selector
        self._runtime_provider = runtime_provider
        self._normalize_workflow = normalize_workflow
        self._preview_provider = preview_provider
        self._run_provider = run_provider
        self._resolve_decision_provider = resolve_decision_provider
        self._cancel_provider = cancel_provider
        self._retry_provider = retry_provider
        self._reserve_receipt = reserve_receipt
        self._complete_receipt = complete_receipt
        self._capability_resolver = capability_resolver
        self._request_facts_resolver = request_facts_resolver

    def get(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict[str, Any]:
        """Return only the bounded next-action projection for one run."""
        payload = self._run_reader(run_id, planner, backend)
        envelope = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        interaction = project_interaction(payload)
        return {
            "schema_version": "spatial-agent.selection-interaction-reference.v1",
            "run_id": str(payload.get("run_id") or run_id)[:160],
            "domain_id": str(payload.get("domain_id") or "unknown")[:80],
            "interaction": interaction,
            "selection_interaction": normalize_selection_interaction(
                envelope.get("selection_interaction")
            ),
        }

    def apply(
        self,
        run_id: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Invoke one legacy or canonical command through InteractionHost."""
        data = dict(payload) if isinstance(payload, dict) else {}
        selected_planner, selected_backend = self._runtime_selector(
            run_id, planner, backend
        )
        if data.get("schema_version") == INTERACTION_COMMAND_SCHEMA_VERSION:
            command = data
        else:
            current = self._run_reader(run_id, selected_planner, selected_backend)
            interaction = project_interaction(current)
            action_id = str(
                action or data.get("action_id") or data.get("action") or ""
            ).strip().lower()
            action_input = dict(data)
            for key in (
                "schema_version",
                "subject",
                "action_id",
                "action",
                "idempotency_key",
                "planner",
                "backend",
            ):
                action_input.pop(key, None)
            idempotency_key = str(data.get("idempotency_key") or "").strip()
            if not idempotency_key:
                fingerprint = action_input_fingerprint(action_id, action_input)
                idempotency_key = (
                    "interaction:"
                    + str(run_id)[:48]
                    + ":"
                    + action_id[:24]
                    + ":"
                    + fingerprint.rsplit(":", 1)[-1][:20]
                )
            command = {
                "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
                "subject": interaction.get("subject"),
                "action_id": action_id,
                "input": action_input,
                "idempotency_key": idempotency_key,
            }

        host = InteractionHost(
            loader=lambda _subject: self._run_reader(
                run_id, selected_planner, selected_backend
            ),
            dispatcher=lambda checked, _interaction: self._dispatch(
                run_id,
                str(checked["action_id"]),
                {
                    **dict(checked["input"]),
                    "idempotency_key": checked["idempotency_key"],
                },
                planner=selected_planner,
                backend=selected_backend,
            ),
        )
        return host.invoke(command)

    def _dispatch(
        self,
        run_id: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Apply one allowlisted next action through injected lifecycle ports."""
        action = str(action or "").strip().lower()
        if not action:
            raise ValueError("interaction action must be a non-empty string")
        current = self._run_reader(run_id, planner, backend)
        envelope = current.get("result") if isinstance(current.get("result"), dict) else {}
        interaction = project_interaction(current)
        data = dict(payload) if isinstance(payload, dict) else {}
        selected_planner, selected_backend = self._runtime_selector(
            run_id, planner, backend
        )

        if action in {"confirm", "reject"}:
            decision = current.get("decision_evidence") or envelope.get("decision")
            if not isinstance(decision, dict) or not decision.get("decision_id"):
                raise ValueError("interaction decision evidence is unavailable")
            choice = "approve" if action == "confirm" else "reject"
            expected_version = data.get("expected_version", decision.get("version"))
            return self._resolve_decision_provider(
                str(decision["decision_id"]),
                choice,
                expected_version=expected_version,
                planner=selected_planner,
                backend=selected_backend,
                idempotency_key=data.get("idempotency_key"),
            )
        if action == "cancel":
            return self._cancel_provider(
                run_id,
                planner=selected_planner,
                backend=selected_backend,
                idempotency_key=data.get("idempotency_key"),
            )
        if action in {"retry", "recover"}:
            return self._retry_provider(
                run_id,
                planner=selected_planner,
                backend=selected_backend,
                export_artifact=bool(data.get("export_artifact", True)),
                export_geojson=bool(data.get("export_geojson", False)),
                geojson_max_features=int(
                    data.get("geojson_max_features", DEFAULT_GEOJSON_MAX_FEATURES)
                ),
                idempotency_key=data.get("idempotency_key"),
            )

        workflow_value = data.get("workflow")
        if action in {"repair", "preview"} and not isinstance(workflow_value, dict):
            workflow_value = current.get("workflow")
        if action in {"select_capability", "provide_facts"} and not isinstance(
            workflow_value, dict
        ):
            capability_id = self._interaction_capability_id(data, interaction)
            if action == "select_capability" and not capability_id:
                raise ValueError("interaction capability_id must be a non-empty string")
            if capability_id:
                workflow_value = self._capability_resolver(
                    capability_id,
                    interaction=interaction,
                    request_facts=self._request_facts_resolver(
                        current,
                        planner=selected_planner,
                        backend=selected_backend,
                    ),
                    planner=selected_planner,
                    backend=selected_backend,
                )
            elif action == "provide_facts":
                raise ValueError(
                    "interaction facts require a capability_id or selected capability"
                )
        if action == "provide_facts" and isinstance(workflow_value, dict):
            workflow_value = dict(workflow_value)
            constraints = dict(workflow_value.get("constraints") or {})
            facts = data.get("facts") or data.get("constraints") or {}
            if not isinstance(facts, dict):
                raise ValueError("interaction facts must be an object")
            constraints.update(facts)
            workflow_value["constraints"] = constraints
        if action not in {"repair", "preview"} and not isinstance(workflow_value, dict):
            raise ValueError("interaction workflow selection must be an object")
        if isinstance(workflow_value, dict):
            workflow_value = self._normalize_workflow(
                workflow_value, selected_planner, selected_backend
            )
        continuation_request = str(
            current.get("request") or current.get("resolved_request") or ""
        ).strip()
        resolved_request_override = str(
            current.get("resolved_request") or continuation_request
        ).strip()
        if not continuation_request:
            raise ValueError("interaction request context is unavailable")
        receipt = None
        receipt_actions = {
            "provide_facts",
            "select_capability",
            "select_workflow",
            "preview",
            "repair",
        }
        if action in receipt_actions:
            receipt, replay = self._reserve_receipt(
                source_run_id=run_id,
                action=action,
                payload=data,
                planner=selected_planner,
                backend=selected_backend,
            )
            if replay:
                return receipt
        if action in {"provide_facts", "select_capability", "select_workflow", "preview"}:
            continuation_runtime = self._runtime_provider(
                selected_planner, selected_backend
            )
            clear_pending = getattr(continuation_runtime, "clear_session", None)
            if callable(clear_pending):
                clear_pending(str(current.get("session_id") or "default"))
        if action in {"preview", "repair"}:
            try:
                response = self._preview_provider(
                    request=continuation_request,
                    session_id=str(current.get("session_id") or "default"),
                    planner=selected_planner,
                    backend=selected_backend,
                    workflow=workflow_value,
                    spatial_context=current.get("spatial_context"),
                    _resolved_request=resolved_request_override,
                )
            except Exception:
                if receipt is not None:
                    self._complete_receipt(
                        receipt, {}, status="FAILED", error_code="preview_failed"
                    )
                raise
            return (
                self._complete_receipt(receipt, response, status="COMPLETED")
                if receipt is not None
                else response
            )
        try:
            response = self._run_provider(
                request=continuation_request,
                session_id=str(current.get("session_id") or "default"),
                planner=selected_planner,
                backend=selected_backend,
                workflow=workflow_value,
                require_confirmation=bool(data.get("require_confirmation", True)),
                export_artifact=bool(data.get("export_artifact", True)),
                export_geojson=bool(data.get("export_geojson", False)),
                geojson_max_features=int(
                    data.get("geojson_max_features", DEFAULT_GEOJSON_MAX_FEATURES)
                ),
                _resolved_request=resolved_request_override,
            )
        except Exception:
            if receipt is not None:
                self._complete_receipt(
                    receipt, {}, status="FAILED", error_code="interaction_failed"
                )
            raise
        if receipt is not None:
            response = self._complete_receipt(receipt, response, status="COMPLETED")
            if response.get("artifact_ref"):
                self._artifact_store.write_run(response)
        return response

    @staticmethod
    def _interaction_capability_id(
        payload: Mapping[str, Any], interaction: Mapping[str, Any]
    ) -> str:
        explicit = str(payload.get("capability_id") or "").strip()
        if explicit:
            return explicit[:96]
        selection = interaction.get("selection")
        if not isinstance(selection, Mapping):
            return ""
        selected = str(selection.get("selected_capability_id") or "").strip()
        if selected:
            return selected[:96]
        candidates = selection.get("candidate_ids")
        if isinstance(candidates, (list, tuple)) and len(candidates) == 1:
            candidate = str(candidates[0] or "").strip()
            return candidate[:96]
        return ""
