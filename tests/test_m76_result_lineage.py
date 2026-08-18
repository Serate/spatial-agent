import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from result_contract import build_result_contract


COMPLEX_REQUEST = (
    "请对洪山区进行综合空间分析：查询行政区边界，统计DEM高程与坡度，"
    "分析土地利用分布，汇总道路和水体，并筛选坡度不超过20度、"
    "距离道路不超过1000米且排除水体的建设候选区域。"
)


class M76ResultLineageTests(unittest.TestCase):
    def test_console_renders_the_shared_lineage_index(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="lineageEvidence"', html)
        self.assertIn("const lineage=envelope.lineage||{}", html)
        self.assertIn("lineage.map_layers", html)
        self.assertIn("const degradationMatrix=envelope.degradation||{}", html)

    def test_result_contract_indexes_run_answer_trace_and_release_evidence(self):
        payload = AgentService().run(
            "查询洪山区行政区边界",
            backend="memory",
            export_artifact=True,
            export_geojson=True,
        )
        lineage = payload["result"]["lineage"]
        self.assertEqual(lineage["run_id"], payload["run_id"])
        self.assertTrue(lineage["answer"]["available"])
        self.assertTrue(lineage["trace"]["available"])
        self.assertTrue(lineage["artifact"]["available"])
        self.assertTrue(lineage["geojson"]["available"])
        self.assertEqual(lineage["geojson"]["status"], "no_geometry")
        self.assertEqual(lineage["release_evidence"]["scope"], "configured_data_volume")
        self.assertTrue(any(item["kind"] == "trace" for item in lineage["references"]))

    def test_lineage_does_not_expose_absolute_artifact_paths(self):
        payload = AgentService().run(
            "查询DEM栅格元数据",
            backend="memory",
            export_artifact=True,
        )
        lineage = payload["result"]["lineage"]
        self.assertNotIn("/", lineage["artifact"]["ref"])
        self.assertNotIn("\\", lineage["artifact"]["ref"])

    def test_result_contract_exposes_memory_backend_degradation_matrix(self):
        payload = AgentService().run(COMPLEX_REQUEST, backend="memory")

        degradation = payload["result"]["degradation"]
        codes = {item["code"] for item in degradation["items"]}
        messages = " ".join(item["message"] for item in degradation["items"])

        self.assertTrue(degradation["available"])
        self.assertEqual(degradation["status"], "degraded")
        self.assertIn("data_health_degraded", codes)
        self.assertIn("tool_result_error:composed-slope", codes)
        self.assertIn("tool_result_error:composed-buildability", codes)
        self.assertIn("in-memory backend has no DEM pixels", messages)
        self.assertIn("in-memory backend has no raster geometry", messages)

    def test_result_contract_marks_geometry_truncation_as_warning(self):
        contract = build_result_contract({
            "run_id": "truncated-run",
            "status": "COMPLETED",
            "answer": "已完成",
            "steps": [],
            "plan": {"output": {"type": "spatial_analysis_result"}},
            "_geometry_evidence": {
                "status": "truncated_geometry",
                "reason": "GeoJSON summary exceeds max_bytes",
                "feature_count": 100,
                "truncated": True,
                "sources": ["geojson"],
            },
        })

        degradation = contract["degradation"]
        codes = {item["code"] for item in degradation["items"]}

        self.assertEqual(degradation["status"], "warning")
        self.assertIn("geometry_truncated", codes)

    def test_result_contract_marks_analysis_ready_and_manifest_limits(self):
        contract = build_result_contract({
            "run_id": "analysis-ready-limit",
            "status": "COMPLETED",
            "answer": "已完成",
            "plan": {"output": {"type": "spatial_analysis_result"}},
            "steps": [
                {
                    "id": "dataset-health",
                    "tool": "get_dataset_health_report",
                    "status": "COMPLETED",
                    "result": {
                        "dataset": "all",
                        "status": "ready",
                        "data_readiness": "not_ready",
                        "analysis_ready": {
                            "status": "unavailable",
                            "source_binding": {"status": "degraded"},
                            "output_manifest": {"status": "degraded"},
                        },
                    },
                }
            ],
        })

        degradation = contract["degradation"]
        codes = {item["code"] for item in degradation["items"]}

        self.assertEqual(degradation["status"], "unavailable")
        self.assertIn("data_readiness_not_ready", codes)
        self.assertIn("analysis_ready_unavailable", codes)
        self.assertIn("source_binding_degraded", codes)
        self.assertIn("output_manifest_degraded", codes)

    def test_artifact_and_recovered_run_share_degradation_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(str(Path(directory) / "runs"))
            service = AgentService(artifact_store=store)
            payload = service.run(COMPLEX_REQUEST, backend="memory", export_artifact=True)
            artifact = json.loads(Path(payload["artifact_ref"]).read_text(encoding="utf-8"))
            recovered = AgentService(artifact_store=store).get_run(payload["run_id"])

        self.assertEqual(artifact["degradation"], payload["result"]["degradation"])
        self.assertEqual(artifact["result"]["degradation"], payload["result"]["degradation"])
        self.assertEqual(recovered["result"]["degradation"], payload["result"]["degradation"])


if __name__ == "__main__":
    unittest.main()
