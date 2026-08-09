import unittest
from pathlib import Path

from agent.service import AgentService
from evaluation.runner import run_cases
from run_demo import build_runtime


class M46ResultContractTests(unittest.TestCase):
    def test_console_consumes_result_envelope_before_legacy_fields(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("const envelope = data.result || {}", html)
        self.assertIn("envelope.geometry?.available", html)
        self.assertIn("const payload = data.result ||", html)

    def test_completed_run_returns_bounded_evidence_result_envelope(self):
        payload = AgentService().run("查询DEM栅格元数据", backend="memory")

        result = payload["result"]
        self.assertEqual(result["type"], "raster_metadata_result")
        self.assertEqual(result["title"], "栅格元数据")
        self.assertIn("文件数", result["summary"])
        self.assertEqual(result["data"]["evidence_steps"][0]["tool"], "get_raster_metadata")
        self.assertNotIn("metadata", result["data"]["evidence_steps"][0]["summary"])

    def test_geojson_reference_is_exposed_as_spatial_evidence(self):
        payload = AgentService().run(
            "查询洪山区行政区边界",
            backend="memory",
            export_geojson=True,
        )

        result = payload["result"]
        self.assertFalse(result["geometry"]["available"])
        self.assertEqual(result["geometry"]["status"], "no_geometry")
        self.assertEqual(result["references"][-1]["kind"], "geojson")
        self.assertTrue(result["geometry"]["geojson_ref"])

    def test_contract_does_not_include_raw_geometry(self):
        payload = AgentService().run("你好", backend="memory")

        serialized = str(payload["result"])
        self.assertNotIn("coordinates", serialized)
        self.assertNotIn("_candidate_geometry", serialized)

    def test_core_evaluation_checks_result_types_and_contract_integrity(self):
        cases = __import__("json").loads(
            (Path(__file__).parents[1] / "evaluation" / "cases" / "core-workflows.json").read_text(
                encoding="utf-8"
            )
        )
        report = run_cases(build_runtime("rule", "memory"), cases)

        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["result_type_match_rate"], 1.0)
        self.assertEqual(report["result_contract_valid_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
