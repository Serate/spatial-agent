import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M11SmokeCheckTests(unittest.TestCase):
    def test_smoke_check_script_reports_ok(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "smoke_check.py")],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(all(check["ok"] for check in payload["checks"]))


if __name__ == "__main__":
    unittest.main()
