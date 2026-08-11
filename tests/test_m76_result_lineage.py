import unittest
from pathlib import Path

from agent.service import AgentService


class M76ResultLineageTests(unittest.TestCase):
    def test_console_renders_the_shared_lineage_index(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="lineageEvidence"', html)
        self.assertIn("const lineage=envelope.lineage||{}", html)
        self.assertIn("lineage.map_layers", html)

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


if __name__ == "__main__":
    unittest.main()
