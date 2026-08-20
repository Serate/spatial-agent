import unittest
from unittest.mock import patch

from agent.llm_planner import LLMPlanner
from agent.planner_guidance import normalize_planner_guidance
from agent.runtime_factory import build_runtime
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK


class M129PlannerGuidanceTests(unittest.TestCase):
    def test_guidance_is_a_bounded_domain_contract(self):
        guidance = normalize_planner_guidance(GIS_DOMAIN_PACK.planner_guidance())

        self.assertEqual(guidance["schema_version"], "spatial-agent.planner-guidance.v1")
        self.assertEqual(guidance["domain_id"], "gis")
        self.assertIn("get_raster_metadata", guidance["tool_semantics"])
        self.assertIn("spatial_overview_result", guidance["result_types"])
        self.assertTrue(guidance["planning_rules"])

    def test_text_guidance_has_no_gis_vocabulary(self):
        guidance = normalize_planner_guidance(TEXT_DOMAIN_PACK.planner_guidance())
        rendered = str(guidance).lower()

        for forbidden in ("dem", "land_use", "roads", "water", "洪山区"):
            self.assertNotIn(forbidden.lower(), rendered)
        self.assertIn("summarize_text", rendered)
        self.assertIn("text_summary_result", rendered)

    def test_same_llm_planner_switches_domain_guidance(self):
        class Client:
            def __init__(self):
                self.messages = []

            def complete_json(self, messages, schema):
                self.messages.append(messages)
                return {
                    "goal": "answer",
                    "message": "已收到请求。",
                    "steps": [],
                    "output": {"type": "direct_answer"},
                }

        gis_client = Client()
        gis_planner = LLMPlanner(
            gis_client,
            ["get_raster_metadata"],
            planner_guidance=GIS_DOMAIN_PACK.planner_guidance(),
        )
        gis_planner.plan("查询栅格元数据")
        gis_prompt = gis_client.messages[0][0]["content"]
        self.assertIn("spatial_overview_result", gis_prompt)
        self.assertIn("get_raster_metadata", gis_prompt)

        text_client = Client()
        text_planner = LLMPlanner(
            text_client,
            ["summarize_text"],
            planner_guidance=TEXT_DOMAIN_PACK.planner_guidance(),
        )
        text_planner.plan("请摘要这段文本")
        text_prompt = text_client.messages[0][0]["content"]
        self.assertIn("text_summary_result", text_prompt)
        self.assertIn("summarize_text", text_prompt)
        for forbidden in ("dem", "land_use", "roads", "water", "洪山区"):
            self.assertNotIn(forbidden.lower(), text_prompt.lower())

    def test_runtime_factory_binds_selected_domain_guidance(self):
        with patch("agent.runtime_factory.load_openai_config", return_value={}), patch(
            "agent.runtime_factory.OpenAIPlannerClient", return_value=object()
        ):
            runtime = build_runtime("openai", "memory")

        self.assertEqual(runtime._domain_pack.domain_id, "gis")
        self.assertIn("spatial_overview_result", runtime._planner._system_prompt())


if __name__ == "__main__":
    unittest.main()
