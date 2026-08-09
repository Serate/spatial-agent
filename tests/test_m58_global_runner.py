import unittest
from pathlib import Path

from evaluation.global_runner import run_global_cases
from evaluation.runner import load_cases


class M58GlobalRunnerTests(unittest.TestCase):
    def test_global_runner_executes_supported_cases_and_marks_optional_cases(self):
        root = Path(__file__).parents[1]
        report = run_global_cases(
            load_cases(str(root / "evaluation" / "cases" / "global-acceptance.json")),
            backend="memory",
        )
        self.assertEqual(report["total"], 10)
        self.assertGreaterEqual(report["executed"], 7)
        self.assertGreaterEqual(report["skipped"], 2)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["evaluation_context"]["environment"], "memory")
        self.assertTrue(any(item.get("status") == "SKIPPED" for item in report["results"]))


if __name__ == "__main__":
    unittest.main()
