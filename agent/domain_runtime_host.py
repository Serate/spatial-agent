"""Multi-Domain application host for isolated :class:`AgentService` instances."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import os
from threading import RLock
from typing import Any

from agent.domain_registry import DomainRegistry, DomainSelectionError, domain_registry
from agent.domain_selection import (
    DOMAIN_SELECTION_SCHEMA_VERSION,
    DomainSelection,
    resolve_domain_selection,
)


DOMAIN_RUNTIME_HOST_SCHEMA_VERSION = "spatial-agent.domain-runtime-host.v1"


class DomainRuntimeHostError(RuntimeError):
    """Machine-readable lifecycle failure at the multi-Domain host seam."""

    def __init__(self, message: str, *, code: str):
        self.code = str(code)[:64]
        super().__init__(message)


class DomainRuntimeHost:
    """Own and isolate one application service per enabled Domain.

    The Host deliberately does not interpret natural language, choose a
    planner, or inspect Domain internals.  It centralizes allowlist selection,
    concurrent service creation, eager recovery startup, and resource
    ownership behind a small interface.
    """

    def __init__(
        self,
        *,
        registry: DomainRegistry | None = None,
        service_factory: Callable[[str], Any] | None = None,
        enabled_domain_ids: Iterable[str] | None = None,
        legacy_domain_id: str | None = None,
    ) -> None:
        self._registry = registry or domain_registry()
        requested_ids = (
            tuple(enabled_domain_ids)
            if enabled_domain_ids is not None
            else self._registry.ids()
        )
        if not requested_ids:
            raise DomainSelectionError(
                "at least one enabled domain is required",
                code="domain_required",
            )
        normalized_ids: list[str] = []
        for domain_id in requested_ids:
            resolved = self._registry.resolve_id(domain_id)
            if resolved not in normalized_ids:
                normalized_ids.append(resolved)
        self._enabled_domain_ids = tuple(sorted(normalized_ids))
        legacy_value = legacy_domain_id or os.environ.get(
            "SPATIAL_AGENT_LEGACY_DOMAIN"
        )
        self._legacy_domain_id = (
            self._registry.resolve_id(legacy_value) if legacy_value else None
        )
        self._service_factory = service_factory or self._default_service_factory
        self._services: dict[str, Any] = {}
        self._started_service_ids: set[str] = set()
        self._started = False
        self._closed = False
        self._lock = RLock()

    def _default_service_factory(self, domain_id: str) -> Any:
        from agent.service import AgentService

        return AgentService(
            domain_id=domain_id,
            legacy_domain_id=self._legacy_domain_id or domain_id,
        )

    def catalog(self) -> dict[str, Any]:
        """Return the bounded deployment catalog without creating services."""

        source = self._registry.catalog()
        enabled = set(self._enabled_domain_ids)
        domains = [item for item in source.get("domains", []) if item.get("id") in enabled]
        return {
            "schema_version": DOMAIN_RUNTIME_HOST_SCHEMA_VERSION,
            "selection_schema_version": DOMAIN_SELECTION_SCHEMA_VERSION,
            "legacy_domain_id": self._legacy_domain_id,
            "domain_ids": list(self._enabled_domain_ids),
            "domains": domains,
        }

    def select(
        self,
        value: DomainSelection | Mapping[str, Any] | str,
        *,
        source: str = "explicit",
    ) -> DomainSelection:
        """Validate one transport-neutral selection against enabled Domains."""

        selection = resolve_domain_selection(
            value,
            registry=self._registry,
            source=source,
        )
        if selection.domain_id not in self._enabled_domain_ids:
            raise DomainSelectionError(
                "domain is disabled: " + selection.domain_id,
                code="domain_disabled",
            )
        return selection

    def service(self, selection: DomainSelection | Mapping[str, Any] | str) -> Any:
        """Return the stable, isolated service owned by one selected Domain."""

        selected = self.select(selection)
        with self._lock:
            self._ensure_open()
            service = self._services.get(selected.domain_id)
            if service is None:
                service = self._service_factory(selected.domain_id)
                if service is None:
                    raise DomainRuntimeHostError(
                        "service factory returned no service for " + selected.domain_id,
                        code="service_factory_failed",
                    )
                self._services[selected.domain_id] = service
            if self._started:
                self._start_service(selected.domain_id, service)
            return service

    def start(self) -> None:
        """Eagerly create every enabled Domain so each can recover its jobs."""

        with self._lock:
            self._ensure_open()
            if self._started:
                return
            try:
                for domain_id in self._enabled_domain_ids:
                    service = self._services.get(domain_id)
                    if service is None:
                        service = self._service_factory(domain_id)
                        if service is None:
                            raise DomainRuntimeHostError(
                                "service factory returned no service for " + domain_id,
                                code="service_factory_failed",
                            )
                        self._services[domain_id] = service
                    self._start_service(domain_id, service)
                self._started = True
            except Exception as exc:
                self._closed = True
                try:
                    self._close_owned_services()
                except Exception as cleanup_exc:
                    raise DomainRuntimeHostError(
                        "domain runtime host failed to start and clean up",
                        code="host_start_failed",
                    ) from cleanup_exc
                raise DomainRuntimeHostError(
                    "domain runtime host failed to start",
                    code="host_start_failed",
                ) from exc

    def close(self) -> None:
        """Idempotently close every owned service and reject future access."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._close_owned_services()

    def _start_service(self, domain_id: str, service: Any) -> None:
        if domain_id in self._started_service_ids:
            return
        start_reaper = getattr(service, "start_reaper", None)
        if callable(start_reaper):
            start_reaper()
        self._started_service_ids.add(domain_id)

    def _close_owned_services(self) -> None:
        first_error: Exception | None = None
        for domain_id in reversed(tuple(self._services)):
            close = getattr(self._services[domain_id], "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception as exc:  # best-effort closure of all owned resources
                first_error = first_error or exc
        self._services.clear()
        self._started_service_ids.clear()
        self._started = False
        if first_error is not None:
            raise DomainRuntimeHostError(
                "one or more domain services failed to close",
                code="host_close_failed",
            ) from first_error

    def _ensure_open(self) -> None:
        if self._closed:
            raise DomainRuntimeHostError(
                "domain runtime host is closed",
                code="host_closed",
            )

    def __enter__(self) -> "DomainRuntimeHost":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
