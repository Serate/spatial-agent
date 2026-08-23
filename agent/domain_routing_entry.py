"""Shared application seam for automatic Domain routing entry points."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
import os
from threading import RLock
from typing import Any

from agent.api_contract import async_run_kwargs, run_kwargs
from agent.domain_registry import DomainRegistry, DomainSelectionError
from agent.domain_selector import (
    DomainRouter,
    DomainRoutingDecision,
    build_domain_routing_interaction,
)
from agent.sqlite_store import SQLiteConversationStore


class DomainRoutingApplicationError(ValueError):
    """Machine-readable failure at the automatic routing application seam."""

    def __init__(self, message: str, *, code: str):
        self.code = str(code)[:64]
        super().__init__(message)


class DomainRoutingState:
    """Bounded in-process decisions with optional durable SQLite lineage."""

    def __init__(self, store: Any = None, *, max_decisions: int = 256) -> None:
        self._store = store
        self._max_decisions = max(16, min(int(max_decisions), 1024))
        self._decisions: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._bindings: dict[str, str] = {}
        self._lock = RLock()

    def bound_domain(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        if self._store is not None:
            getter = getattr(self._store, "get_bound_session_domain", None)
            if callable(getter):
                persisted = getter(session_id)
                return str(persisted) if persisted else None
        with self._lock:
            return self._bindings.get(session_id)

    def bind(self, session_id: str | None, domain_id: str) -> None:
        if not session_id:
            return
        with self._lock:
            existing = self._bindings.get(session_id)
            if existing and existing != domain_id:
                raise DomainSelectionError(
                    "session belongs to another domain: " + session_id,
                    code="session_domain_mismatch",
                )
            self._bindings[session_id] = domain_id

    def save(self, decision: DomainRoutingDecision, session_id: str | None = None) -> None:
        payload = decision.to_dict()
        if self._store is not None and session_id:
            saver = getattr(self._store, "save_domain_routing_decision", None)
            if callable(saver):
                saver(session_id, payload)
        with self._lock:
            self._decisions[decision.decision_id] = {
                "decision": payload,
                "session_id": session_id,
            }
            self._decisions.move_to_end(decision.decision_id)
            while len(self._decisions) > self._max_decisions:
                self._decisions.popitem(last=False)

    def get(self, decision_id: str, session_id: str | None = None) -> Mapping[str, Any] | None:
        if self._store is not None:
            getter = getattr(self._store, "get_domain_routing_decision", None)
            if callable(getter):
                return getter(decision_id, session_id)
        with self._lock:
            record = self._decisions.get(decision_id)
            if record is None:
                return None
            if session_id is not None and record["session_id"] != session_id:
                return None
            return record["decision"]

    def clear(self, session_id: str) -> None:
        if self._store is not None:
            clearer = getattr(self._store, "clear_session", None)
            if callable(clearer):
                clearer(session_id)
        self.forget(session_id)

    def forget(self, session_id: str, *, keep_binding: bool = False) -> None:
        """Discard process-local routing state after an authoritative clear."""

        with self._lock:
            for decision_id in [
                key
                for key, record in self._decisions.items()
                if record["session_id"] == session_id
            ]:
                self._decisions.pop(decision_id, None)
            if not keep_binding:
                self._bindings.pop(session_id, None)


class DomainRoutingApplication:
    """Select, clarify, override and execute through one transport-neutral interface."""

    def __init__(
        self,
        host: Any,
        *,
        router: DomainRouter | None = None,
        state: DomainRoutingState | None = None,
    ) -> None:
        self._host = host
        self._router = router or DomainRouter(
            enabled_domain_ids=host.catalog().get("domain_ids")
        )
        self._state = state or DomainRoutingState()

    def catalog(self) -> dict[str, Any]:
        return self._router.catalog()

    def select(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        decision = self._route(payload)
        self._state.save(decision, _session_id(payload, default=None))
        return self._routing_response(decision)

    def override(self, decision_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        session_id = _session_id(payload, default=None)
        prior = self._state.get(decision_id, session_id)
        if prior is None:
            raise DomainRoutingApplicationError(
                "domain routing decision not found",
                code="domain_routing_decision_not_found",
            )
        decision = self._router.override(prior, str(payload.get("domain_id") or ""))
        bound_domain = self._state.bound_domain(session_id)
        if bound_domain and bound_domain != decision.selection.domain_id:
            raise DomainSelectionError(
                "session belongs to another domain: " + str(session_id),
                code="session_domain_mismatch",
            )
        self._state.save(decision, session_id)
        return self._routing_response(decision)

    def run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["session_id"] = _session_id(normalized, default="default")
        decision_id = str(normalized.get("domain_routing_decision_id") or "").strip()
        if decision_id:
            restored = self._state.get(decision_id, normalized["session_id"])
            if restored is None:
                raise DomainRoutingApplicationError(
                    "domain routing decision not found",
                    code="domain_routing_decision_not_found",
                )
            decision = self._router.resolve(restored)
            if decision.status != "selected":
                raise DomainRoutingApplicationError(
                    "domain routing decision must be selected",
                    code="domain_routing_decision_not_selected",
                )
            bound_domain = self._state.bound_domain(normalized["session_id"])
            if bound_domain and bound_domain != decision.selection.domain_id:
                raise DomainSelectionError(
                    "session belongs to another domain: " + normalized["session_id"],
                    code="session_domain_mismatch",
                )
        else:
            decision = self._route(normalized)
            self._state.save(decision, normalized["session_id"])
        if decision.needs_clarification:
            return {
                "status": "NEEDS_CLARIFICATION",
                "session_id": normalized["session_id"],
                "domain_id": None,
                **self._routing_response(decision),
            }
        selected_service = self._host.service(decision.selection)
        if bool(normalized.get("async", False)):
            result = selected_service.run_async(**async_run_kwargs(normalized))
        else:
            result = selected_service.run(**run_kwargs(normalized))
        self._state.bind(normalized["session_id"], decision.selection.domain_id)
        response = dict(result)
        response["domain_id"] = decision.selection.domain_id
        response["domain_routing"] = decision.to_dict()
        return response

    def clear_unbound_session(self, session_id: str) -> dict[str, Any]:
        normalized = _session_id({"session_id": session_id}, default=None)
        if self._state.bound_domain(normalized):
            raise DomainRoutingApplicationError(
                "bound sessions must be cleared through their selected domain",
                code="domain_routing_session_bound",
            )
        self._state.clear(normalized)
        return {"status": "CLEARED", "session_id": normalized, "domain_id": None}

    def forget_session(self, session_id: str, *, keep_binding: bool = False) -> None:
        """Synchronize process-local routing state with Domain session cleanup."""

        normalized = _session_id({"session_id": session_id}, default=None)
        self._state.forget(normalized, keep_binding=keep_binding)

    def _route(self, payload: Mapping[str, Any]) -> DomainRoutingDecision:
        request = str(payload.get("request") or "")
        session_id = _session_id(payload, default=None)
        bound_domain = self._state.bound_domain(session_id)
        if bound_domain:
            return self._router.restore(request, bound_domain)
        return self._router.route(request, domain_id=payload.get("domain_id"))

    @staticmethod
    def _routing_response(decision: DomainRoutingDecision) -> dict[str, Any]:
        response = {"domain_routing": decision.to_dict()}
        if decision.needs_clarification:
            response["domain_routing_interaction"] = build_domain_routing_interaction(
                decision
            )
        return response


def routing_state_from_environment(
    *,
    registry: DomainRegistry | None = None,
) -> DomainRoutingState:
    # Use the exact state database configured for AgentService so routing
    # decisions and session-domain bindings cannot drift into separate files.
    path = os.environ.get("SPATIAL_AGENT_STATE_DB")
    store = (
        SQLiteConversationStore(path, routing_registry=registry)
        if path
        else None
    )
    return DomainRoutingState(store)


def _session_id(payload: Mapping[str, Any], *, default: str | None) -> str | None:
    value = payload.get("session_id", default)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("session_id must be a non-empty string")
    return value.strip()
