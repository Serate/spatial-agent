import unittest
from pathlib import Path


class M30ConsoleResultSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

    def test_console_has_structured_result_panels(self):
        for marker in (
            "栅格统计概览",
            "综合空间分析",
            "运行血缘",
            "建设适宜性筛选",
            "function stepResult(result)",
            "function buildabilityStats(data)",
            "请将空间后端切换为“本地 GIS”",
            "function rasterStats(data)",
            "geometry_source==='raster-buildability-screening'",
            "空间预览加载失败：",
            "行政区边界",
            "map-legend",
            "leafletMapPreview",
            "L.control.layers",
            "交互式空间预览",
        ):
            self.assertIn(marker, self.html)

    def test_step_summary_covers_failure_and_category_results(self):
        self.assertIn("业务错误：", self.html)
        self.assertIn("类别 ", self.html)
        self.assertIn("step-status '+String(s.status||'').toLowerCase()", self.html)


if __name__ == "__main__":
    unittest.main()
