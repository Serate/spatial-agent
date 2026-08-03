import argparse
import json
from pathlib import Path

from agent.llm_planner import LLMPlanner, OpenAIPlannerClient
from agent.planner import RuleBasedPlanner
from agent.runtime import AgentRuntime
from agent.tools import DemoSpatialAdapter, ToolRegistry


def build_runtime(planner_name: str) -> AgentRuntime:
    root = Path(__file__).parent
    registry = ToolRegistry.from_json(
        str(root / "tools" / "schema" / "tool-definitions.json"),
        DemoSpatialAdapter(),
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    request = " ".join(args.request) or "查询距离主干道500米以内、坡度超过25度的区域。"
    result = build_runtime(args.planner).run(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
