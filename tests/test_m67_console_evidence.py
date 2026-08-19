import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M67ConsoleEvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.acceptance = (ROOT / "docs" / "console-browser-acceptance.md").read_text(
            encoding="utf-8"
        )

    def test_result_evidence_view_is_dynamic_and_starts_hidden(self):
        self.assertEqual(self.html.count('class="panel result-panel evidence-result"'), 1)
        self.assertIn('id="evidenceSummary"', self.html)
        for element_id in (
            "geometryEvidenceDetail",
            "provenanceEvidence",
            "runtimeEvidence",
            "dataEvidence",
            "degradationEvidence",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn("setResultPanel('.evidence-result', hasRun)", self.html)
        self.assertIn("setResultPanel('.result-panel', false)", self.html)

    def test_geometry_contract_uses_result_geometry_without_inventing_drawability(self):
        for marker in (
            "envelope.geometry||data.geometry_evidence",
            "geometryStatus=geometry.status||'unknown'",
            "real_geometry",
            "boundary_geometry",
            "no_geometry",
            "truncated_geometry",
            "geometry.available?'是':'否'",
            "geometry.feature_count",
            "geometry.sources",
            "geometry.crs",
            "geometry.geojson_ref||data.geojson_ref",
            "const view=resultViewPanels(data).raster",
            "const view=resultViewPanels(data).health",
            "const view=resultViewPanels(data).composite",
        ):
            self.assertIn(marker, self.html)

    def test_runtime_data_provenance_and_degradation_are_explicit(self):
        for marker in (
            "/capabilities/runtime?max_files=3",
            "runtime_evidence",
            "data_evidence",
            "data.provenance",
            "p.execution_policy",
            "provenanceSteps",
            "NEEDS_CLARIFICATION",
            "部分可用",
            "不可用",
            "不能据此推断数据已完成核验",
            "降级与限制",
        ):
            self.assertIn(marker, self.html)

    def test_existing_run_interfaces_remain_in_the_console(self):
        for marker in (
            "'/runs'",
            "'/runs/async'",
            "'/capabilities/runtime?max_files=3'",
            "export_artifact:true",
            "export_geojson:true",
            "function renderRun(data)",
        ):
            self.assertIn(marker, self.html)

    def test_acceptance_document_covers_evidence_and_degraded_states(self):
        for marker in (
            "M67 结果证据补充",
            "result.geometry",
            "runtime evidence",
            "data evidence",
            "provenance",
            "降级",
            "截断",
            "未知",
        ):
            self.assertIn(marker, self.acceptance)


if __name__ == "__main__":
    unittest.main()
