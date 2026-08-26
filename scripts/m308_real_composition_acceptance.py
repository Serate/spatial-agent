"""M308-B real Docker execution acceptance without a provider call.

This script deliberately uses a replayed, bounded planner decision.  The
selected capabilities, workflows, TaskPlans, ToolRegistry policy and
execution binding still come from the real Domain Host and services.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from agent.application.composite import CompositeApplication
from agent.application.composite_planning import (
    CompositeCapabilityProjector,
    CompositePlanningApplication,
)
from agent.composite_planner import ReplayCompositePlanner
from agent.domain_runtime_host import DomainRuntimeHost


def _payload() -> dict[str, Any]:
    return {
        "outcome": "success",
        "goal": "组合真实空间与指标目录分析",
        "message": "",
        "components": [
            {
                "component_id": "space",
                "domain_id": "gis",
                "capability_id": "spatial_overview",
                "request": "查询洪山区空间总览",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "economic_catalog",
                "domain_id": "economic",
                "capability_id": "economic_indicator_discovery",
                "request": "列出可用经济指标",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "regional_catalog",
                "domain_id": "indicators",
                "capability_id": "indicator_discovery",
                "request": "列出可用区域指标",
                "depends_on": [],
                "required": True,
            },
        ],
    }


def _safe_output(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    composite = result.get("composite") if isinstance(result.get("composite"), dict) else {}
    components = composite.get("components") if isinstance(composite.get("components"), list) else []
    return {
        "status": response.get("status"),
        "state": composite.get("state"),
        "component_count": len(components),
        "component_states": {
            str(item.get("component_id")): item.get("state")
            for item in components
            if isinstance(item, dict)
        },
        "data_kinds": (result.get("data_profile") or {}).get("kinds", []),
        "input_states": {
            str(item.get("component_id")): (item.get("input_evidence") or {}).get("state")
            for item in components
            if isinstance(item, dict) and isinstance(item.get("input_evidence"), dict)
        },
    }


def main() -> int:
    host = DomainRuntimeHost()
    host.start()
    try:
        planning = CompositePlanningApplication(
            host=host,
            projector=CompositeCapabilityProjector(host),
            planner=ReplayCompositePlanner(_payload()),
            composite_runs=object(),
        ).prepare(
            "请组合分析洪山区空间总览、经济指标目录和区域指标目录",
            # Replay is the injected Composite planner implementation.  The
            # Domain runtimes still receive their supported deterministic
            # planner selection rather than an unsupported transport label.
            planner_name="rule",
            backend="local",
            domain_ids=["gis", "economic", "indicators"],
        )
        if planning.get("status") != "PLANNED":
            print(json.dumps({
                "status": "PLANNING_FAILED",
                "error_code": planning.get("error_code"),
                "message": planning.get("message"),
            }, ensure_ascii=False))
            return 1
        binding = getattr(planning, "execution_binding", None)
        if not isinstance(binding, dict):
            print(json.dumps({"status": "BINDING_MISSING"}, ensure_ascii=False))
            return 1
        response = CompositeApplication(
            host=host,
            require_execution_binding=True,
        ).run(
            planning["request"],
            session_id="m308-real-acceptance",
            run_id="m308-real-composition",
            execution_binding=binding,
        )
        output = _safe_output(response)
        print(json.dumps(output, ensure_ascii=False))
        return 0 if output["status"] == "COMPLETED" else 1
    finally:
        host.close()


if __name__ == "__main__":
    sys.exit(main())
