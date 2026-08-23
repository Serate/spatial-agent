import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.artifact_store import ArtifactStore
from agent.domain_contract import planner_guidance
from agent.llm_planner import LLMPlanner
from agent.planner_context import PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION
from agent.runtime_factory import build_runtime
from agent.service import AgentService
from domains.gis.domain import GIS_DOMAIN_PACK


COMPLEX_REQUEST = (
    "请对洪山区进行综合空间分析：查询行政区边界，统计DEM高程与坡度，"
    "分析土地利用分布，汇总道路和水体，并筛选坡度不超过20度、"
    "距离道路不超过1000米且排除水体的建设候选区域。"
)


class M229PlannerContextTests(unittest.TestCase):
    def test_complex_request_uses_bounded_projection_without_losing_source_evidence(self):
        runtime = build_runtime("rule", "memory")
        packet = runtime._build_context_packet(
            COMPLEX_REQUEST,
            COMPLEX_REQUEST,
            "m229-context",
            None,
        )

        planner = packet.payload["sections"]
        source = packet.source_payload["sections"]
        self.assertLessEqual(len(packet.rendered), 12000)
        self.assertFalse(packet.evidence["truncated"])
        self.assertEqual(
            packet.evidence["projection_schema_version"],
            PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION,
        )
        self.assertIn("actions", source["capability_catalog"])
        self.assertNotIn("actions", planner["capability_catalog"])
        self.assertIn("candidate_details", source["workflow_selection"])
        self.assertNotIn("candidate_details", planner["workflow_selection"])
        self.assertEqual(
            planner["workflow_selection"]["selected_capability_id"],
            "spatial_analysis",
        )
        self.assertGreaterEqual(
            len(planner["capability_catalog"]["tool_schemas"]), 9
        )
        llm_planner = LLMPlanner(
            object(),
            runtime._registry.names,
            planner_guidance=planner_guidance(GIS_DOMAIN_PACK),
        )
        self.assertLessEqual(
            len(packet.rendered) + len(llm_planner._system_prompt(packet.payload)),
            16000,
        )

    def test_unavailable_local_backend_enters_recoverable_runtime_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="m229-unavailable-") as directory:
            root = Path(directory)
            config = root / "datasets.json"
            config.write_text(
                json.dumps(
                    {
                        "root": str(root / "missing-data"),
                        "datasets": {
                            "admin_areas": {
                                "kind": "vector",
                                "format": "geojson",
                                "path": "missing.geojson",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"SPATIAL_AGENT_DATASET_CONFIG": str(config)},
            ):
                service = AgentService(
                    domain_id="gis",
                    state_db_path=str(root / "state.sqlite"),
                    artifact_store=ArtifactStore(root / "artifacts"),
                )
                try:
                    result = service.run(
                        "查询洪山区行政区边界",
                        session_id="m229-unavailable",
                        planner="rule",
                        backend="local",
                    )
                finally:
                    service.close()

        interaction = result["result"]["interaction"]
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], "backend_initialization_unavailable")
        self.assertEqual(interaction["state"], "recoverable")
        self.assertEqual(
            [item["id"] for item in interaction["actions"]],
            ["retry", "recover", "cancel"],
        )


if __name__ == "__main__":
    unittest.main()
