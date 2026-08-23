"""Compact Console result-surface contract."""

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class M30ConsoleResultSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.registry = (ROOT / "web" / "console_renderer_registry.js").read_text(
            encoding="utf-8"
        )
        cls.gis_plugin = (ROOT / "web" / "console_gis_plugin.js").read_text(
            encoding="utf-8"
        )

    def test_console_has_one_registry_driven_structured_surface(self):
        for marker in (
            'class="panel result-panel generic-result"',
            'id="genericResult"',
            "function genericResult(data)",
            "rendererRegistry.renderWorkspace",
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

    def test_optional_map_rendering_lives_in_the_gis_adapter(self):
        self.assertIn('["generic", "metrics", "table", "chart"]', self.registry)
        self.assertIn("function createMapAdapter", self.gis_plugin)
        self.assertIn("function renderGeoJSON", self.gis_plugin)
        self.assertIn("function renderSvg", self.gis_plugin)
        self.assertNotIn("function renderGeoJSON", self.html)

    def test_step_summary_is_bounded_and_domain_neutral(self):
        self.assertIn("Object.entries(result)", self.html)
        self.assertIn(".slice(0,4)", self.html)
        self.assertIn("业务错误：", self.html)
        for domain_field in ("candidate_pixel_count", "nodata_ratio", "category_count"):
            self.assertNotIn(domain_field, self.html)


if __name__ == "__main__":
    unittest.main()
