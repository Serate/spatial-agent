"""Runtime factory shared by the CLI, HTTP services, evaluation, and tests.

Kept out of run_demo.py so the agent package never depends on a root-level
demo script (the previous layering inversion). run_demo re-exports this
factory for CLI compatibility.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .domain_contract import (
    DomainPack,
    default_permissions,
    planner_guidance,
    planner_request_hint,
    rule_planner as resolve_rule_planner,
)
from .domain_registry import resolve_domain_pack
from .general_capability_host import GeneralCapabilityHost
from .general_runtime import GeneralRuntimePack
from .answer_generation import LLMAnswerGenerator
from .agent_settings import open_agent_defaults
from .llm_planner import LLMPlanner, OpenAIPlannerClient
from .network import (
    WebFetchAdapter,
    WebSearchAdapter,
    web_fetch_tool_definition,
    web_search_tool_definition,
)
from agent.integration.openai_config import load_answer_generation_config, load_openai_config
from .planner import RuleBasedPlanner
from .runtime import AgentRuntime
from .tooling import ToolProposalValidator, UnixSocketSandboxClient
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
    approval_store=None,
    allowed_permissions: Optional[Iterable[str]] = None,
    approved_tools: Optional[Iterable[str]] = None,
    require_dependency_evidence: Optional[bool] = None,
    domain_pack: Optional[DomainPack] = None,
    domain_id: Optional[str] = None,
    answer_generator: Any = None,
    event_sink: Optional[Callable[[dict], dict]] = None,
) -> AgentRuntime:
    root = Path(__file__).resolve().parent.parent
    if domain_pack is not None and domain_id is not None:
        raise ValueError("domain_pack and domain_id are mutually exclusive")
    selected_domain_pack = domain_pack or resolve_domain_pack(domain_id)
    agent_defaults = open_agent_defaults()
    provider_factory = getattr(selected_domain_pack, "tool_provider", None)
    if callable(provider_factory):
        provider = provider_factory(backend_name=backend_name, root=root)
        registry = ToolRegistry.from_provider(provider)
    else:
        registry = _legacy_gis_registry(backend_name, root)
    if (
        agent_defaults["web_search_enabled"]
        and agent_defaults.get("web_mode") != "off"
        and "web_search" not in registry.names
    ):
        registry.register_tool(
            "web_search",
            web_search_tool_definition(),
            WebSearchAdapter.from_settings(agent_defaults).invoke,
        )
    if (
        agent_defaults["web_search_enabled"]
        and agent_defaults.get("web_mode") != "off"
        and "web_fetch" not in registry.names
    ):
        registry.register_tool(
            "web_fetch",
            web_fetch_tool_definition(),
            WebFetchAdapter.from_settings(agent_defaults).invoke,
        )
    resolved_answer_generator = answer_generator
    proposal_validator = ToolProposalValidator(
        UnixSocketSandboxClient(
            agent_defaults["tool_proposal_sandbox_socket"],
            timeout_seconds=agent_defaults["tool_proposal_sandbox_timeout_seconds"],
        )
    ) if agent_defaults["tool_proposals_enabled"] else None
    if planner_name == "openai":
        model_config = load_openai_config()
        planner_client = OpenAIPlannerClient(**model_config)
        planner = LLMPlanner(
            planner_client,
            registry.names,
            planner_guidance=planner_guidance(selected_domain_pack),
            request_hint=planner_request_hint(selected_domain_pack),
            react_enabled=(
                bool(getattr(planner_client, "supports_react", False))
                and agent_defaults["react_mode"] != "off"
            ),
        )
        # Keep planner and answer metrics independent.  The second call is
        # intentionally a separate client instance so an answer timeout
        # cannot overwrite the planner evidence persisted for the run.
        if resolved_answer_generator is None:
            resolved_answer_generator = LLMAnswerGenerator(
                OpenAIPlannerClient(**load_answer_generation_config())
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
        approval_store=approval_store,
        backend_name=backend_name,
        planner_name=planner_name,
        answer_generator=resolved_answer_generator,
        proposal_validator=proposal_validator,
        domain_pack=selected_domain_pack,
        allowed_permissions=allowed_permissions,
        approved_tools=approved_tools,
        require_dependency_evidence=require_dependency_evidence,
        event_sink=event_sink,
    )


def build_general_runtime(
    planner_name: str = "openai",
    backend_name: str = "local",
    *,
    host: GeneralCapabilityHost | None = None,
    domain_ids: Iterable[str] | None = None,
    **kwargs: Any,
) -> AgentRuntime:
    """Build the open-request Runtime over all registered Domain Packs.

    The explicit ``build_runtime(..., domain_id=...)`` path remains unchanged
    for single-Domain compatibility.  This helper is the narrow factory seam
    intended for the future default HTTP/CLI/Console entrypoints.
    """

    if "domain_id" in kwargs or "domain_pack" in kwargs:
        raise ValueError("general runtime cannot be combined with an explicit Domain")
    root = Path(__file__).resolve().parent.parent
    selected_host = host or GeneralCapabilityHost(
        backend_name=backend_name,
        root=root,
        domain_ids=domain_ids,
    )
    return build_runtime(
        planner_name,
        backend_name,
        domain_pack=GeneralRuntimePack(selected_host),
        **kwargs,
    )


def build_general_runtime_context_snapshot(
    planner_name: str = "openai",
    backend_name: str = "local",
    *,
    host: GeneralCapabilityHost | None = None,
    domain_ids: Iterable[str] | None = None,
    allowed_permissions: Optional[Iterable[str]] = None,
    approved_tools: Optional[Iterable[str]] = None,
    require_dependency_evidence: Optional[bool] = None,
) -> dict:
    """Build a submission-time context for the general Runtime."""

    root = Path(__file__).resolve().parent.parent
    selected_host = host or GeneralCapabilityHost(
        backend_name=backend_name,
        root=root,
        domain_ids=domain_ids,
    )
    return build_runtime_context_snapshot(
        planner_name,
        backend_name,
        domain_pack=GeneralRuntimePack(selected_host),
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
    agent_defaults = open_agent_defaults()
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
    if (
        agent_defaults["web_search_enabled"]
        and agent_defaults.get("web_mode") != "off"
        and provider_info
    ):
        try:
            provider_info["tool_count"] = int(provider_info.get("tool_count") or 0) + 1
            if agent_defaults.get("web_mode") != "off":
                provider_info["tool_count"] += 1
        except (TypeError, ValueError):
            provider_info["tool_count"] = 1
    return build_runtime_context(
        domain_id=str(getattr(selected_domain_pack, "domain_id", "unknown")),
        planner=planner_name,
        backend=backend_name,
        tool_provider=provider_info,
        permissions=allowed_permissions,
        approved_tools=approved_tools,
        require_dependency_evidence=bool(require_dependency_evidence),
        web_mode=agent_defaults.get("web_mode", "allowlist"),
    )


def _legacy_gis_registry(backend_name: str, root: Path) -> ToolRegistry:
    """Keep older Domain Packs working until they expose ``tool_provider``."""
    from domains.gis.adapters.dataset_catalog import DatasetCatalog
    from domains.gis.adapters.spatial_backend import (
        HybridSpatialBackend,
        InMemorySpatialBackend,
        SpatialToolAdapter,
    )

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
