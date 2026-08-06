import unittest
from pathlib import Path


class M30ConsoleResultSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

    def test_console_has_structured_result_panels(self):
        for marker in (
            "栅格统计概览",
            "综合空间分析",
            "运行血缘",
            "function stepResult(result)",
            "function rasterStats(data)",
        ):
            self.assertIn(marker, self.html)

    def test_step_summary_covers_failure_and_category_results(self):
        self.assertIn("业务错误：", self.html)
        self.assertIn("类别 ", self.html)
        self.assertIn("step-status '+String(s.status||'').toLowerCase()", self.html)


if __name__ == "__main__":
    unittest.main()
