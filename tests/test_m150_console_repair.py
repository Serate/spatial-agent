"""M150-C: offline Console decision-evidence seam.

The test intentionally stays on the static/Node boundary.  It does not import
the Runtime, start an HTTP server, require Docker/GIS data, or call a model.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.console_source import read_console_source


ROOT = Path(__file__).resolve().parents[1]


class M150ConsoleRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = read_console_source(ROOT)
        cls.module = (ROOT / "web" / "src" / "console_decision_evidence.js").read_text(
            encoding="utf-8"
        )
        cls.smoke = ROOT / "scripts" / "console_decision_evidence_smoke.js"

    def test_console_loads_decision_evidence_seam(self) -> None:
        self.assertIn(
            '<script src="./console_decision_evidence.js"></script>', self.html
        )
        for marker in (
            'id="decisionEvidence"',
            "normalizeDecisionEvidence",
            "renderDecisionEvidence",
            "ConsoleDecisionEvidence.normalize",
            "data-repair-state",
            "仅显示结构化、脱敏状态",
        ):
            self.assertIn(marker, self.html + self.module)

    def test_seam_has_bounded_versions_and_no_raw_error_projection(self) -> None:
        for marker in (
            "spatial-agent.replanning.v1",
            "spatial-agent.repair-evaluation.v1",
            "spatial-agent.clarification.v1",
            "spatial-agent.failure.v1",
            "state: \"missing\"",
            "state: \"unavailable\"",
            "replanned_step_ids",
        ):
            self.assertIn(marker, self.module)
        # The renderer is required to use only projected fields.  These raw
        # fields may be present in input fixtures, but must not be interpolated
        # by the decision-evidence HTML functions.
        render_source = self.module.split("function renderRepair", 1)[1]
        self.assertNotIn("repair.error", render_source)
        self.assertNotIn("data.error", render_source)
        self.assertNotIn("result.error", render_source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_node_smoke_is_offline_and_passes(self) -> None:
        source = self.smoke.read_text(encoding="utf-8")
        self.assertNotIn("WebSocket", source)
        self.assertNotIn("fetch(", source)
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
            msg=(completed.stdout + "\n" + completed.stderr)[-5000:],
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["states"]["unknown"], "unavailable")
        self.assertEqual(payload["states"]["missing"], "missing")


if __name__ == "__main__":
    unittest.main()
