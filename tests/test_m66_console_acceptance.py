import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M66ConsoleAcceptanceContractTests(unittest.TestCase):
    def test_cdp_launcher_is_non_destructive_and_isolates_profile(self):
        source = (ROOT / "scripts" / "console_cdp_start.ps1").read_text(encoding="utf-8")
        self.assertIn("--user-data-dir=$profile", source)
        self.assertIn("Get-CdpVersion", source)
        self.assertIn("if ($existing)", source)
        self.assertNotIn("Stop-Process", source)
        self.assertIn("--remote-debugging-port=$Port", source)

    def test_overview_smoke_checks_result_panel_and_all_vector_layers(self):
        source = (ROOT / "scripts" / "console_overview_smoke.js").read_text(encoding="utf-8")
        for marker in (
            "spatial_overview_result",
            ".overview-result.is-visible",
            "工具步骤",
            "数据来源",
            "空间要素",
            "行政区边界",
            "道路",
            "水体",
            "#087f8c",
            "#d97706",
            "#2563eb",
            "scripts/console_cdp_start.ps1",
        ):
            self.assertIn(marker, source)

    def test_existing_browser_smokes_keep_cdp_and_console_configuration_documented(self):
        for name in (
            "console_health_smoke.js",
            "console_session_smoke.js",
            "console_clear_smoke.js",
            "console_map_smoke.js",
        ):
            source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("process.env.CDP_URL", source)


if __name__ == "__main__":
    unittest.main()
