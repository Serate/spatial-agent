"""Runtime factory shared by the CLI, HTTP services, evaluation, and tests.

Kept out of run_demo.py so the agent package never depends on a root-level
demo script (the previous layering inversion). run_demo re-exports this
factory for CLI compatibility.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Iterable, Optional

from .domain_contract import (
    DomainPack,
    default_permissions,
    planner_guidance,
    planner_request_hint,
    rule_planner as resolve_rule_planner,
)
from .domain_registry import resolve_domain_pack
from .llm_planner import LLMPlanner, OpenAIPlannerClient
from .openai_config import load_openai_config
from .planner import RuleBasedPlanner
from .runtime import AgentRuntime
from .runtime_context import build_runtime_context
from .tools import ToolRegistry


def build_runtime(
    planner_name: str,
    backend_name: str = "memory",
    state_store=None,
    conversation_store=None,
    memory=None,
    observability=None,
    decision_store=None,
    allowed_permissions: Optional[Iterable[str]] = None,
    approved_tools: Optional[Iterable[str]] = None,
    require_dependency_evidence: Optional[bool] = None,
    domain_pack: Optional[DomainPack] = None,
    domain_id: Optional[str] = None,
) -> AgentRuntime:
    root = Path(__file__).resolve().parent.parent
    if domain_pack is not None and domain_id is not None:
        raise ValueError("domain_pack and domain_id are mutually exclusive")
    selected_domain_pack = domain_pack or resolve_domain_pack(domain_id)
    provider_factory = getattr(selected_domain_pack, "tool_provider", None)
    if callable(provider_factory):
        provider = provider_factory(backend_name=backend_name, root=root)
        registry = ToolRegistry.from_provider(provider)
    else:
        registry = _legacy_gis_registry(backend_name, root)
    if planner_name == "openai":
        planner = LLMPlanner(
            OpenAIPlannerClient(**load_openai_config()),
            registry.names,
            planner_guidance=planner_guidance(selected_domain_pack),
            request_hint=planner_request_hint(selected_domain_pack),
        )
    else:
        planner = resolve_rule_planner(selected_domain_pack) or RuleBasedPlanner()
    if allowed_permissions is None:
        allowed_permissions = _csv_env("SPATIAL_AGENT_PERMISSIONS") or default_permissions(
            selected_domain_pack
        )
    if approved_tools is None:
        approved_tools = _csv_env("SPATIAL_AGENT_APPROVED_TOOLS")
    if require_dependency_evidence is None:
        require_dependency_evidence = _bool_env(
            "SPATIAL_AGENT_REQUIRE_DEPENDENCY_EVIDENCE",
            default=False,
        )
    return AgentRuntime(
        planner,
        registry,
        state_store=state_store,
        conversation_store=conversation_store,
        memory=memory,
        observability=observability,
        decision_store=decision_store,
        backend_name=backend_name,
        planner_name=planner_name,
        domain_pack=selected_domain_pack,
        allowed_permissions=allowed_permissions,
        approved_tools=approved_tools,
        require_dependency_evidence=require_dependency_evidence,
    )


def build_runtime_context_snapshot(
    planner_name: str,
    backend_name: str = "memory",
    *,
    domain_pack: Optional[DomainPack] = None,
    domain_id: Optional[str] = None,
    allowed_permissions: Optional[Iterable[str]] = None,
    approved_tools: Optional[Iterable[str]] = None,
    require_dependency_evidence: Optional[bool] = None,
) -> dict:
    """Build submission-time context without initializing a backend."""
    root = Path(__file__).resolve().parent.parent
    if domain_pack is not None and domain_id is not None:
        raise ValueError("domain_pack and domain_id are mutually exclusive")
    selected_domain_pack = domain_pack or resolve_domain_pack(domain_id)
    if allowed_permissions is None:
        allowed_permissions = _csv_env("SPATIAL_AGENT_PERMISSIONS") or default_permissions(
            selected_domain_pack
        )
    if approved_tools is None:
        approved_tools = _csv_env("SPATIAL_AGENT_APPROVED_TOOLS")
    if require_dependency_evidence is None:
        require_dependency_evidence = _bool_env(
            "SPATIAL_AGENT_REQUIRE_DEPENDENCY_EVIDENCE",
            default=False,
        )
    provider_info = {}
    info_factory = getattr(selected_domain_pack, "tool_provider_info", None)
    if callable(info_factory):
        value = info_factory(backend_name=backend_name, root=root)
        if isinstance(value, Mapping):
            provider_info = dict(value)
    return build_runtime_context(
        domain_id=str(getattr(selected_domain_pack, "domain_id", "unknown")),
        planner=planner_name,
        backend=backend_name,
        tool_provider=provider_info,
        permissions=allowed_permissions,
        approved_tools=approved_tools,
        require_dependency_evidence=bool(require_dependency_evidence),
    )


def _legacy_gis_registry(backend_name: str, root: Path) -> ToolRegistry:
    """Keep older Domain Packs working until they expose ``tool_provider``."""
    from .dataset_catalog import DatasetCatalog
    from .spatial_backend import HybridSpatialBackend, InMemorySpatialBackend, SpatialToolAdapter

    if backend_name == "local":
        catalog_path = os.environ.get(
            "SPATIAL_AGENT_DATASET_CONFIG",
            str(root / "config" / "datasets.local.example.json"),
        )
        catalog = DatasetCatalog.from_json(catalog_path)
        adapter = SpatialToolAdapter(HybridSpatialBackend(catalog))
    else:
        adapter = SpatialToolAdapter(InMemorySpatialBackend())
    return ToolRegistry.from_json(
        str(root / "tools" / "schema" / "tool-definitions.json"),
        adapter,
    )


def _csv_env(name: str) -> set[str]:
    value = os.environ.get(name, "")
    return {item.strip() for item in value.split(",") if item.strip()}


def _bool_env(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
