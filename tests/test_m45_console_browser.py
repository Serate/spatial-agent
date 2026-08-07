import unittest
from pathlib import Path


class M45ConsoleBrowserSmokeTests(unittest.TestCase):
    def test_session_smoke_script_covers_switch_and_result_isolation(self):
        script = (Path(__file__).parents[1] / "scripts" / "console_session_smoke.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("restoreSession", script)
        self.assertIn("createRun", script)
        self.assertIn("conversation user history was not restored", script)
        self.assertIn("conversation assistant history was not restored", script)
        self.assertIn("result from another conversation leaked", script)

    def test_map_smoke_selects_local_gis_and_awaits_the_console_run(self):
        script = (Path(__file__).parents[1] / "scripts" / "console_map_smoke.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("$('backend').value='local'", script)
        self.assertIn("awaitPromise: true", script)
        self.assertIn("exceptionDetails", script)
        self.assertIn("地图要素点击没有生成可用的空间上下文", script)

    def test_clear_chat_resets_the_complete_workspace(self):
        source = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        clear_body = source.split("function clearChat()", 1)[1].split("\n", 1)[0]
        self.assertIn("resetConversationView()", clear_body)
        self.assertIn("resetMapSelection()", source)

    def test_threshold_comparison_can_reuse_selected_map_context(self):
        source = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("spatial_context:selectedSpatialContext", source)
        self.assertIn("spatial_context:selectedSpatialContext", source.split("async function compareBuildability", 1)[1])

    def test_clear_smoke_script_covers_workspace_reset(self):
        script = (Path(__file__).parents[1] / "scripts" / "console_clear_smoke.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("await clearChat()", script)
        self.assertIn("清空对话没有清除当前工作区", script)
        self.assertIn("awaitPromise: true", script)

    def test_console_exposes_distinct_clear_and_delete_session_actions(self):
        source = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="deleteSession"', source)
        self.assertIn("/clear", source)
        self.assertIn("deleteSession", source)

    def test_console_exposes_multi_region_comparison(self):
        source = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="compareRegions"', source)
        self.assertIn("/region-comparisons", source)
        self.assertIn("compareRegions()", source)


if __name__ == "__main__":
    unittest.main()
