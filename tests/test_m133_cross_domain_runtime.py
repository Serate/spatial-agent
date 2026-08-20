import unittest
from unittest.mock import patch

from agent.runtime_factory import build_runtime
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.text.runtime import build_text_runtime


class RecordedTextPlannerClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, messages, schema):
        self.calls.append((messages, schema))
        return {
            "goal": "summarize supplied text",
            "steps": [
                {
                    "id": "summary",
                    "tool": "summarize_text",
                    "args": {"text": "跨领域 Runtime 需要统一工具入口。"},
                    "depends_on": [],
                }
            ],
            "output": {
                "type": "text_summary_result",
                "title": "文本摘要",
                "summary": True,
            },
        }


class M133CrossDomainRuntimeTests(unittest.TestCase):
    def test_generic_factory_uses_text_domain_tool_provider(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)

        capabilities = runtime.runtime_capabilities(max_files=1)
        result = runtime.run("请摘要这段文本")

        self.assertEqual(capabilities["domain_id"], "text")
        self.assertEqual(capabilities["tool_provider"]["id"], "text-native")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[0].tool, "summarize_text")
        self.assertEqual(result.plan.output["type"], "text_summary_result")

    def test_text_runtime_factory_honors_openai_planner_selection(self):
        client = RecordedTextPlannerClient()
        with patch("agent.runtime_factory.load_openai_config", return_value={}), patch(
            "agent.runtime_factory.OpenAIPlannerClient", return_value=client
        ):
            runtime = build_text_runtime("openai", "memory")
            result = runtime.run("请摘要这段文本")

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "text_summary_result")
        prompt = client.calls[0][0][0]["content"]
        self.assertIn("summarize_text", prompt)
        self.assertNotIn("洪山区", prompt)


if __name__ == "__main__":
    unittest.main()
