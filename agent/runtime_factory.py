"""Runtime factory shared by the CLI, HTTP services, evaluation, and tests.

Kept out of run_demo.py so the agent package never depends on a root-level
demo script (the previous layering inversion). run_demo re-exports this
factory for CLI compatibility.
"""

import os
from pathlib import Path

from .dataset_catalog import DatasetCatalog
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
) -> AgentRuntime:
    root = Path(__file__).resolve().parent.parent
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
        planner = LLMPlanner(OpenAIPlannerClient(**load_openai_config()), registry.names)
    else:
        planner = RuleBasedPlanner()
    return AgentRuntime(
        planner,
        registry,
        state_store=state_store,
        conversation_store=conversation_store,
        memory=memory,
    )
