"""M79.2 console contract: the result zone converges on result_type-driven
panels, replaces misleading "waiting" placeholders, and renders structured
error_category badges instead of raw strings.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M79ResultZoneContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    def test_error_category_badge_contract_exists(self):
        for marker in (
            "errorCategoryLabels",
            "errorCategoryBadge",
            "errorCategoryBadge(errorCategory)",
            "data.error_category||(data.result||{}).error_category",
            ".error-category.provider",
            ".error-category.timeout",
            ".error-category.rejected",
            ".error-category.clarification",
        ):
            self.assertIn(marker, self.html)

    def test_error_category_labels_cover_the_service_taxonomy(self):
        for label in ("模型服务错误", "规划错误", "工具执行错误", "执行超时", "无效输入", "执行错误", "请求已拒绝", "需要澄清"):
            self.assertIn(label, self.html)

    def test_result_zone_panels_are_driven_by_backend_workspace_contract(self):
        for marker in (
            "workspacePanelSelectors",
            "setResultPanel('.result-panel', false)",
            "Backend workspace contract decides result-specific panels",
            "const workspace=envelope.workspace||{}",
            "Array.isArray(workspace.panels)?workspace.panels:[]",
            "Object.entries(workspacePanelSelectors)",
            "views.has(view)",
            "setResultPanel('.generic-result'",
        ):
            self.assertIn(marker, self.html)
        # Tool inference fallback must be gone: the backend result workspace
        # decides panels, while tool results only populate already-open panels.
        self.assertNotIn("registeredViews === undefined", self.html)
        self.assertNotIn("hasRasterResult", self.html)
        self.assertNotIn("hasCompositeResult", self.html)
        self.assertNotIn("hasHealthResult", self.html)
        self.assertNotIn("hasBuildabilityResult", self.html)
        self.assertNotIn("resultViewRegistry", self.html)

    def test_panel_contents_prefer_backend_view_model(self):
        for marker in (
            "function resultViewPanels(data)",
            "const view=resultViewPanels(data).raster",
            "const view=resultViewPanels(data).overview",
            "const view=resultViewPanels(data).health",
            "const view=resultViewPanels(data).composite",
            "const view=resultViewPanels(data).buildability",
            "const view=resultViewPanels(data).vector",
            "renderMetricGrid(view.metrics||[])",
            "view.kind==='raster_metadata'",
            "view.kind==='spatial_overview'",
            "view.kind==='dataset_health'",
            "view.kind==='spatial_composite'",
            "view.kind==='buildability_screening'",
            "view.kind==='vector_query'||view.kind==='zonal_vector_summary'||view.kind==='spatial_relation'",
            "renderViewTable(view.table)",
        ):
            self.assertIn(marker, self.html)
        self.assertNotIn("const steps=data.steps||[]; const datasets=new Set()", self.html)
        self.assertNotIn("map(s=>s.result||{}).find(x=>x.statistics||x.metadata)", self.html)
        self.assertNotIn("const find=tool=>((data.steps||[]).find(s=>s.tool===tool)||{}).result||{}", self.html)
        self.assertNotIn("find(s=>s.tool==='get_dataset_health_report')", self.html)
        self.assertNotIn("find(s=>s.tool==='get_zonal_buildability_analysis')", self.html)

    def test_backend_workspace_contract_covers_all_catalog_result_types(self):
        import json
        import sys

        sys.path.insert(0, str(ROOT))
        from agent.capability_catalog import capability_catalog
        from result_contract import build_result_contract

        catalog_types = set()
        for capability in capability_catalog()["capabilities"]:
            catalog_types.update(capability.get("result_types", []))
        for result_type in sorted(catalog_types):
            payload = build_result_contract({
                "run_id": "workspace-" + result_type,
                "status": "COMPLETED",
                "result_type": result_type,
                "answer": "已完成",
                "steps": [],
            })
            self.assertTrue(payload["workspace"]["registered_type"], result_type)

    def test_no_misleading_waiting_placeholders_remain(self):
        # Terminal results must not claim they are still "waiting".
        for stale in (
            "等待统计分析",
            "等待数据健康检查",
            "等待建设候选筛选",
            "等待高程、坡度和土地利用联合分析",
        ):
            self.assertNotIn(stale, self.html)
        for replacement in (
            "本次结果未包含栅格统计面板所需数据",
            "本次结果未包含数据健康检查面板所需数据",
            "本次结果未包含建设候选筛选面板所需数据",
            "本次结果未包含综合空间分析面板所需数据",
        ):
            self.assertIn(replacement, self.html)

    def test_compare_panels_start_with_actionable_hint(self):
        self.assertIn("设置坡度阈值后点击「对比」生成结果", self.html)
        self.assertIn("设置行政区与阈值后点击「多区域对比」生成结果", self.html)


if __name__ == "__main__":
    unittest.main()
