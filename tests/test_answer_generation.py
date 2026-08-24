import unittest

from agent.answer_generation import (
    AnswerGenerationResult,
    LLMAnswerGenerator,
    build_answer_context,
    fallback_answer_generation_evidence,
)
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.runtime_factory import build_runtime


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def complete_json(self, messages, schema):
        self.messages = messages
        self.schema = schema
        return self.payload

    def metrics(self):
        return {
            "provider": "test-provider",
            "model": "test-model",
            "wire_api": "chat_completions",
            "execution_mode": "live_model",
            "status": "success",
            "attempts": 1,
            "retries": 0,
            "latency_ms": 4.2,
            "usage": {"prompt_tokens": 20, "completion_tokens": 12, "total_tokens": 32},
        }


class _Generator:
    def generate(self, _result):
        return AnswerGenerationResult(
            "这是一段面向用户的自然语言总结。",
            {"available": True, "status": "success", "execution_mode": "live_model"},
        )


class AnswerGenerationTests(unittest.TestCase):
    def _result(self):
        return AgentRunResult(
            run_id="answer-generation",
            status=RunStatus.COMPLETED,
            request="请分析空间结果",
            plan=TaskPlan(
                "分析空间结果",
                [PlanStep("step", "get_raster_statistics", {})],
                {"type": "raster_statistics_result"},
            ),
            steps=[
                StepRun(
                    "step",
                    "get_raster_statistics",
                    {},
                    status="COMPLETED",
                    result={
                        "dataset": "dem",
                        "statistics": {"mean": 12.345678, "valid_pixel_count": 100},
                        "geometry": {"coordinates": [1, 2]},
                        "result_ref": "memory://private-result",
                    },
                )
            ],
        )

    def test_context_is_bounded_and_redacts_internal_fields(self):
        context = build_answer_context(self._result())
        encoded = str(context)
        self.assertLess(len(encoded), 12000)
        self.assertNotIn("memory://", encoded)
        self.assertNotIn("coordinates", encoded)
        self.assertIn("valid_pixel_count", encoded)

    def test_llm_answer_is_structured_and_metrics_are_allowlisted(self):
        client = _Client({"answer": "结论：数据已准备好，适合继续查看。"})
        generated = LLMAnswerGenerator(client).generate(self._result())
        self.assertIn("结论", generated.answer)
        self.assertEqual(generated.evidence["mode"], "live_model")
        self.assertEqual(generated.evidence["usage"]["total_tokens"], 32)
        self.assertNotIn("messages", generated.evidence)

    def test_fallback_evidence_overrides_provider_error_status(self):
        evidence = fallback_answer_generation_evidence(
            "answer_generation_failed",
            metrics={"status": "error", "execution_mode": "live_model"},
        )
        self.assertEqual(evidence["status"], "fallback")
        self.assertEqual(evidence["mode"], "template_fallback")
        self.assertFalse(evidence["available"])

    def test_runtime_uses_generator_but_keeps_composer_fallback_contract(self):
        runtime = build_runtime("rule", "memory", answer_generator=_Generator())
        result = runtime.run("查询DEM栅格元数据")
        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.answer, "这是一段面向用户的自然语言总结。")
        self.assertTrue(result.answer_generation_evidence["available"])

        from result_contract import build_result_contract

        contract = build_result_contract(result.to_dict())
        self.assertEqual(contract["answer_generation"]["mode"], "live_model")
        self.assertEqual(contract["summary"], result.answer)


if __name__ == "__main__":
    unittest.main()
