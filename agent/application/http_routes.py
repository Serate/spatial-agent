"""Shared HTTP route metadata for the stdlib and FastAPI adapters.

The adapters still own framework-specific response behavior, streaming, and
parameter injection.  This module owns only the path-to-semantic-action map so
both transports invoke the same ``HTTPApplication`` action for a route.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class RouteMatch:
    """A normalized route with no framework-specific request objects."""

    method: str
    action: str
    path: str
    resource_id: Optional[str] = None
    template_id: Optional[str] = None


@dataclass(frozen=True)
class _RouteSpec:
    method: str
    pattern: re.Pattern[str]
    action: str
    resource_group: Optional[str] = None
    template_group: Optional[str] = None

    def match(self, method: str, path: str) -> Optional[RouteMatch]:
        if method != self.method:
            return None
        found = self.pattern.fullmatch(path)
        if found is None:
            return None
        return RouteMatch(
            method=method,
            action=self.action,
            path=path,
            resource_id=(
                found.group(self.resource_group)
                if self.resource_group is not None
                else None
            ),
            template_id=(
                found.group(self.template_group)
                if self.template_group is not None
                else None
            ),
        )


def _spec(
    method: str,
    pattern: str,
    action: str,
    *,
    resource_group: Optional[str] = None,
    template_group: Optional[str] = None,
) -> _RouteSpec:
    return _RouteSpec(
        method,
        re.compile(pattern),
        action,
        resource_group=resource_group,
        template_group=template_group,
    )


# More specific paths precede their resource-level counterparts.
_ROUTE_SPECS = (
    # GET resources
    _spec("GET", r"/action-executions/(?P<execution_id>[^/]+)", "action_execution", resource_group="execution_id"),
    _spec("GET", r"/action-executions", "action_executions"),
    _spec("GET", r"/capabilities/runtime", "runtime_capabilities"),
    _spec("GET", r"/capabilities", "capabilities"),
    _spec("GET", r"/release-evidence", "release_evidence"),
    _spec("GET", r"/workflows", "workflow"),
    _spec("GET", r"/decisions/(?P<decision_id>[^/]+)", "decision", resource_group="decision_id"),
    _spec("GET", r"/runs/(?P<run_id>[^/]+)/evidence", "run_evidence", resource_group="run_id"),
    _spec("GET", r"/runs/(?P<run_id>[^/]+)/interaction", "run_interaction", resource_group="run_id"),
    _spec("GET", r"/runs/(?P<run_id>[^/]+)/(?:observability|async)", "async_observability", resource_group="run_id"),
    _spec("GET", r"/runs/(?P<run_id>[^/]+)/events", "run_events", resource_group="run_id"),
    _spec("GET", r"/runs/(?P<run_id>[^/]+)", "run", resource_group="run_id"),
    _spec("GET", r"/runs", "runs"),
    _spec("GET", r"/sessions/(?P<session_id>[^/]+)/runs", "session_runs", resource_group="session_id"),
    _spec("GET", r"/sessions", "sessions"),
    _spec("GET", r"/actions", "actions"),
    _spec("GET", r"/metrics", "metrics"),
    _spec("GET", r"/memory", "memory"),
    _spec("GET", r"/observability/health", "observability_health"),
    _spec("GET", r"/tools/dynamic", "dynamic_tools"),
    _spec("GET", r"/tools/approvals/(?P<approval_id>[^/]+)", "tool_approval", resource_group="approval_id"),
    _spec("GET", r"/tools/approvals", "tool_approvals"),
    # POST commands
    _spec("POST", r"/domain-routing/select", "domain_select"),
    _spec("POST", r"/domain-routing/decisions/(?P<run_id>[^/]+)/select", "domain_routing_override", resource_group="run_id"),
    _spec("POST", r"/domain-routing/sessions/(?P<run_id>[^/]+)/clear", "domain_routing_clear", resource_group="run_id"),
    _spec("POST", r"/composite-runs/async", "composite_run_async"),
    _spec("POST", r"/composite-runs", "composite_run"),
    _spec("POST", r"/composite-plans", "composite_plan"),
    _spec("POST", r"/runs/auto", "run_auto"),
    _spec("POST", r"/runs/preview", "preview"),
    _spec("POST", r"/runs/async", "run_async"),
    _spec("POST", r"/runs/(?P<run_id>[^/]+)/retry", "retry", resource_group="run_id"),
    _spec("POST", r"/runs/(?P<run_id>[^/]+)/cancel", "cancel", resource_group="run_id"),
    _spec("POST", r"/runs/(?P<run_id>[^/]+)/interaction", "interaction", resource_group="run_id"),
    _spec("POST", r"/runs", "run"),
    _spec("POST", r"/decisions/(?P<run_id>[^/]+)/resolve", "resolve_decision", resource_group="run_id"),
    _spec("POST", r"/sessions/(?P<run_id>[^/]+)/clear", "session_clear", resource_group="run_id"),
    _spec("POST", r"/sessions", "session_create"),
    _spec("POST", r"/comparisons", "compare"),
    _spec("POST", r"/region-comparisons", "region_compare"),
    _spec("POST", r"/constrained-comparisons", "constrained_compare"),
    _spec("POST", r"/actions/(?P<run_id>[^/]+)", "domain_action", resource_group="run_id"),
    _spec("POST", r"/tools/approvals/(?P<run_id>[^/]+)/resolve", "tool_approval_resolve", resource_group="run_id"),
    _spec("POST", r"/tools", "tool_register"),
    _spec("POST", r"/workflows/(?P<template_id>[^/]+)/(?P<operation>validate|revise)", "workflow_action", template_group="template_id"),
)


def resolve_route(method: str, path: str) -> Optional[RouteMatch]:
    """Resolve a normalized path to one semantic ``HTTPApplication`` action."""

    normalized_method = str(method or "").upper().strip()
    normalized_path = str(path or "/").strip() or "/"
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    for spec in _ROUTE_SPECS:
        match = spec.match(normalized_method, normalized_path)
        if match is not None:
            if match.action == "workflow_action":
                operation = normalized_path.rsplit("/", 1)[-1]
                return RouteMatch(
                    method=match.method,
                    action="workflow_" + operation,
                    path=match.path,
                    template_id=match.template_id,
                )
            return match
    return None


def dispatch_read(
    application: Any,
    path: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Dispatch one shared GET route through ``HTTPApplication.read``."""

    match = resolve_route("GET", path)
    if match is None:
        raise ValueError("unknown GET route: " + str(path))
    return application.read(
        match.action,
        dict(payload or {}),
        resource_id=match.resource_id,
    )


def dispatch_execute(
    application: Any,
    path: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Dispatch one shared POST route through ``HTTPApplication.execute``."""

    match = resolve_route("POST", path)
    if match is None:
        raise ValueError("unknown POST route: " + str(path))
    return application.execute(
        match.action,
        dict(payload or {}),
        run_id=match.resource_id,
        template_id=match.template_id,
    )


__all__ = ["RouteMatch", "dispatch_execute", "dispatch_read", "resolve_route"]
