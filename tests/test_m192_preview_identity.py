"""M192-B: preview and execution share one plan identity boundary."""

from __future__ import annotations

import unittest

from agent.service import AgentService
from domains.text.domain import TextDomainPack
from agent.workflow_templates import workflow_request_hint


class M192PreviewIdentityTests(unittest.TestCase):
    def test_custom_workflow_facts_reach_planner_hint_without_sensitive_values(self):
        hint = workflow_request_hint(
            "请处理这段内容",
            {
                "template_id": "text_summary",
                "constraints": {
                    "source": "用户输入文本",
                    "api_key": "must-not-be-forwarded",
                },
            },
        )

        self.assertIn("source=用户输入文本", hint)
        self.assertNotIn("must-not-be-forwarded", hint)

    def test_preview_fingerprint_accepts_same_plan_and_rejects_drift(self):
        service = AgentService(domain_pack=TextDomainPack())
        try:
            request = "请总结这段文本"
            preview = service.preview(
                request,
                session_id="m192-preview",
                planner="rule",
                backend="memory",
            )
            fingerprint = preview["plan_identity"]["fingerprint"]
            completed = service.run(
                request,
                session_id="m192-preview-same",
                planner="rule",
                backend="memory",
                preview_fingerprint=fingerprint,
            )
            rejected = service.run(
                request,
                session_id="m192-preview-drift",
                planner="rule",
                backend="memory",
                preview_fingerprint="sha256:preview-drift",
            )
        finally:
            service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertTrue(completed["plan_evidence"]["plan_fingerprint_match"])
        self.assertEqual(rejected["status"], "FAILED")
        self.assertFalse(rejected["plan_evidence"]["plan_fingerprint_match"])
        self.assertEqual(rejected["steps"], [])


if __name__ == "__main__":
    unittest.main()
