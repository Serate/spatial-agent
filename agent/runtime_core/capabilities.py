"""Domain-neutral Runtime capability and deployment evidence surface."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any, Callable, Dict, Mapping, Optional

from ..deployment_evidence import build_deployment_evidence
from ..domain_contract import (
    DomainPack,
    domain_action_catalog,
    release_evidence as resolve_release_evidence,
    runtime_evidence as resolve_runtime_evidence,
    workflow_catalog as resolve_workflow_catalog,
)
from ..evidence_contract import project_capability_catalog_evidence
from .projection import capability_evidence_cache_ttl


class RuntimeCapabilitySurface:
    """Expose catalog, provider health, and release evidence behind one seam.

    Capability evidence is advisory for planning.  The Runtime's execution
    preflight and evidence revalidation remain the authorization gates; this
    module only owns bounded discovery and deployment projections.
    """

    _evidence_cache: Dict[tuple[Any, ...], tuple[float, Any, Mapping[str, Any]]] = {}
    _evidence_cache_lock = Lock()
    _evidence_cache_limit = 32

    def __init__(
        self,
        *,
        domain_pack: DomainPack,
        backend_name: str,
        registry: Any,
        domain_id: Callable[[], str],
        runtime_context: Callable[[], Mapping[str, Any]],
    ):
        self._domain_pack = domain_pack
        self._backend_name = str(backend_name or "unknown")[:80]
        self._registry = registry
        self._domain_id = domain_id
        self._runtime_context = runtime_context

    def capability_catalog(self) -> Mapping[str, Any]:
        catalog = self._domain_pack.capability_catalog(environment=self._backend_name)
        return dict(catalog) if isinstance(catalog, Mapping) else {}

    def domain_actions(self) -> Dict[str, Any]:
        return domain_action_catalog(self._domain_pack)

    def workflow_template_catalog(self) -> Dict[str, Dict[str, Any]]:
        return resolve_workflow_catalog(self._domain_pack)

    def workflow_contract(self) -> Dict[str, Any]:
        catalog = self.workflow_template_catalog()
        result_types = sorted(
            {
                str(result_type)
                for template in catalog.values()
                if isinstance(template, Mapping)
                for result_type in (template.get("result_types") or [])
                if str(result_type).strip()
            }
        )
        return {
            "domain_id": self._domain_id(),
            "catalog": catalog,
            "known_tools": list(self._registry.names),
            "known_result_types": result_types,
        }

    def runtime_capabilities(self, *, max_files: int = 10) -> Dict[str, Any]:
        if not isinstance(max_files, int) or max_files < 1 or max_files > 10:
            raise ValueError("max_files must be between 1 and 10")
        snapshot = dict(self.capability_catalog())
        snapshot.setdefault("actions", self.domain_actions())
        snapshot.update(
            {
                "domain_id": self._domain_id(),
                "runtime_context": self._runtime_context(),
                "runtime": {
                    "backend": self._backend_name,
                    "domain_id": self._domain_id(),
                },
                "tool_provider": self._registry.provider_info(),
                "tool_provider_health": self._registry.provider_health(),
                "tool_governance": self._registry.governance_summary(max_tools=32),
                "health_status": "not_evaluated",
                "data_readiness": "not_evaluated",
                "data_evidence": {},
                "data_provenance": {},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        try:
            evidence = resolve_runtime_evidence(self._domain_pack, max_files=max_files)
        except Exception:
            evidence = {
                "health_status": "unavailable",
                "evidence_error_code": "domain_runtime_evidence_unavailable",
            }
        capability_runtime = evidence.get("capabilities_runtime")
        if isinstance(capability_runtime, list):
            snapshot["capabilities"] = capability_runtime[:32]
        for key, value in evidence.items():
            if key not in {
                "capabilities",
                "capabilities_runtime",
                "tool_provider",
                "tool_provider_health",
                "tool_governance",
            }:
                snapshot[key] = value
        context = snapshot.get("runtime_context")
        if isinstance(context, Mapping) and context.get("fingerprint"):
            snapshot["runtime_context_fingerprint"] = str(context["fingerprint"])
        snapshot = project_capability_catalog_evidence(snapshot, runtime_evidence=evidence)
        snapshot["deployment_evidence"] = build_deployment_evidence(
            {"runtime_context": context, "runtime_evidence": snapshot},
            degradation=snapshot.get("degradation"),
        )
        return snapshot

    def release_evidence(
        self,
        *,
        config_path: Optional[str] = None,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        if not isinstance(max_files, int) or max_files < 1 or max_files > 10:
            raise ValueError("max_files must be between 1 and 10")
        evidence = resolve_release_evidence(
            self._domain_pack,
            config_path=config_path,
            max_files=max_files,
        )
        evidence = dict(evidence) if isinstance(evidence, Mapping) else {}
        evidence.setdefault("domain_id", self._domain_id())
        context = self._runtime_context()
        evidence["runtime_context"] = context
        evidence["runtime_context_fingerprint"] = context["fingerprint"]
        evidence["deployment_evidence"] = build_deployment_evidence(
            {
                "domain_id": evidence.get("domain_id"),
                "runtime_context": context,
                "release_evidence": evidence,
            },
            model_evidence=None,
        )
        return evidence

    def context_evidence(self) -> Mapping[str, Any]:
        provider_factory = getattr(self._domain_pack, "evidence_provider", None)
        provider = provider_factory() if callable(provider_factory) else None
        provider_key = id(provider) if provider is not None else id(self._domain_pack)
        config_key = os.environ.get("SPATIAL_AGENT_DATASET_CONFIG", "")[:240]
        key = (self._domain_id(), self._backend_name, provider_key, config_key)
        ttl = capability_evidence_cache_ttl()
        now = monotonic()
        if ttl > 0:
            with self._evidence_cache_lock:
                cached = self._evidence_cache.get(key)
                if cached is not None and now - cached[0] < ttl:
                    value = cached[2]
                    return dict(value) if isinstance(value, Mapping) else {}
        try:
            value = resolve_runtime_evidence(self._domain_pack, max_files=1)
        except Exception:
            value = {
                "health_status": "unavailable",
                "errors": ["capability_evidence_provider_unavailable"],
            }
        if not isinstance(value, Mapping):
            value = {"health_status": "unknown"}
        value = dict(value)
        if ttl > 0:
            with self._evidence_cache_lock:
                self._evidence_cache[key] = (now, provider, value)
                while len(self._evidence_cache) > self._evidence_cache_limit:
                    oldest = min(self._evidence_cache, key=lambda item: self._evidence_cache[item][0])
                    self._evidence_cache.pop(oldest, None)
        return value
