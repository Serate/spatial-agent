import unittest
from pathlib import Path


class M45ConsoleBrowserSmokeTests(unittest.TestCase):
    def test_session_smoke_script_covers_switch_and_result_isolation(self):
        script = (Path(__file__).parents[1] / "scripts" / "console_session_smoke.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("restoreSession", script)
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


if __name__ == "__main__":
    unittest.main()
