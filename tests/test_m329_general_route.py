"""Compact M329 contract tests for the domain-neutral request mode."""

import unittest

from agent.application.http import HTTPApplication
from agent.models import AgentRunResult, RunStatus, StepRun
from agent.persistence.sqlite_store import _result_from_dict
from agent.request_mode import (
    REQUEST_MODE_SCHEMA_VERSION,
    derive_request_mode,
    normalize_request_mode,
)
from agent.run_events import new_run_event
from agent.service import AgentService


class M329RequestModeTests(unittest.TestCase):
    def test_normalize_request_mode_is_bounded_and_fail_safe(self):
        value = normalize_request_mode(
            {
                "mode": "not-a-mode",
                "reason_code": "x" * 200,
                "tool_count": 9999,
                "execution_started": "yes",
            }
        )
        self.assertEqual(value["schema_version"], REQUEST_MODE_SCHEMA_VERSION)
        self.assertEqual(value["mode"], "answer")
        self.assertEqual(len(value["reason_code"]), 64)
        self.assertEqual(value["tool_count"], 128)
        self.assertTrue(value["execution_started"])

    def test_derive_direct_answer_and_clarification(self):
        direct = AgentRunResult("direct", RunStatus.COMPLETED, "解释一下地图投影")
        self.assertEqual(derive_request_mode(direct)["mode"], "answer")

        clarify = AgentRunResult("clarify", RunStatus.NEEDS_CLARIFICATION, "查询数据")
        mode = derive_request_mode(clarify)
        self.assertEqual(mode["mode"], "clarify")
        self.assertEqual(mode["reason_code"], "clarification_required")

    def test_derive_mixed_answer_and_expose_execution_record(self):
        result = AgentRunResult("mixed", RunStatus.COMPLETED, "查询并解释")
        result.steps = [
            StepRun("step-1", "lookup", {}, status="COMPLETED"),
        ]
        result.answer = "已查询并完成说明。"
        result.request_mode = derive_request_mode(result)
        payload = result.to_dict()
        self.assertEqual(payload["request_mode"]["mode"], "mixed")
        self.assertEqual(payload["execution_record"]["request_mode"], "mixed")

    def test_sqlite_restore_and_terminal_event_keep_mode_projection(self):
        result = AgentRunResult("restore", RunStatus.COMPLETED, "回答问题")
        result.request_mode = derive_request_mode(result)
        restored = _result_from_dict(result.to_dict())
        self.assertEqual(restored.to_dict()["request_mode"], result.to_dict()["request_mode"])

        event = new_run_event(
            run_id="restore",
            phase="evidence",
            kind="run_completed",
            status="COMPLETED",
            message="分析已完成",
            data={
                "request_mode": "answer",
                "request_mode_reason": "direct_answer",
                "tool_count": 0,
                "execution_started": False,
            },
            terminal=True,
        )
        self.assertEqual(event["data"]["request_mode"], "answer")
        self.assertFalse(event["data"]["execution_started"])

    def test_general_service_is_domain_neutral_at_product_boundary(self):
        service = AgentService(general=True)
        try:
            runtime = service._runtime("rule", "memory")
            self.assertEqual(runtime.domain_id, "general")
            context = service._submission_runtime_context("rule", "memory")
            self.assertEqual(context["domain_id"], "general")
            response = HTTPApplication(
                service,
                use_product_defaults=True,
            ).execute(
                "run",
                {
                    "request": "请解释什么是数据可视化",
                    "session_id": "m329-general-product-boundary",
                    "planner": "rule",
                    "backend": "memory",
                },
            )
            self.assertEqual(response["domain_id"], "general")
            self.assertEqual(response["status"], "COMPLETED")
        finally:
            service.close()


if __name__ == "__main__":
    unittest.main()
