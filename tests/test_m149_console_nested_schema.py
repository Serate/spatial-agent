"""M149 Console nested workspace/views/view/panel contract.

The test is deliberately independent from the backend schema implementation:
it checks that the browser loads a frontend compatibility seam and that the
same seam is executable in Node without HTTP, Docker, GIS, or a live model.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.console_source import read_console_source


ROOT = Path(__file__).resolve().parents[1]


class M149ConsoleNestedSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read_console_source(ROOT)
        cls.module = (ROOT / "web" / "src" / "console_nested_schema.js").read_text(
            encoding="utf-8"
        )
        cls.smoke = ROOT / "scripts" / "console_nested_schema_smoke.js"

    def test_console_loads_shared_frontend_nested_schema_seam(self):
        self.assertIn(
            '<script src="./console_nested_schema.js"></script>', self.html
        )
        for marker in (
            "normalizeConsoleResult",
            "ConsoleNestedSchema.normalize",
            "const contract=normalizeConsoleResult(data)",
            "function resultViewPanels(data)",
        ):
            self.assertIn(marker, self.html)
        self.assertIn("有界不可用空态", self.module)

    def test_nested_module_rejects_future_versions_and_keeps_legacy(self):
        for marker in (
            "spatial-agent.result-envelope.v1",
            "spatial-agent.workspace.v1",
            "spatial-agent.views.v1",
            "spatial-agent.view.v1",
            "unknown_schema_version",
            "fallbackPanel",
            "artifact_available",
        ):
            self.assertIn(marker, self.module)
        self.assertIn("console_nested_schema_smoke.js", str(self.smoke))

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_node_nested_schema_smoke(self):
        completed = subprocess.run(
            ["node", str(self.smoke)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=(completed.stdout + "\n" + completed.stderr)[-4000:],
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["fallback_kind"], "unavailable")


if __name__ == "__main__":
    unittest.main()
