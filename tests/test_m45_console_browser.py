"""Small browser-facing Console contract; dynamic behavior stays in explicit smokes."""

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class M45ConsoleBrowserSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    def test_session_smoke_covers_switch_and_result_isolation(self):
        script = (ROOT / "scripts" / "console_session_smoke.js").read_text(
            encoding="utf-8"
        )
        for marker in (
            "restoreSession",
            "createRun",
            "conversation user history was not restored",
            "result from another conversation leaked",
        ):
            self.assertIn(marker, script)

    def test_clear_resets_shell_and_registered_adapters_once(self):
        clear_body = self.source.split("function clearChat()", 1)[1].split(
            "async function deleteConversation", 1
        )[0]
        reset_body = self.source.split("function resetResultWorkspace()", 1)[1].split(
            "function updateResultPanels", 1
        )[0]
        self.assertIn("resetConversationView()", clear_body)
        self.assertEqual(reset_body.count("rendererRegistry?.reset"), 1)
        self.assertNotIn("resetMapSelection", self.source)

    def test_map_context_is_owned_by_the_registered_adapter(self):
        self.assertIn("rendererRegistry?.context()||{}", self.source)
        self.assertIn("Object.assign({request,session_id", self.source)
        self.assertNotIn("selectedSpatialContext", self.source)
        self.assertNotIn("spatial_context:selectedSpatialContext", self.source)

    def test_async_cancel_and_session_actions_remain_available(self):
        for marker in (
            'id="deleteSession"',
            'id="clearAllSessions"',
            'id="cancelRun"',
            "/runs/async",
            "/cancel",
            "setCancelState(true)",
        ):
            self.assertIn(marker, self.source)

    def test_session_actions_cover_unbound_auto_and_clear_all(self):
        script = (ROOT / "scripts" / "console_session_actions_smoke.js").read_text(
            encoding="utf-8"
        )
        for marker in (
            "自动领域未绑定时新建对话按钮被禁用",
            "clearAllSessions",
            "includePersisted:false",
            "清空全部对话后消息区未重置",
            "heroRect.height",
            "chatRect.height",
        ):
            self.assertIn(marker, script)
        self.assertIn("localDraftSessionIds", self.source)
        self.assertIn("$('newSession').disabled=false", self.source)

    def test_new_session_button_click_uses_default_arguments(self):
        script = (ROOT / "scripts" / "console_new_session_click_smoke.js").read_text(
            encoding="utf-8"
        )
        for marker in (
            "$('newSession').click()",
            "下拉选项或当前选择未变化",
            "nativeFetch('/domains/'",
        ):
            self.assertIn(marker, script)
        self.assertIn("$('newSession').addEventListener('click',()=>newSession())", self.source)
        self.assertIn("sessionCatalogGeneration", self.source)

    def test_console_defaults_are_live_gis_local(self):
        """The first-use browser configuration should be ready for live GIS checks."""
        planner_select = self.source.split('<select id="planner"', 1)[1].split(
            '</select>', 1
        )[0]
        backend_select = self.source.split('<select id="backend"', 1)[1].split(
            '</select>', 1
        )[0]
        self.assertIn('value="openai" selected', planner_select)
        self.assertIn('value="local" selected', backend_select)
        self.assertIn("const defaultDomain=available.has('gis')?'gis'", self.source)
        self.assertIn("$('domain').value=available.has(preferred)?preferred:defaultDomain", self.source)


if __name__ == "__main__":
    unittest.main()
