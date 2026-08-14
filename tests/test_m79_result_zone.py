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

    def test_result_zone_panels_are_driven_by_result_type_registry(self):
        for marker in (
            "resultViewRegistry",
            "setResultPanel('.result-panel', false)",
            "Pure result-type driven panel selection",
            "registeredViews || []",
            "views.has('overview')",
            "views.has('buildability')",
            "setResultPanel('.map-result'",
            "setResultPanel('.generic-result'",
        ):
            self.assertIn(marker, self.html)
        # Tool inference fallback must be gone: no unregistered-type tool sniffing.
        self.assertNotIn("registeredViews === undefined", self.html)
        self.assertNotIn("hasRasterTool) views.add('raster'", self.html)

    def test_result_registry_covers_all_catalog_result_types(self):
        # Every catalog result_type must have an explicit registry entry so no
        # result silently falls back to tool inference.
        import json
        import sys

        sys.path.insert(0, str(ROOT))
        from agent.capability_catalog import capability_catalog

        catalog_types = set()
        for capability in capability_catalog()["capabilities"]:
            catalog_types.update(capability.get("result_types", []))
        registry_start = self.html.index("const resultViewRegistry = {")
        registry_end = self.html.index("};", registry_start)
        registry_block = self.html[registry_start:registry_end]
        for result_type in sorted(catalog_types):
            self.assertIn(result_type + ":", registry_block)

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
