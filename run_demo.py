import json
import sys
from pathlib import Path

from agent.planner import RuleBasedPlanner
from agent.runtime import AgentRuntime
from agent.tools import DemoSpatialAdapter, ToolRegistry


def build_runtime() -> AgentRuntime:
    root = Path(__file__).parent
    registry = ToolRegistry.from_json(
        str(root / "tools" / "schema" / "tool-definitions.json"),
        DemoSpatialAdapter(),
    )
    return AgentRuntime(RuleBasedPlanner(), registry)


if __name__ == "__main__":
    request = " ".join(sys.argv[1:]) or "查询距离主干道500米以内、坡度超过25度的区域。"
    result = build_runtime().run(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
