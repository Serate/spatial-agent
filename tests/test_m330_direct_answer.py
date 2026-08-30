"""Compact M330-A contracts for domain-neutral direct answers."""

from __future__ import annotations

import unittest

from agent.answer_generation import LLMAnswerGenerator
from agent.general_runtime import GeneralAnswerComposer
from agent.models import AgentRunResult, RunStatus, TaskPlan
from agent.request_mode import derive_request_mode
from agent.runtime_factory import build_general_runtime


SCENARIOS = (
    "请解释什么是反馈回路，并举一个日常例子。",
    "比较番茄工作法和时间分块法，并给出选择建议。",
    "把“目标、约束、执行、复盘”总结成三条工作建议。",
    "写一段 100 字以内的城市绿色空间项目介绍。",
    "每周工作 5 天、每天 8 小时，连续 4 周是多少小时？",
)


class _AnswerClient:
    def __init__(self, answer: str):
        self.answer = answer
        self.messages = []

    def complete_json(self, messages, schema):
        self.messages = messages
        self.schema = schema
        return {"answer": self.answer}

    def metrics(self):
        return {"execution_mode": "live_model", "status": "success"}


def _direct_result(request: str) -> AgentRunResult:
    return AgentRunResult(
        run_id="m330-direct",
        status=RunStatus.COMPLETED,
        request=request,
        plan=TaskPlan(
            goal=request,
            steps=[],
            output={"type": "direct_answer"},
        ),
    )


class M330DirectAnswerTests(unittest.TestCase):
    def test_open_non_data_requests_use_one_domain_neutral_answer_mode(self):
        runtime = build_general_runtime("rule", "memory")
        for request in SCENARIOS:
            with self.subTest(request=request):
                result = runtime.run(request)
                self.assertEqual(result.status, RunStatus.COMPLETED)
                self.assertEqual(result.domain_id, "general")
                self.assertEqual(result.plan.output["type"], "direct_answer")
                self.assertEqual(result.steps, [])
                self.assertEqual(result.request_mode["mode"], "answer")
                self.assertEqual(result.request_mode["tool_count"], 0)
                self.assertFalse(result.request_mode["execution_started"])

    def test_model_answer_can_use_request_when_fact_packet_is_empty(self):
        request = SCENARIOS[0]
        client = _AnswerClient("反馈回路是结果反过来影响后续行为的循环过程。")
        generated = LLMAnswerGenerator(client).generate(_direct_result(request))

        self.assertEqual(generated.answer, client.answer)
        self.assertEqual(generated.evidence["mode"], "live_model")
        prompt = client.messages[0]["content"]
        self.assertIn("不依赖外部数据", prompt)
        self.assertNotIn("memory://", client.messages[1]["content"])

    def test_unavailable_model_fallback_is_not_misreported_as_empty_result(self):
        result = _direct_result(SCENARIOS[1])
        answer = GeneralAnswerComposer().compose(result)

        self.assertIn("离线", answer)
        self.assertIn("真实模型", answer)
        self.assertNotIn("没有可展示的结果", answer)

    def test_request_mode_remains_answer_for_direct_result_without_tools(self):
        result = _direct_result(SCENARIOS[2])
        mode = derive_request_mode(result)
        self.assertEqual(mode["mode"], "answer")
        self.assertEqual(mode["reason_code"], "direct_answer")
        self.assertFalse(mode["execution_started"])


if __name__ == "__main__":
    unittest.main()
