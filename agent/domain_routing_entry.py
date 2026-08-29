"""Shared application seam for automatic Domain routing entry points."""

from __future__ import annotations

from collections import Counter, OrderedDict
from collections.abc import Mapping
import os
from time import perf_counter
from threading import RLock
from typing import Any

from agent.api_contract import async_run_kwargs, run_kwargs
from agent.domain_registry import DomainRegistry, DomainSelectionError
from agent.domain_selector import (
    DomainRouter,
    DomainRoutingDecision,
    build_domain_routing_interaction,
    resolve_domain_routing_decision,
)
from agent.domain_routing_evidence import build_domain_routing_evidence
from agent.interaction_contract import (
    INTERACTION_COMMAND_SCHEMA_VERSION,
    InteractionContractError,
    legacy_domain_routing_interaction,
    project_interaction,
)
from agent.interaction_host import InteractionHost
from agent.recovery_action import action_input_fingerprint, project_action_receipt
from agent.domain_selector_provider import domain_selector_from_environment
from agent.persistence.sqlite_store import SQLiteConversationStore


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
        self._interaction_receipts: OrderedDict[tuple[str, str], dict[str, Any]] = (
            OrderedDict()
        )
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
            self._remember_decision(decision, session_id)

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

    def lineage(
        self,
        decision: DomainRoutingDecision | Mapping[str, Any],
        session_id: str | None,
        *,
        limit: int = 8,
    ) -> list[Mapping[str, Any]]:
        """Return one bounded, root-to-current immutable decision chain."""

        current = (
            decision.to_dict()
            if isinstance(decision, DomainRoutingDecision)
            else dict(decision)
        )
        bounded_limit = max(1, min(int(limit), 16))
        values: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        while current and len(values) < bounded_limit:
            decision_id = str(current.get("decision_id") or "")
            if not decision_id or decision_id in seen:
                break
            seen.add(decision_id)
            values.append(current)
            parent_id = str(current.get("parent_decision_id") or "")
            if not parent_id:
                break
            restored = self.get(parent_id, session_id)
            if restored is None:
                break
            current = restored
        values.reverse()
        return values

    def child(
        self,
        parent_decision_id: str,
        session_id: str | None,
    ) -> Mapping[str, Any] | None:
        """Return the immutable direct child of a routing decision, if any."""

        if self._store is not None and session_id:
            listing = getattr(self._store, "list_domain_routing_decisions", None)
            if callable(listing):
                for item in listing(session_id, limit=32):
                    if item.get("parent_decision_id") == parent_decision_id:
                        return item
        with self._lock:
            for record in reversed(tuple(self._decisions.values())):
                if session_id is not None and record["session_id"] != session_id:
                    continue
                decision = record["decision"]
                if decision.get("parent_decision_id") == parent_decision_id:
                    return decision
        return None

    def commit_interaction(
        self,
        *,
        subject_decision_id: str,
        decision: DomainRoutingDecision,
        session_id: str | None,
        action: str,
        idempotency_key: str,
        input_fingerprint: str,
    ) -> dict[str, Any]:
        """Atomically commit one routing child and its bounded command receipt."""

        if self._store is not None and session_id:
            committer = getattr(
                self._store,
                "commit_domain_routing_interaction",
                None,
            )
            if callable(committer):
                result = committer(
                    session_id=session_id,
                    subject_decision_id=subject_decision_id,
                    decision=decision,
                    action=action,
                    idempotency_key=idempotency_key,
                    input_fingerprint=input_fingerprint,
                )
                restored = resolve_domain_routing_decision(result["decision"])
                with self._lock:
                    self._remember_decision(restored, session_id)
                    self._remember_receipt(
                        subject_decision_id,
                        action,
                        result["receipt"],
                    )
                return result

        key = (subject_decision_id, action)
        requested_domain = (
            decision.selection.domain_id if decision.selection is not None else ""
        )
        with self._lock:
            existing_receipt = self._interaction_receipts.get(key)
            if existing_receipt is not None:
                if (
                    existing_receipt.get("idempotency_key") != idempotency_key
                    or existing_receipt.get("input_fingerprint") != input_fingerprint
                ):
                    raise InteractionContractError(
                        "routing interaction conflicts with an existing command",
                        code="interaction_revision_conflict",
                    )
                result_id = str(
                    (existing_receipt.get("result_ref") or {}).get("id") or ""
                )
                result_record = self._decisions.get(result_id)
                if result_record is None:
                    raise ValueError("routing interaction receipt result is missing")
                return {
                    "created": False,
                    "decision": result_record["decision"],
                    "receipt": project_action_receipt(
                        existing_receipt,
                        reused=True,
                    ),
                }

            for receipt_key, receipt in self._interaction_receipts.items():
                if (
                    receipt_key != key
                    and receipt.get("idempotency_key") == idempotency_key
                ):
                    raise InteractionContractError(
                        "interaction idempotency key already belongs to another subject",
                        code="interaction_idempotency_conflict",
                    )

            existing_child = None
            for record in reversed(tuple(self._decisions.values())):
                if session_id is not None and record["session_id"] != session_id:
                    continue
                if record["decision"].get("parent_decision_id") == subject_decision_id:
                    existing_child = resolve_domain_routing_decision(record["decision"])
                    break
            created = existing_child is None
            if existing_child is not None:
                existing_domain = (
                    existing_child.selection.domain_id
                    if existing_child.selection is not None
                    else ""
                )
                if existing_domain != requested_domain:
                    raise InteractionContractError(
                        "routing decision was already resolved with another domain",
                        code="interaction_revision_conflict",
                    )
                committed = existing_child
            else:
                committed = decision
                self._remember_decision(committed, session_id)

            receipt = project_action_receipt(
                {
                    "status": "COMPLETED",
                    "action_id": action,
                    "subject": {
                        "kind": "routing_decision",
                        "id": subject_decision_id,
                    },
                    "result_ref": {
                        "kind": "routing_decision",
                        "id": committed.decision_id,
                    },
                    "idempotency_key": idempotency_key,
                    "input_fingerprint": input_fingerprint,
                }
            )
            self._remember_receipt(subject_decision_id, action, receipt)
            return {
                "created": created,
                "decision": committed.to_dict(),
                "receipt": receipt,
            }

    def _remember_decision(
        self,
        decision: DomainRoutingDecision,
        session_id: str | None,
    ) -> None:
        self._decisions[decision.decision_id] = {
            "decision": decision.to_dict(),
            "session_id": session_id,
        }
        self._decisions.move_to_end(decision.decision_id)
        while len(self._decisions) > self._max_decisions:
            self._decisions.popitem(last=False)

    def _remember_receipt(
        self,
        subject_decision_id: str,
        action: str,
        receipt: Mapping[str, Any],
    ) -> None:
        key = (subject_decision_id, action)
        self._interaction_receipts[key] = dict(receipt)
        self._interaction_receipts.move_to_end(key)
        while len(self._interaction_receipts) > self._max_decisions:
            self._interaction_receipts.popitem(last=False)

    def clear(self, session_id: str) -> None:
        if self._store is not None:
            clearer = getattr(self._store, "clear_session", None)
            if callable(clearer):
                clearer(session_id)
        self.forget(session_id)

    def forget(self, session_id: str, *, keep_binding: bool = False) -> None:
        """Discard process-local routing state after an authoritative clear."""

        with self._lock:
            decision_ids = [
                key
                for key, record in self._decisions.items()
                if record["session_id"] == session_id
            ]
            for decision_id in decision_ids:
                self._decisions.pop(decision_id, None)
            for receipt_key in [
                key
                for key in self._interaction_receipts
                if key[0] in decision_ids
            ]:
                self._interaction_receipts.pop(receipt_key, None)
            if not keep_binding:
                self._bindings.pop(session_id, None)


class DomainRoutingMetrics:
    """Bounded, request-free observations for the routing application."""

    schema_version = "spatial-agent.domain-routing-metrics.v1"

    def __init__(self) -> None:
        self._lock = RLock()
        self._count = 0
        self._clarification_count = 0
        self._fallback_count = 0
        self._latency_total_ms = 0.0
        self._status_counts: Counter[str] = Counter()
        self._selector_counts: Counter[str] = Counter()
        self._last: dict[str, Any] | None = None

    def observe(
        self,
        decision: DomainRoutingDecision,
        *,
        latency_ms: float,
    ) -> None:
        latency = round(max(0.0, min(float(latency_ms), 86_400_000.0)), 3)
        fallback_reason = (
            decision.reason_code.split(":", 1)[1][:96]
            if decision.reason_code.startswith("selector_fallback:")
            and ":" in decision.reason_code
            else None
        )
        item = {
            "status": decision.status,
            "selector_id": decision.selector_id,
            "selector_mode": decision.selector_id.split(".", 1)[0][:32],
            "candidate_count": len(decision.candidates),
            "clarification_required": decision.needs_clarification,
            "fallback_reason": fallback_reason,
            "latency_ms": latency,
        }
        with self._lock:
            self._count += 1
            self._latency_total_ms += latency
            self._status_counts[decision.status] += 1
            self._selector_counts[decision.selector_id] += 1
            if decision.needs_clarification:
                self._clarification_count += 1
            if fallback_reason:
                self._fallback_count += 1
            self._last = item

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            count = self._count
            return {
                "schema_version": self.schema_version,
                "selection_count": count,
                "clarification_count": self._clarification_count,
                "clarification_rate": round(
                    self._clarification_count / count, 6
                ) if count else 0.0,
                "fallback_count": self._fallback_count,
                "average_latency_ms": round(
                    self._latency_total_ms / count, 3
                ) if count else 0.0,
                "status_counts": dict(sorted(self._status_counts.items())),
                "selector_counts": dict(sorted(self._selector_counts.items())),
                "last_selection": dict(self._last) if self._last else None,
            }


class DomainRoutingApplication:
    """Select, clarify, override and execute through one transport-neutral interface."""

    def __init__(
        self,
        host: Any,
        *,
        router: DomainRouter | None = None,
        state: DomainRoutingState | None = None,
        metrics: DomainRoutingMetrics | None = None,
        selector_provider: Any = None,
    ) -> None:
        self._host = host
        self._selector_provider = selector_provider
        if router is None:
            self._selector_provider = (
                selector_provider or domain_selector_from_environment()
            )
            router = DomainRouter(
                enabled_domain_ids=host.catalog().get("domain_ids"),
                selector=self._selector_provider,
            )
        self._router = router
        self._state = state or DomainRoutingState()
        self._metrics = metrics or DomainRoutingMetrics()

    def catalog(self) -> dict[str, Any]:
        result = dict(self._router.catalog())
        status = getattr(self._selector_provider, "status", None)
        if callable(status):
            result["selector_provider"] = status()
        return result

    def metrics(self) -> dict[str, Any]:
        result = self._metrics.snapshot()
        provider_metrics = getattr(self._selector_provider, "metrics", None)
        if callable(provider_metrics):
            result["provider"] = provider_metrics()
        return result

    def select(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        decision, _latency_ms = self._route_observed(payload)
        self._state.save(decision, _session_id(payload, default=None))
        return self._routing_response(decision)

    def override(self, decision_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a legacy payload or canonical command through InteractionHost."""

        session_id = _session_id(payload, default=None)
        prior = self._state.get(decision_id, session_id)
        if prior is None:
            raise DomainRoutingApplicationError(
                "domain routing decision not found",
                code="domain_routing_decision_not_found",
            )
        authoritative_source = self._routing_response(
            resolve_domain_routing_decision(prior)
        )
        interaction = project_interaction(authoritative_source)
        if payload.get("schema_version") == INTERACTION_COMMAND_SCHEMA_VERSION:
            command = dict(payload)
        else:
            action_input = {"domain_id": str(payload.get("domain_id") or "")}
            idempotency_key = str(payload.get("idempotency_key") or "").strip()
            if not idempotency_key:
                fingerprint = action_input_fingerprint("select_domain", action_input)
                idempotency_key = (
                    "interaction:"
                    + decision_id[:48]
                    + ":select_domain:"
                    + fingerprint.rsplit(":", 1)[-1][:20]
                )
            command = {
                "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
                "subject": interaction["subject"],
                "action_id": "select_domain",
                "input": action_input,
                "idempotency_key": idempotency_key,
            }
        host = InteractionHost(
            loader=lambda _subject: self._routing_response(
                resolve_domain_routing_decision(
                    self._state.get(decision_id, session_id) or prior
                )
            ),
            dispatcher=lambda checked, _interaction: self._override_authorized(
                decision_id,
                checked,
                session_id=session_id,
                prior=prior,
            ),
        )
        return host.invoke(command)

    def _override_authorized(
        self,
        decision_id: str,
        command: Mapping[str, Any],
        *,
        session_id: str | None,
        prior: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a Host-validated selection with immutable-lineage CAS."""

        action_input = command.get("input")
        action_input = action_input if isinstance(action_input, Mapping) else {}
        requested_domain_id = str(action_input.get("domain_id") or "")
        started = perf_counter()
        decision = self._router.override(prior, requested_domain_id)
        bound_domain = self._state.bound_domain(session_id)
        if bound_domain and bound_domain != decision.selection.domain_id:
            raise DomainSelectionError(
                "session belongs to another domain: " + str(session_id),
                code="session_domain_mismatch",
            )
        committed = self._state.commit_interaction(
            subject_decision_id=decision_id,
            decision=decision,
            session_id=session_id,
            action=str(command.get("action_id") or "select_domain"),
            idempotency_key=str(command.get("idempotency_key") or ""),
            input_fingerprint=action_input_fingerprint(
                command.get("action_id"),
                action_input,
            ),
        )
        restored = resolve_domain_routing_decision(committed["decision"])
        if committed.get("created"):
            self._metrics.observe(
                restored,
                latency_ms=(perf_counter() - started) * 1000,
            )
        return self._routing_response(
            restored,
            receipt=committed.get("receipt"),
        )

    def run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["session_id"] = _session_id(normalized, default="default")
        decision_id = str(normalized.get("domain_routing_decision_id") or "").strip()
        if decision_id:
            started = perf_counter()
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
            selector_latency_ms = (perf_counter() - started) * 1000
            self._metrics.observe(decision, latency_ms=selector_latency_ms)
        else:
            decision, selector_latency_ms = self._route_observed(normalized)
            self._state.save(decision, normalized["session_id"])
        if decision.needs_clarification:
            return {
                "status": "NEEDS_CLARIFICATION",
                "session_id": normalized["session_id"],
                "domain_id": None,
                **self._routing_response(decision),
            }
        selected_service = self._host.service(decision.selection)
        routing_evidence = build_domain_routing_evidence(
            decision,
            lineage=self._state.lineage(
                decision,
                normalized["session_id"],
            ),
            selector_latency_ms=selector_latency_ms,
        )
        if bool(normalized.get("async", False)):
            execution_kwargs = async_run_kwargs(normalized)
            execution_kwargs["_domain_routing_evidence"] = routing_evidence
            result = selected_service.run_async(**execution_kwargs)
        else:
            execution_kwargs = run_kwargs(normalized)
            execution_kwargs["_domain_routing_evidence"] = routing_evidence
            result = selected_service.run(**execution_kwargs)
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

    def _route_observed(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[DomainRoutingDecision, float]:
        started = perf_counter()
        decision = self._route(payload)
        latency_ms = (perf_counter() - started) * 1000
        self._metrics.observe(decision, latency_ms=latency_ms)
        return decision, latency_ms

    @staticmethod
    def _routing_response(
        decision: DomainRoutingDecision,
        *,
        receipt: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = {"domain_routing": decision.to_dict()}
        if isinstance(receipt, Mapping):
            response["action_receipt"] = project_action_receipt(
                receipt,
                reused=receipt.get("reused") is True,
            )
        legacy = build_domain_routing_interaction(decision)
        response["interaction"] = project_interaction(
            {**response, "domain_routing_interaction": legacy}
        )
        if decision.needs_clarification:
            response["domain_routing_interaction"] = legacy_domain_routing_interaction(
                response["interaction"], legacy
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
