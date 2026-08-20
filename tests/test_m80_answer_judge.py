import unittest

from evaluation.answer_judge import (
    _bound_score,
    _score_clarity,
    _score_completeness,
    _score_explanatory,
    answer_judge_report,
    heuristic_answer_judge,
    llm_answer_judge,
)
from evaluation.model_evaluation import evaluate_plan_quality


def evidence_steps(candidate=22800, valid=576040, ratio=0.0396):
    return [
        {
            "id": "screening",
            "tool": "get_zonal_buildability_analysis",
            "result": {
                "admin_name": "洪山区",
                "statistics": {
                    "candidate_pixel_count": candidate,
                    "valid_pixel_count": valid,
                    "candidate_ratio": ratio,
                },
            },
        }
    ]


GOOD_ANSWER = (
    "洪山区建设候选筛选完成：坡度不超过15度条件下，候选像元 22,800 个，"
    "占有效像元（576,040 个）的 3.96%。本结果仅用于演示筛选，不代表规划许可结论；"
    "数据来源为分析就绪派生层（EPSG:32649，30 米分辨率）。"
)


class M80AnswerJudgeUnitTests(unittest.TestCase):
    def test_good_answer_scores_high_on_all_dimensions(self):
        judge = heuristic_answer_judge(GOOD_ANSWER, evidence_steps(), "筛选洪山区坡度不超过15度的建设候选区域")
        self.assertTrue(judge["passed"])
        self.assertEqual(judge["mode"], "heuristic")
        for score in judge["scores"].values():
            self.assertGreaterEqual(score, 3)

    def test_empty_answer_scores_zero(self):
        judge = heuristic_answer_judge("", evidence_steps(), "筛选洪山区建设候选")
        self.assertFalse(judge["passed"])
        self.assertEqual(judge["scores"]["completeness"], 0)
        self.assertEqual(judge["scores"]["clarity"], 0)

    def test_groundedness_penalizes_contradicting_numbers(self):
        bad = "洪山区候选像元为 1,000,000,000 个。"
        judge = heuristic_answer_judge(bad, evidence_steps(candidate=22800), "筛选洪山区建设候选")
        self.assertLess(judge["scores"]["groundedness"], 3)

    def test_clarity_penalizes_garbled_text(self):
        garbled = "洪山区\uFFFD\uFFFD候选像元\ufffd\ufffd"
        self.assertLess(_score_clarity(garbled), 3)

    def test_completeness_uses_request_terms(self):
        self.assertGreaterEqual(
            _score_completeness(GOOD_ANSWER, "筛选洪山区坡度不超过15度的建设候选区域"), 3
        )
        self.assertEqual(_score_completeness("", "筛选洪山区建设候选"), 0)

    def test_explanatory_detects_disclaimer(self):
        with_disclaimer = GOOD_ANSWER
        without = "洪山区候选像元 22800 个。"
        self.assertGreater(_score_explanatory(with_disclaimer), _score_explanatory(without))

    def test_judge_report_uses_heuristic_by_default(self):
        report = answer_judge_report(GOOD_ANSWER, evidence_steps(), "筛选洪山区建设候选")
        self.assertEqual(report["mode"], "heuristic")

    def test_llm_judge_redacts_and_falls_back_on_failure(self):
        # Without an enabled flag and client, the LLM path falls back to heuristic.
        report = llm_answer_judge(GOOD_ANSWER, evidence_steps(), "筛选洪山区建设候选", client=object())
        self.assertEqual(report["mode"], "heuristic")
        self.assertTrue(report["passed"])

    def test_llm_judge_uses_recorded_client(self):
        class RecordedClient:
            def complete_json(self, messages, schema):
                return {
                    "scores": {
                        "completeness": 5,
                        "groundedness": 4,
                        "clarity": 5,
                        "explanatory": 4,
                    },
                    "passed": True,
                    "reason": "答案完整且与证据一致。",
                }

        import os
        os.environ["SPATIAL_AGENT_JUDGE_LLM"] = "1"
        try:
            report = llm_answer_judge(
                GOOD_ANSWER, evidence_steps(), "筛选洪山区建设候选", client=RecordedClient()
            )
            self.assertEqual(report["mode"], "llm")
            self.assertTrue(report["passed"])
            self.assertEqual(report["scores"]["completeness"], 5)
            self.assertEqual(report["reason"], "答案完整且与证据一致。")
        finally:
            os.environ.pop("SPATIAL_AGENT_JUDGE_LLM", None)

    def test_bound_score_clamps(self):
        self.assertEqual(_bound_score(9), 5)
        self.assertEqual(_bound_score(-2), 0)
        self.assertEqual(_bound_score("x"), 0)


class M80AnswerJudgeIntegrationTests(unittest.TestCase):
    def test_evaluate_plan_quality_includes_answer_judge_dimension(self):
        plan = {
            "goal": "筛选建设候选",
            "steps": [
                {"id": "s", "tool": "get_zonal_buildability_analysis", "args": {}}
            ],
            "output": {"type": "buildability_result"},
        }
        quality = evaluate_plan_quality(
            plan,
            expected_tools=["get_zonal_buildability_analysis"],
            expected_result_type="buildability_result",
            answer=GOOD_ANSWER,
        )
        self.assertIn("answer_judge", quality)
        self.assertTrue(quality["answer_judge"]["passed"])
        # Additive: the original structured semantics are unchanged.
        self.assertIn("chinese_answer", quality)
        self.assertIn("tool_coverage", quality)


if __name__ == "__main__":
    unittest.main()
