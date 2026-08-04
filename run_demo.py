import argparse
import json
from pathlib import Path

from agent.llm_planner import LLMPlanner, OpenAIPlannerClient
from agent.planner import RuleBasedPlanner
from agent.runtime import AgentRuntime
from agent.dataset_catalog import DatasetCatalog
from agent.spatial_backend import HybridSpatialBackend, InMemorySpatialBackend, SpatialToolAdapter
from agent.tools import ToolRegistry


def build_runtime(planner_name: str, backend_name: str = "memory") -> AgentRuntime:
    root = Path(__file__).parent
    if backend_name == "local":
        catalog = DatasetCatalog.from_json(str(root / "config" / "datasets.local.example.json"))
        adapter = SpatialToolAdapter(HybridSpatialBackend(catalog))
    else:
        adapter = SpatialToolAdapter(InMemorySpatialBackend())
    registry = ToolRegistry.from_json(
        str(root / "tools" / "schema" / "tool-definitions.json"),
        adapter,
    )
    if planner_name == "openai":
        planner = LLMPlanner(OpenAIPlannerClient(), registry.names)
    else:
        planner = RuleBasedPlanner()
    return AgentRuntime(planner, registry)


def parse_args():
    parser = argparse.ArgumentParser(description="Run the spatial Agent Runtime demo.")
    parser.add_argument(
        "request",
        nargs="*",
        help="Spatial analysis request. Defaults to the M1 road/slope example.",
    )
    parser.add_argument(
        "--planner",
        choices=("rule", "openai"),
        default="rule",
        help="Planner Adapter to use. openai requires OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--backend",
        choices=("memory", "local"),
        default="memory",
        help="Spatial backend to use. local reads configured datasets where supported.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    request = " ".join(args.request) or "查询距离主干道500米以内、坡度超过25度的区域。"
    result = build_runtime(args.planner, args.backend).run(request)
    print(json.dumps(result.to_dict(), ensure_ascii=True, indent=2))
