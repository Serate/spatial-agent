"""Small offline developer gate for the shared Agent Runtime contract."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from evaluation.contract_harness import compare_results


class DevGateTests(unittest.TestCase):
    def test_runtime_result_and_artifact_share_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(artifact_store=ArtifactStore(str(Path(directory) / "runs")))
            payload = service.run(
                "查询洪山区行政区边界",
                session_id="dev-gate",
                planner="rule",
                backend="memory",
                export_artifact=True,
            )
            artifact = json.loads(Path(payload["artifact_ref"]).read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["result"]["type"], "admin_area_result")
        self.assertTrue(payload["answer"])
        self.assertTrue(payload["trace_summary"])
        self.assertEqual(compare_results([payload, artifact]), [])

    def test_clarification_follow_up_is_session_scoped(self):
        service = AgentService()
        first = service.run("查询行政区边界", session_id="dev-clarification")
        second = service.run("洪山区", session_id="dev-clarification")

        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertIn("memory://range/admin_areas", second["answer"])

    def test_service_smoke_covers_raster_and_tool_dispatch(self):
        service = AgentService()
        raster = service.run("查询DEM栅格元数据", session_id="dev-raster")
        road = service.run(
            "查询距离主干道500米以内、坡度超过25度的区域。",
            session_id="dev-road",
        )

        self.assertEqual(raster["status"], "COMPLETED")
        self.assertEqual(raster["steps"][0]["tool"], "get_raster_metadata")
        self.assertEqual(road["status"], "COMPLETED")
        self.assertTrue(road["steps"])


if __name__ == "__main__":
    unittest.main()
