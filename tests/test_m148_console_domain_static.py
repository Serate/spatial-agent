"""Compact static contract for the domain-neutral Console plugin seam."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class M148ConsoleDomainStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.registry = (ROOT / "web" / "console_renderer_registry.js").read_text(
            encoding="utf-8"
        )
        cls.action_host = (ROOT / "web" / "console_action_host.js").read_text(
            encoding="utf-8"
        )
        cls.gis_plugin = (ROOT / "web" / "console_gis_plugin.js").read_text(
            encoding="utf-8"
        )

    def test_shell_uses_registry_and_schema_driven_action_interfaces(self):
        for asset in (
            "console_renderer_registry.js",
            "console_action_host.js",
            "console_gis_plugin.js",
        ):
            self.assertIn(asset, self.shell)
        self.assertIn("rendererRegistry.renderWorkspace", self.shell)
        self.assertIn("rendererRegistry?.context()||{}", self.shell)
        self.assertIn("window.ConsoleActionHost.mount", self.shell)
        self.assertIn("catalog:actionCatalog", self.shell)

    def test_domain_implementation_is_absent_from_shell(self):
        for legacy_marker in (
            "selectedSpatialContext",
            "setDomainControlState",
            "data-domain-control",
            "gis.buildability_threshold_comparison",
            "gis.buildability_region_comparison",
            "gis.constrained_buildability_comparison",
            "spatialOverviewMapPreview",
        ):
            self.assertNotIn(legacy_marker, self.shell)
        self.assertIn("createMapAdapter", self.gis_plugin)
        self.assertIn('surface: "visual"', self.gis_plugin)
        self.assertIn("const registry = Object.freeze({register, renderWorkspace, reset, context})", self.registry)
        self.assertIn("return Object.freeze({SCHEMA_VERSION, mount, collectPayload})", self.action_host)


if __name__ == "__main__":
    unittest.main()
