"""Compact contract for the registry-driven Console result zone."""

from pathlib import Path

from tests.console_source import read_console_source
import unittest


ROOT = Path(__file__).parents[1]


class M79ResultZoneContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read_console_source(ROOT)
        cls.registry = (ROOT / "web" / "src" / "console_renderer_registry.js").read_text(
            encoding="utf-8"
        )

    def test_error_category_badges_keep_the_service_taxonomy(self):
        for marker in (
            "errorCategoryLabels",
            "errorCategoryBadge(errorCategory)",
            ".error-category.provider",
            ".error-category.timeout",
            ".error-category.clarification",
        ):
            self.assertIn(marker, self.html)

    def test_workspace_views_are_dispatched_through_one_registry_seam(self):
        for marker in (
            "workspace.view_specs||[]",
            "workspace.panels||[]",
            "rendererRegistry.renderWorkspace",
            "resultViewPanels(safeData)",
        ):
            self.assertIn(marker, self.html)
        for marker in (
            "const requestedRenderer",
            "adapters.get(requestedRenderer) || genericAdapter",
            "unknown_renderers",
            "failures: failures.slice(0, 8)",
        ):
            self.assertIn(marker, self.registry)

    def test_shell_has_no_result_type_or_fixed_action_dispatch_table(self):
        for stale in (
            "hasRasterResult",
            "hasCompositeResult",
            "hasBuildabilityResult",
            "renderComparisonPayload",
            "gis.buildability_threshold_comparison",
            "gis.buildability_region_comparison",
            "gis.constrained_buildability_comparison",
        ):
            self.assertNotIn(stale, self.html)


if __name__ == "__main__":
    unittest.main()
