import unittest
from pathlib import Path


class M30ConsoleResultSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

    def test_console_uses_one_dynamic_result_surface(self):
        for marker in (
            'class="panel result-panel generic-result"',
            'id="genericResult"',
            "function genericResult(data)",
            "function resultViewPanels(data)",
            "function renderGenericView(viewId,view,spec={},data={})",
            "Object.entries(panels).filter(([id])=>id!=='map')",
            "function updateResultPanels(data)",
            "function resetResultWorkspace()",
        ):
            self.assertIn(marker, self.html)

        for legacy_id in (
            'id="rasterStats"',
            'id="healthStats"',
            'id="overviewStats"',
            'id="compositeStats"',
            'id="buildabilityStats"',
        ):
            self.assertNotIn(legacy_id, self.html)

    def test_map_remains_an_optional_renderer_plugin(self):
        for marker in (
            "spatialOverviewMapPreview",
            "leafletMapPreview",
            "L.control.layers",
            "行政区边界",
            "道路",
            "水体",
        ):
            self.assertIn(marker, self.html)

    def test_step_summary_covers_failure_and_category_results(self):
        self.assertIn("业务错误：", self.html)
        self.assertIn("类别 ", self.html)
        self.assertIn("step-status '+String(s.status||'').toLowerCase()", self.html)


if __name__ == "__main__":
    unittest.main()
