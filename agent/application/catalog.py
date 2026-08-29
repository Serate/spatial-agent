"""Canonical runtime and Domain capability catalog application.

This module is the single application seam for selecting a cached Runtime and
reading the capability surfaces exposed by its Domain Pack.  It also owns the
small amount of selection policy shared by synchronous, asynchronous and HTTP
callers: workflow normalization, runtime-context snapshots and dynamic tool
registration.  The legacy ``AgentService`` facade delegates here so callers do
not need to know how a Runtime is cached or how a Domain is bound.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from agent.domain_registry import domain_registry
from agent.domain_registry import resolve_domain_id
from agent.runtime_factory import build_runtime, build_runtime_context_snapshot
from agent.application.service_format import normalize_workflow_payload as _legacy_normalize_workflow


def _bind_domain_pack(domain_pack: Any) -> Callable[..., Any]:
    """Bind one explicit Domain Pack to the generic Runtime Factory seam."""
    if domain_pack is None:
        raise ValueError("domain_pack is required")

    def factory(planner: str, backend: str, **kwargs: Any) -> Any:
        return build_runtime(
            planner,
            backend,
            domain_pack=domain_pack,
            **kwargs,
        )

    return factory


def _bind_domain_id(domain_id: str) -> Callable[..., Any]:
    """Bind a registered Domain id without exposing import paths to callers."""
    if not isinstance(domain_id, str) or not domain_id.strip():
        raise ValueError("domain_id must be a non-empty string")

    def factory(planner: str, backend: str, **kwargs: Any) -> Any:
        return build_runtime(
            planner,
            backend,
            domain_id=domain_id,
            **kwargs,
        )

    return factory


class CatalogApplication:
    """Own Runtime selection and Domain capability discovery.

    The interface is intentionally small for callers: ``runtime`` supplies a
    selected adapter, while the catalog methods expose stable projections.
    All stateful selection behaviour is inside this module, which keeps the
    facade and transport adapters from growing their own Runtime policy.
    """

    def __init__(
        self,
        *,
        state: Any,
        runtime_factory: Callable[..., Any],
        configured_domain_id: Optional[str],
        configured_domain_pack: Any,
        resolved_domain_id: Optional[str],
        runtime_context_snapshot: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> None:
        self._state = state
        self._runtime_factory = runtime_factory
        self._configured_domain_id = configured_domain_id
        self._configured_domain_pack = configured_domain_pack
        self._resolved_domain_id = resolved_domain_id
        self._runtime_context_snapshot = runtime_context_snapshot or build_runtime_context_snapshot

    @property
    def runtime_factory(self) -> Callable[..., Any]:
        return self._runtime_factory

    def configured_domain_id(self) -> Optional[str]:
        return self._configured_domain_id

    def resolved_domain_id(self) -> Optional[str]:
        return self._resolved_domain_id

    def runtime(self, planner: str, backend: str) -> Any:
        """Return the cached Runtime and bind its resolved Domain identity."""
        runtime = self._state.runtime(planner, backend)
        runtime_domain_id = getattr(runtime, "domain_id", None)
        if runtime_domain_id:
            self._resolved_domain_id = str(runtime_domain_id)[:80]
        return runtime

    def runtime_context(
        self, planner: str, backend: str
    ) -> Optional[Dict[str, Any]]:
        runtime = self.runtime(planner, backend)
        builder = getattr(runtime, "runtime_context", None)
        value = builder() if callable(builder) else None
        return dict(value) if isinstance(value, dict) else None

    def submission_runtime_context(
        self, planner: str, backend: str
    ) -> Optional[Dict[str, Any]]:
        """Build a context snapshot without blocking asynchronous submission."""
        if self._configured_domain_id or self._runtime_factory is build_runtime:
            return self._runtime_context_snapshot(
                planner,
                backend,
                domain_pack=self._configured_domain_pack,
                domain_id=(
                    None
                    if self._configured_domain_pack is not None
                    else self._configured_domain_id
                ),
            )

        runtimes = self._state.runtimes()
        runtime = runtimes.get((str(planner), str(backend)))
        if runtime is None:
            # Preserve compatibility with old custom state adapters that used
            # a string cache key while keeping tuple keys canonical.
            runtime = runtimes.get(str(planner) + ":" + str(backend))
        builder = getattr(runtime, "runtime_context", None) if runtime else None
        value = builder() if callable(builder) else None
        return dict(value) if isinstance(value, dict) else None

    def domain_id(self, planner: str, backend: str) -> str:
        """Return the selected Domain id, resolving custom factories lazily."""
        if self._resolved_domain_id:
            return self._resolved_domain_id
        runtime = self.runtime(planner, backend)
        return self._resolved_domain_id or str(
            getattr(runtime, "domain_id", "unknown")
        )[:80]

    def normalize_workflow(
        self,
        workflow: Dict[str, Any] | None,
        planner: str,
        backend: str,
    ) -> Dict[str, Any] | None:
        """Normalize an explicit workflow through the selected Domain Pack."""
        if workflow is None:
            return None
        runtime = self.runtime(planner, backend)
        domain_pack = getattr(runtime, "_domain_pack", None)
        normalizer = getattr(domain_pack, "normalize_workflow", None)
        if callable(normalizer):
            value = normalizer(workflow)
            if not isinstance(value, dict):
                value = dict(value) if isinstance(value, Mapping) else None
            if value is None:
                raise ValueError("Domain workflow normalizer must return an object")
            return value
        return _legacy_normalize_workflow(workflow)

    def capabilities(self, planner: str = "rule", backend: str = "memory") -> Dict[str, Any]:
        """Return the selected Domain capability catalog."""
        value = self.runtime(planner, backend).capability_catalog()
        return dict(value) if isinstance(value, Mapping) else {}

    def workflow_contract(
        self, planner: str = "rule", backend: str = "memory"
    ) -> Dict[str, Any]:
        """Return workflow templates and validator inputs for one Domain."""
        runtime = self.runtime(planner, backend)
        resolver = getattr(runtime, "workflow_contract", None)
        if not callable(resolver):
            return self._empty_workflow_contract(planner, backend)
        value = resolver()
        return (
            dict(value)
            if isinstance(value, Mapping)
            else self._empty_workflow_contract(planner, backend)
        )

    def domains(self) -> Dict[str, Any]:
        """Return the bounded deployment Domain Registry catalog."""
        return domain_registry().catalog()

    def actions(self, planner: str = "rule", backend: str = "memory") -> Dict[str, Any]:
        """Return the actions declared by the selected Domain Pack."""
        runtime = self.runtime(planner, backend)
        resolver = getattr(runtime, "domain_actions", None)
        if not callable(resolver):
            return self._empty_actions()
        value = resolver()
        return dict(value) if isinstance(value, Mapping) else self._empty_actions()

    def runtime_capabilities(
        self,
        max_files: int = 10,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return generic runtime evidence from the selected Domain Pack."""
        return self.runtime(planner, backend).runtime_capabilities(max_files=max_files)

    def release_evidence(
        self,
        config_path: str = None,
        max_files: int = 10,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict[str, Any]:
        """Return release evidence from the selected Domain Pack."""
        return self.runtime(planner, backend).release_evidence(
            config_path=config_path,
            max_files=max_files,
        )

    def register_tool(
        self,
        name: str,
        definition: Dict[str, Any],
        handler: Any,
    ) -> Dict[str, Any]:
        """Register one dynamic tool on every live Runtime.

        Registration is deliberately centralized here so a tool added after
        service construction is visible to all cached Runtime adapters and to
        a lazily created default Runtime.
        """
        if not isinstance(definition, dict):
            raise ValueError("definition must be an object")
        registered = None
        for runtime in self._state.runtimes().values():
            registry = getattr(runtime, "_registry", None)
            if registry is not None and hasattr(registry, "register_tool"):
                registered = registry.register_tool(name, definition, handler)
        if registered is None:
            runtime = self.runtime("rule", "memory")
            registered = runtime._registry.register_tool(name, definition, handler)
        return registered

    def list_dynamic_tools(self) -> Dict[str, Any]:
        tools = []
        for runtime in self._state.runtimes().values():
            registry = getattr(runtime, "_registry", None)
            if registry is not None and hasattr(registry, "dynamic_tools"):
                for item in registry.dynamic_tools():
                    if item not in tools:
                        tools.append(item)
        return {"dynamic_tools": tools, "count": len(tools)}

    def _empty_workflow_contract(self, planner: str, backend: str) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id(planner, backend),
            "catalog": {},
            "known_tools": [],
            "known_result_types": [],
        }

    @staticmethod
    def _empty_actions() -> Dict[str, Any]:
        return {
            "schema_version": "spatial-agent.actions.v1",
            "domain_id": "unknown",
            "actions": [],
        }


__all__ = ["CatalogApplication"]
