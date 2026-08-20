"""Runtime factory shared by the CLI, HTTP services, evaluation, and tests.

Kept out of run_demo.py so the agent package never depends on a root-level
demo script (the previous layering inversion). run_demo re-exports this
factory for CLI compatibility.
"""

import os
from pathlib import Path
from typing import Iterable, Optional

from .dataset_catalog import DatasetCatalog
from .domain_contract import DomainPack, default_domain_pack, planner_guidance
from .llm_planner import LLMPlanner, OpenAIPlannerClient
from .openai_config import load_openai_config
from .planner import RuleBasedPlanner
from .runtime import AgentRuntime
from .spatial_backend import HybridSpatialBackend, InMemorySpatialBackend, SpatialToolAdapter
from .tools import ToolRegistry


def build_runtime(
    planner_name: str,
    backend_name: str = "memory",
    state_store=None,
    conversation_store=None,
    memory=None,
    observability=None,
    allowed_permissions: Optional[Iterable[str]] = None,
    approved_tools: Optional[Iterable[str]] = None,
    require_dependency_evidence: Optional[bool] = None,
    domain_pack: Optional[DomainPack] = None,
) -> AgentRuntime:
    root = Path(__file__).resolve().parent.parent
    selected_domain_pack = domain_pack or default_domain_pack()
    if backend_name == "local":
        catalog_path = os.environ.get(
            "SPATIAL_AGENT_DATASET_CONFIG",
            str(root / "config" / "datasets.local.example.json"),
        )
        catalog = DatasetCatalog.from_json(catalog_path)
        adapter = SpatialToolAdapter(HybridSpatialBackend(catalog))
    else:
        adapter = SpatialToolAdapter(InMemorySpatialBackend())
    registry = ToolRegistry.from_json(
        str(root / "tools" / "schema" / "tool-definitions.json"),
        adapter,
    )
    if planner_name == "openai":
        planner = LLMPlanner(
            OpenAIPlannerClient(**load_openai_config()),
            registry.names,
            planner_guidance=planner_guidance(selected_domain_pack),
        )
    else:
        planner = RuleBasedPlanner()
    if allowed_permissions is None:
        allowed_permissions = _csv_env("SPATIAL_AGENT_PERMISSIONS") or {
            "spatial_data:read"
        }
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
        backend_name=backend_name,
        domain_pack=selected_domain_pack,
        allowed_permissions=allowed_permissions,
        approved_tools=approved_tools,
        require_dependency_evidence=require_dependency_evidence,
    )


def _csv_env(name: str) -> set[str]:
    value = os.environ.get(name, "")
    return {item.strip() for item in value.split(",") if item.strip()}


def _bool_env(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
