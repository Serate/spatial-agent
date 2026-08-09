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
            "阈值结果对比",
            "function compareBuildability()",
            "candidate_pixel_count",
            "geometry_source==='raster-buildability-screening'",
            "空间预览加载失败：",
            "行政区边界",
            "map-legend",
            "leafletMapPreview",
            "L.control.layers",
            "交互式空间预览",
            "if(!boundaryLayer.getLayers().length&&!candidateLayer.getLayers().length)",
            "catch(error) { destroyMap(); return false; }",
            ".map > svg",
            "leaflet-overlay-pane svg",
            "fillColor:'#e09a5b'",
            "fillColor:'#87c7d1'",
            "OpenStreetMap",
            "纯矢量",
            "历史任务",
            "function loadHistory()",
            "/runs?limit=20",
            "runtimeMetrics",
            "fetch('/metrics')",
            "function decisionMode(data)",
            "通用回答 · 未调用空间工具",
            "空间计划 · 已执行",
            "function updateResultPanels(data)",
            "function resetResultWorkspace()",
            "resultEmpty",
            "result-panel",
            "数据健康检查",
            "dataset_health_result",
            "spatial_overview_result",
            "spatialOverviewMapPreview",
            "function healthStats(data)",
            "DEM/土地利用覆盖关系",
            "capabilityStatus",
            "function renderCapabilities(data)",
            "function geometryEvidence(data)",
            "空间证据：",
        ):
            self.assertIn(marker, self.html)

    def test_step_summary_covers_failure_and_category_results(self):
        self.assertIn("业务错误：", self.html)
        self.assertIn("类别 ", self.html)
        self.assertIn("step-status '+String(s.status||'').toLowerCase()", self.html)


if __name__ == "__main__":
    unittest.main()
