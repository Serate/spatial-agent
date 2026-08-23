"""Versioned, bounded selection of a Domain before planning begins.

The selector sees only a compact discovery projection.  It never receives
tool schemas, backend data, or Python import identities, and it can only
return Domain/capability identities present in that projection.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Protocol
from uuid import uuid4

from agent.domain_registry import DomainRegistry, DomainSelectionError, domain_registry
from agent.domain_selection import DomainSelection, resolve_domain_selection


DOMAIN_DISCOVERY_SCHEMA_VERSION = "spatial-agent.domain-discovery.v1"
DOMAIN_ROUTING_DECISION_SCHEMA_VERSION = "spatial-agent.domain-routing-decision.v1"
DOMAIN_ROUTING_INTERACTION_SCHEMA_VERSION = "spatial-agent.domain-routing-interaction.v1"
_ROUTING_STATES = frozenset({"selected", "ambiguous", "unmatched"})
_RISK_LEVELS = frozenset({"low", "medium", "high", "unknown"})
_IDENTITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,95}$")


class DomainSelectorError(ValueError):
    """Safe failure raised when a selector violates the routing contract."""

    def __init__(self, message: str, *, code: str = "invalid_domain_selector_output"):
        self.code = str(code)[:64]
        super().__init__(message)


@dataclass(frozen=True)
class DomainRoutingCandidate:
    domain_id: str
    label: str
    capability_ids: tuple[str, ...] = ()
    score: int = 0
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "label": self.label,
            "capability_ids": list(self.capability_ids),
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DomainRoutingDecision:
    status: str
    reason_code: str
    selector_id: str
    request_fingerprint: str
    candidates: tuple[DomainRoutingCandidate, ...] = ()
    selection: DomainSelection | None = None
    decision_id: str = ""
    parent_decision_id: str | None = None
    schema_version: str = DOMAIN_ROUTING_DECISION_SCHEMA_VERSION

    @property
    def needs_clarification(self) -> bool:
        return self.status != "selected"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "parent_decision_id": self.parent_decision_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "selector_id": self.selector_id,
            "request_fingerprint": self.request_fingerprint,
            "selection": self.selection.to_dict() if self.selection else None,
            "candidates": [item.to_dict() for item in self.candidates],
        }


class DomainSelector(Protocol):
    """Adapter seam for choosing a Domain from one bounded snapshot."""

    selector_id: str

    def select(self, request: str, snapshot: Mapping[str, Any]) -> DomainRoutingDecision:
        """Return a versioned decision without executing or planning."""


def build_domain_discovery_snapshot(
    *,
    registry: DomainRegistry | None = None,
    enabled_domain_ids: Iterable[str] | None = None,
    environment: str = "unknown",
    max_capabilities_per_domain: int = 32,
) -> dict[str, Any]:
    """Project registered Domain catalogs into a bounded routing context."""

    selected_registry = registry or domain_registry()
    requested = tuple(
        selected_registry.ids() if enabled_domain_ids is None else enabled_domain_ids
    )
    if not requested:
        raise DomainSelectionError(
            "at least one enabled domain is required",
            code="domain_required",
        )
    enabled: list[str] = []
    for value in requested[:16]:
        domain_id = selected_registry.resolve_id(value)
        if domain_id not in enabled:
            enabled.append(domain_id)
    registry_entries = {
        str(item.get("id")): item
        for item in selected_registry.catalog().get("domains", ())
        if isinstance(item, Mapping)
    }
    domains: list[dict[str, Any]] = []
    for domain_id in sorted(enabled):
        pack = selected_registry.resolve(domain_id)
        raw_catalog = pack.capability_catalog(environment=environment)
        raw_capabilities = raw_catalog.get("capabilities", ()) if isinstance(raw_catalog, Mapping) else ()
        capabilities = [
            _project_capability(item)
            for item in list(raw_capabilities)[: max(1, min(int(max_capabilities_per_domain), 64))]
            if isinstance(item, Mapping) and _safe_identity(item.get("id"))
        ]
        entry = registry_entries.get(domain_id, {})
        domains.append(
            {
                "id": domain_id,
                "label": _bounded_text(entry.get("label") or domain_id, 120),
                "description": _bounded_text(entry.get("description"), 320),
                "capabilities": capabilities,
            }
        )
    canonical = json.dumps(domains, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": DOMAIN_DISCOVERY_SCHEMA_VERSION,
        "snapshot_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
        "environment": _bounded_text(environment or "unknown", 32),
        "domains": domains,
    }


class CatalogDomainSelector:
    """Deterministic offline adapter using only Domain-declared request hints."""

    selector_id = "catalog.v1"

    def __init__(self, *, ambiguity_margin: int = 20) -> None:
        self._ambiguity_margin = max(0, min(int(ambiguity_margin), 100))

    def select(self, request: str, snapshot: Mapping[str, Any]) -> DomainRoutingDecision:
        request_text = _normalize_text(request)
        if not request_text:
            raise DomainSelectorError("request is required", code="domain_routing_request_required")
        scored: list[DomainRoutingCandidate] = []
        for domain in _snapshot_domains(snapshot):
            capability_scores: list[tuple[int, str, tuple[str, ...]]] = []
            for capability in domain["capabilities"]:
                score, reasons = _score_capability(request_text, capability)
                if score > 0:
                    capability_scores.append((score, capability["id"], reasons))
            if not capability_scores:
                continue
            capability_scores.sort(key=lambda item: (-item[0], item[1]))
            top_score = capability_scores[0][0]
            selected_capabilities = tuple(
                item[1] for item in capability_scores if item[0] >= top_score - 10
            )[:8]
            reasons = tuple(
                dict.fromkeys(reason for item in capability_scores[:4] for reason in item[2])
            )[:8]
            scored.append(
                DomainRoutingCandidate(
                    domain_id=domain["id"],
                    label=domain["label"],
                    capability_ids=selected_capabilities,
                    score=top_score,
                    reasons=reasons,
                )
            )
        scored.sort(key=lambda item: (-item.score, item.domain_id))
        fingerprint = _request_fingerprint(request)
        if not scored:
            return DomainRoutingDecision(
                decision_id=_new_decision_id(),
                status="unmatched",
                reason_code="no_domain_capability_match",
                selector_id=self.selector_id,
                request_fingerprint=fingerprint,
            )
        top = scored[0]
        competitors = tuple(
            item for item in scored[1:] if top.score - item.score < self._ambiguity_margin
        )
        if competitors:
            return DomainRoutingDecision(
                decision_id=_new_decision_id(),
                status="ambiguous",
                reason_code="multiple_domain_matches",
                selector_id=self.selector_id,
                request_fingerprint=fingerprint,
                candidates=(top, *competitors)[:8],
            )
        return DomainRoutingDecision(
            decision_id=_new_decision_id(),
            status="selected",
            reason_code="unique_domain_match",
            selector_id=self.selector_id,
            request_fingerprint=fingerprint,
            candidates=(top,),
            selection=DomainSelection(domain_id=top.domain_id, source="automatic"),
        )


class ModelDomainSelector:
    """Model adapter restricted to identities from the discovery snapshot.

    ``invoke`` receives a JSON-safe object and must return a mapping.  Prompt
    construction and network transport stay behind the injected callable.
    """

    selector_id = "model.v1"

    def __init__(self, invoke: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
        self._invoke = invoke

    def select(self, request: str, snapshot: Mapping[str, Any]) -> DomainRoutingDecision:
        safe_snapshot = normalize_domain_discovery_snapshot(snapshot)
        payload = {
            "task": "select_domain_identity_only",
            "request": _bounded_text(request, 4000),
            "catalog": safe_snapshot,
            "allowed_statuses": ["selected", "ambiguous", "unmatched"],
        }
        raw = self._invoke(payload)
        if not isinstance(raw, Mapping):
            raise DomainSelectorError("model selector response must be an object")
        return _decision_from_selector_mapping(
            raw,
            request=request,
            snapshot=safe_snapshot,
            selector_id=self.selector_id,
        )


class FallbackDomainSelector:
    """Use an alternate adapter when the preferred selector violates its contract."""

    selector_id = "fallback.v1"

    def __init__(self, primary: DomainSelector, fallback: DomainSelector | None = None) -> None:
        self._primary = primary
        self._fallback = fallback or CatalogDomainSelector()

    def select(self, request: str, snapshot: Mapping[str, Any]) -> DomainRoutingDecision:
        try:
            return self._primary.select(request, snapshot)
        except Exception as exc:
            fallback = self._fallback.select(request, snapshot)
            return DomainRoutingDecision(
                decision_id=fallback.decision_id,
                status=fallback.status,
                reason_code="selector_fallback:" + _error_code(exc),
                selector_id=self.selector_id,
                request_fingerprint=fallback.request_fingerprint,
                candidates=fallback.candidates,
                selection=fallback.selection,
                parent_decision_id=fallback.parent_decision_id,
            )


class DomainRouter:
    """Deep routing module hiding discovery, selector and allowlist validation."""

    def __init__(
        self,
        *,
        registry: DomainRegistry | None = None,
        enabled_domain_ids: Iterable[str] | None = None,
        selector: DomainSelector | None = None,
        environment: str = "unknown",
    ) -> None:
        self._registry = registry or domain_registry()
        requested = tuple(
            self._registry.ids() if enabled_domain_ids is None else enabled_domain_ids
        )
        if not requested:
            raise DomainSelectionError(
                "at least one enabled domain is required",
                code="domain_required",
            )
        self._enabled_domain_ids = tuple(
            dict.fromkeys(self._registry.resolve_id(item) for item in requested)
        )
        self._snapshot = build_domain_discovery_snapshot(
            registry=self._registry,
            enabled_domain_ids=self._enabled_domain_ids,
            environment=environment,
        )
        self._selector = selector or CatalogDomainSelector()

    def catalog(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._snapshot, ensure_ascii=True))

    def route(self, request: str, *, domain_id: str | None = None) -> DomainRoutingDecision:
        if not isinstance(request, str) or not request.strip():
            raise DomainSelectorError("request is required", code="domain_routing_request_required")
        if domain_id is not None and str(domain_id).strip().lower() != "auto":
            selection = self._resolve_enabled(domain_id, source="explicit")
            entry = self._domain_entry(selection.domain_id)
            return DomainRoutingDecision(
                decision_id=_new_decision_id(),
                status="selected",
                reason_code="explicit_domain_selection",
                selector_id="explicit.v1",
                request_fingerprint=_request_fingerprint(request),
                candidates=(DomainRoutingCandidate(selection.domain_id, entry["label"]),),
                selection=selection,
            )
        raw = self._selector.select(request, self._snapshot)
        return self._validate_decision(raw, request=request)

    def override(
        self,
        prior: DomainRoutingDecision | Mapping[str, Any],
        domain_id: str,
    ) -> DomainRoutingDecision:
        previous = resolve_domain_routing_decision(prior, registry=self._registry)
        selection = self._resolve_enabled(domain_id, source="explicit")
        entry = self._domain_entry(selection.domain_id)
        return DomainRoutingDecision(
            decision_id=_new_decision_id(),
            parent_decision_id=previous.decision_id,
            status="selected",
            reason_code="user_domain_override",
            selector_id="user.v1",
            request_fingerprint=previous.request_fingerprint,
            candidates=(DomainRoutingCandidate(selection.domain_id, entry["label"]),),
            selection=selection,
        )

    def restore(
        self,
        request: str,
        domain_id: str,
        *,
        parent_decision_id: str | None = None,
    ) -> DomainRoutingDecision:
        """Reassert a persisted session binding without interpreting again."""

        if not isinstance(request, str) or not request.strip():
            raise DomainSelectorError("request is required", code="domain_routing_request_required")
        selection = self._resolve_enabled(domain_id, source="restored")
        entry = self._domain_entry(selection.domain_id)
        return DomainRoutingDecision(
            decision_id=_new_decision_id(),
            parent_decision_id=_optional_text(parent_decision_id, 96),
            status="selected",
            reason_code="session_domain_restored",
            selector_id="persistence.v1",
            request_fingerprint=_request_fingerprint(request),
            candidates=(DomainRoutingCandidate(selection.domain_id, entry["label"]),),
            selection=selection,
        )

    def resolve(
        self,
        value: DomainRoutingDecision | Mapping[str, Any],
    ) -> DomainRoutingDecision:
        """Validate a restored decision against this deployment's identities."""

        decision = resolve_domain_routing_decision(value, registry=self._registry)
        return self._validate_identities(decision)

    def _resolve_enabled(self, domain_id: str, *, source: str) -> DomainSelection:
        selection = resolve_domain_selection(domain_id, registry=self._registry, source=source)
        if selection.domain_id not in self._enabled_domain_ids:
            raise DomainSelectionError("domain is disabled: " + selection.domain_id, code="domain_disabled")
        return selection

    def _domain_entry(self, domain_id: str) -> Mapping[str, Any]:
        for item in self._snapshot["domains"]:
            if item["id"] == domain_id:
                return item
        raise DomainSelectionError("unknown domain: " + domain_id, code="unknown_domain")

    def _validate_decision(self, value: DomainRoutingDecision, *, request: str) -> DomainRoutingDecision:
        decision = self.resolve(value)
        if decision.request_fingerprint != _request_fingerprint(request):
            raise DomainSelectorError("selector changed request identity", code="domain_routing_request_mismatch")
        return decision

    def _validate_identities(self, decision: DomainRoutingDecision) -> DomainRoutingDecision:
        allowed_capabilities = {
            item["id"]: {capability["id"] for capability in item["capabilities"]}
            for item in self._snapshot["domains"]
        }
        for candidate in decision.candidates:
            if candidate.domain_id not in self._enabled_domain_ids:
                raise DomainSelectorError("selector returned a disabled domain")
            if any(value not in allowed_capabilities[candidate.domain_id] for value in candidate.capability_ids):
                raise DomainSelectorError("selector returned an unknown capability")
        if decision.selection is not None:
            self._resolve_enabled(decision.selection.domain_id, source=decision.selection.source)
        return decision


def resolve_domain_routing_decision(
    value: DomainRoutingDecision | Mapping[str, Any],
    *,
    registry: DomainRegistry | None = None,
) -> DomainRoutingDecision:
    if isinstance(value, DomainRoutingDecision):
        decision = value
    elif isinstance(value, Mapping):
        candidates = tuple(_candidate_from_mapping(item) for item in (value.get("candidates") or ()))
        selection_value = value.get("selection")
        selection = (
            resolve_domain_selection(selection_value, registry=registry)
            if isinstance(selection_value, Mapping)
            else None
        )
        decision = DomainRoutingDecision(
            schema_version=str(value.get("schema_version") or ""),
            decision_id=_bounded_text(value.get("decision_id"), 96),
            parent_decision_id=_optional_text(value.get("parent_decision_id"), 96),
            status=_bounded_text(value.get("status"), 32),
            reason_code=_bounded_text(value.get("reason_code"), 96),
            selector_id=_bounded_text(value.get("selector_id"), 96),
            request_fingerprint=_bounded_text(value.get("request_fingerprint"), 64),
            candidates=candidates,
            selection=selection,
        )
    else:
        raise DomainSelectorError("routing decision must be an object")
    if decision.schema_version != DOMAIN_ROUTING_DECISION_SCHEMA_VERSION:
        raise DomainSelectorError("unsupported routing decision schema")
    if decision.status not in _ROUTING_STATES:
        raise DomainSelectorError("invalid routing decision status")
    if not decision.decision_id or not decision.reason_code or not decision.selector_id:
        raise DomainSelectorError("routing decision identity is incomplete")
    if not re.fullmatch(r"[0-9a-f]{64}", decision.request_fingerprint):
        raise DomainSelectorError("invalid request fingerprint")
    if decision.status == "selected" and decision.selection is None:
        raise DomainSelectorError("selected routing decision requires selection")
    if decision.status != "selected" and decision.selection is not None:
        raise DomainSelectorError("non-selected routing decision cannot carry selection")
    if decision.status == "ambiguous" and len(decision.candidates) < 2:
        raise DomainSelectorError("ambiguous routing decision requires multiple candidates")
    if decision.status == "unmatched" and decision.candidates:
        raise DomainSelectorError("unmatched routing decision cannot carry candidates")
    if decision.selection is not None:
        selection = resolve_domain_selection(decision.selection, registry=registry)
        if not any(item.domain_id == selection.domain_id for item in decision.candidates):
            raise DomainSelectorError("selected domain must be present in candidates")
    return decision


def build_domain_routing_interaction(
    value: DomainRoutingDecision | Mapping[str, Any],
    *,
    registry: DomainRegistry | None = None,
) -> dict[str, Any]:
    """Project one routing decision into the generic schema-driven Action Host."""

    decision = resolve_domain_routing_decision(value, registry=registry)
    candidate_ids = [item.domain_id for item in decision.candidates]
    actions: list[dict[str, Any]] = []
    if decision.status == "ambiguous" and candidate_ids:
        actions.append(
            {
                "id": "select_domain",
                "label": "选择领域",
                "description": "选择由哪个已注册领域继续处理当前请求。",
                "input_schema": {
                    "type": "object",
                    "required": ["domain_id"],
                    "properties": {
                        "domain_id": {
                            "type": "string",
                            "title": "领域",
                            "enum": candidate_ids,
                        }
                    },
                    "additionalProperties": False,
                },
            }
        )
    state = {
        "selected": "completed",
        "ambiguous": "candidate_selection",
        "unmatched": "unavailable",
    }[decision.status]
    return {
        "schema_version": DOMAIN_ROUTING_INTERACTION_SCHEMA_VERSION,
        "available": bool(actions),
        "state": state,
        "reason_code": decision.reason_code,
        "decision_id": decision.decision_id,
        "candidates": [item.to_dict() for item in decision.candidates],
        "allowed_actions": [item["id"] for item in actions],
        "actions": actions,
    }


def normalize_domain_discovery_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly rebuild a discovery snapshot before it crosses an adapter seam."""

    if not isinstance(snapshot, Mapping):
        raise DomainSelectorError("domain discovery snapshot must be an object")
    if snapshot.get("schema_version") != DOMAIN_DISCOVERY_SCHEMA_VERSION:
        raise DomainSelectorError("unsupported domain discovery schema")
    domains: list[dict[str, Any]] = []
    for raw_domain in list(snapshot.get("domains") or ())[:16]:
        if not isinstance(raw_domain, Mapping):
            continue
        domain_id = _safe_identity(raw_domain.get("id"))
        if not domain_id:
            continue
        capabilities: list[dict[str, Any]] = []
        for raw_capability in list(raw_domain.get("capabilities") or ())[:64]:
            if not isinstance(raw_capability, Mapping):
                continue
            capability_id = _safe_identity(raw_capability.get("id"))
            if not capability_id:
                continue
            hints = (
                raw_capability.get("request_hints")
                if isinstance(raw_capability.get("request_hints"), Mapping)
                else {}
            )
            required = (
                raw_capability.get("required_facts")
                if isinstance(raw_capability.get("required_facts"), Mapping)
                else {}
            )
            risk = _bounded_text(raw_capability.get("risk_level") or "unknown", 16).lower()
            if risk not in _RISK_LEVELS:
                risk = "unknown"
            capabilities.append(
                {
                    "id": capability_id,
                    "label": _bounded_text(
                        raw_capability.get("label") or capability_id,
                        120,
                    ),
                    "purpose": _bounded_text(raw_capability.get("purpose"), 320),
                    "request_hints": {
                        "phrases": _bounded_text_list(hints.get("phrases"), 16, 80),
                        "tasks": _bounded_identity_list(hints.get("tasks"), 16),
                        "datasets": _bounded_identity_list(hints.get("datasets"), 16),
                        "constraints": _bounded_identity_list(hints.get("constraints"), 16),
                    },
                    "required_facts": {
                        "entities": _bounded_identity_list(required.get("entities"), 16),
                        "datasets": _bounded_identity_list(required.get("datasets"), 16),
                        "constraints": _bounded_identity_list(required.get("constraints"), 16),
                    },
                    "risk_level": risk,
                }
            )
        domains.append(
            {
                "id": domain_id,
                "label": _bounded_text(raw_domain.get("label") or domain_id, 120),
                "description": _bounded_text(raw_domain.get("description"), 320),
                "capabilities": capabilities,
            }
        )
    canonical = json.dumps(domains, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": DOMAIN_DISCOVERY_SCHEMA_VERSION,
        "snapshot_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
        "environment": _bounded_text(snapshot.get("environment") or "unknown", 32),
        "domains": domains,
    }


def _decision_from_selector_mapping(
    value: Mapping[str, Any],
    *,
    request: str,
    snapshot: Mapping[str, Any],
    selector_id: str,
) -> DomainRoutingDecision:
    status = _bounded_text(value.get("status"), 32).lower()
    if status not in _ROUTING_STATES:
        raise DomainSelectorError("model selector returned an invalid status")
    domains = {item["id"]: item for item in _snapshot_domains(snapshot)}
    raw_candidates = value.get("candidates") or ()
    if status == "selected" and not raw_candidates:
        raw_candidates = ({
            "domain_id": value.get("domain_id"),
            "capability_ids": value.get("capability_ids") or (),
            "score": value.get("score", 0),
            "reasons": value.get("reasons") or (),
        },)
    candidates: list[DomainRoutingCandidate] = []
    for raw in list(raw_candidates)[:8]:
        candidate = _candidate_from_mapping(raw)
        domain = domains.get(candidate.domain_id)
        if domain is None:
            raise DomainSelectorError("model selector returned an unknown domain")
        allowed = {item["id"] for item in domain["capabilities"]}
        if any(item not in allowed for item in candidate.capability_ids):
            raise DomainSelectorError("model selector returned an unknown capability")
        candidates.append(
            DomainRoutingCandidate(
                domain_id=candidate.domain_id,
                label=domain["label"],
                capability_ids=candidate.capability_ids,
                score=candidate.score,
                reasons=candidate.reasons,
            )
        )
    selection = None
    if status == "selected":
        if len(candidates) != 1:
            raise DomainSelectorError("selected model result requires one candidate")
        selection = DomainSelection(candidates[0].domain_id, source="automatic")
    elif status == "ambiguous" and len(candidates) < 2:
        raise DomainSelectorError("ambiguous model result requires multiple candidates")
    elif status == "unmatched" and candidates:
        raise DomainSelectorError("unmatched model result cannot carry candidates")
    return DomainRoutingDecision(
        decision_id=_new_decision_id(),
        status=status,
        reason_code=_bounded_text(value.get("reason_code") or ("model_" + status), 96),
        selector_id=selector_id,
        request_fingerprint=_request_fingerprint(request),
        candidates=tuple(candidates),
        selection=selection,
    )


def _project_capability(value: Mapping[str, Any]) -> dict[str, Any]:
    hints = value.get("request_hints") if isinstance(value.get("request_hints"), Mapping) else {}
    requirements = (
        value.get("request_requirements")
        if isinstance(value.get("request_requirements"), Mapping)
        else {}
    )
    risk = _bounded_text(value.get("risk_level") or value.get("risk") or "unknown", 16).lower()
    if risk not in _RISK_LEVELS:
        risk = "unknown"
    return {
        "id": _safe_identity(value.get("id")),
        "label": _bounded_text(value.get("label") or value.get("id"), 120),
        "purpose": _bounded_text(value.get("description") or value.get("label"), 320),
        "request_hints": {
            "phrases": _bounded_text_list(hints.get("phrases"), 16, 80),
            "tasks": _bounded_identity_list(hints.get("tasks"), 16),
            "datasets": _bounded_identity_list(hints.get("datasets"), 16),
            "constraints": _bounded_identity_list(hints.get("constraints"), 16),
        },
        "required_facts": {
            "entities": _bounded_identity_list(requirements.get("entities"), 16),
            "datasets": _bounded_identity_list(requirements.get("datasets"), 16),
            "constraints": _bounded_identity_list(requirements.get("constraints"), 16),
        },
        "risk_level": risk,
    }


def _score_capability(request: str, capability: Mapping[str, Any]) -> tuple[int, tuple[str, ...]]:
    hints = capability.get("request_hints") or {}
    hits: list[tuple[int, str]] = []
    for phrase in hints.get("phrases", ()):
        normalized = _normalize_text(phrase)
        if normalized and normalized in request:
            hits.append((100 + min(len(normalized), 40), "phrase:" + phrase))
    label = _normalize_text(capability.get("label"))
    if label and label in request:
        hits.append((90 + min(len(label), 30), "label:" + capability["id"]))
    for category in ("tasks", "datasets", "constraints"):
        for identity in hints.get(category, ()):
            normalized = _normalize_text(str(identity).replace("_", " "))
            if normalized and normalized in request:
                hits.append((70 + min(len(normalized), 20), category + ":" + identity))
    if not hits:
        return 0, ()
    hits.sort(key=lambda item: (-item[0], item[1]))
    return hits[0][0] + min(20, 5 * (len(hits) - 1)), tuple(item[1] for item in hits[:8])


def _snapshot_domains(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return normalize_domain_discovery_snapshot(snapshot)["domains"]


def _candidate_from_mapping(value: Any) -> DomainRoutingCandidate:
    if not isinstance(value, Mapping):
        raise DomainSelectorError("routing candidate must be an object")
    domain_id = _safe_identity(value.get("domain_id"))
    if not domain_id:
        raise DomainSelectorError("routing candidate domain_id is invalid")
    return DomainRoutingCandidate(
        domain_id=domain_id,
        label=_bounded_text(value.get("label") or domain_id, 120),
        capability_ids=tuple(_bounded_identity_list(value.get("capability_ids"), 8)),
        score=max(0, min(int(value.get("score") or 0), 1000)),
        reasons=tuple(_bounded_text_list(value.get("reasons"), 8, 120)),
    )


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _optional_text(value: Any, limit: int) -> str | None:
    text = _bounded_text(value, limit)
    return text or None


def _safe_identity(value: Any) -> str:
    text = _bounded_text(value, 96)
    return text if _IDENTITY_RE.fullmatch(text) else ""


def _bounded_text_list(value: Any, count: int, width: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [text for item in value[:count] if (text := _bounded_text(item, width))]


def _bounded_identity_list(value: Any, count: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [identity for item in value[:count] if (identity := _safe_identity(item))]


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _request_fingerprint(request: str) -> str:
    return hashlib.sha256(_normalize_text(request).encode("utf-8")).hexdigest()


def _new_decision_id() -> str:
    return "domain-decision-" + uuid4().hex


def _error_code(exc: Exception) -> str:
    return _bounded_text(getattr(exc, "code", None) or exc.__class__.__name__, 64).lower()
