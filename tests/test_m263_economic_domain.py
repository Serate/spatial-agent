import json
import os
import tempfile
import unittest
from pathlib import Path

from agent.domain_registry import domain_registry
from agent.domain_contract import planner_guidance
from agent.llm_planner import LLMPlanner
from agent.runtime_factory import build_runtime
from domains.economic.provider import EconomicToolProvider


def _payload():
    source = {
        "name": "官方统计公报测试来源",
        "url": "https://example.gov.cn/bulletin",
        "published_at": "2025-01-01",
        "retrieved_at": "2026-08-25",
        "version": "fixture-official-shaped",
        "license": "测试来源，不代表再分发许可",
        "locator": "一、综合/经济总量",
        "geography_level": "district",
    }
    rows = []
    for period, value in (("2023", 1180.31), ("2024", 1303.38), ("2025", 1365.8)):
        rows.append({
            "indicator": "gdp_total",
            "label": "地区生产总值",
            "region_id": "420111",
            "region": "洪山区",
            "geography_level": "district",
            "period": period,
            "period_type": "annual",
            "value": value,
            "unit": "亿元",
            "source": dict(source, version="fixture-" + period),
        })
    return {
        "schema_version": "spatial-agent.economic-data.v1",
        "dataset": "wuhan_hongshan_economic_indicators",
        "provenance": {"source": "fixture", "version": "m263", "retrieved_at": "2026-08-25"},
        "records": rows,
    }


class M263EconomicDomainTests(unittest.TestCase):
    def test_domain_is_registered(self):
        self.assertIn("economic", domain_registry().ids())
        self.assertEqual(domain_registry().resolve("economic").domain_id, "economic")

    def test_provider_returns_source_bound_trend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "economic.json"
            path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
            provider = EconomicToolProvider(str(path))
            result = provider.invoke(
                "economic_indicator_query",
                {"dataset": "wuhan_hongshan_economic_indicators", "operation": "trend", "indicator": "gdp_total", "regions": ["洪山区"], "period_type": "annual"},
            )
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["data_profile"]["primary"], "timeseries")
            self.assertEqual(len(result["rows"]), 3)
            self.assertTrue(result["source_evidence"][0]["url"].endswith("bulletin"))

    def test_provider_reports_region_and_period_states(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "economic.json"
            path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
            provider = EconomicToolProvider(str(path))
            base = {"dataset": "wuhan_hongshan_economic_indicators", "operation": "latest", "indicator": "gdp_total", "regions": ["武汉市"], "period_type": "annual"}
            self.assertEqual(provider.invoke("economic_indicator_query", base)["code"], "economic_region_unavailable")
            base["regions"] = ["洪山区"]
            base["period_type"] = "half_year"
            self.assertEqual(provider.invoke("economic_indicator_query", base)["code"], "economic_time_range_unavailable")

    def test_open_question_enters_structured_clarification(self):
        result = build_runtime("rule", "memory", domain_id="economic").run("武汉市洪山区最近经济发展状况如何")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertIn("indicator", result.clarification.get("missing_fields"))

    def test_runtime_executes_query_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "economic.json"
            path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
            old = os.environ.get("SPATIAL_AGENT_ECONOMIC_DATA")
            os.environ["SPATIAL_AGENT_ECONOMIC_DATA"] = str(path)
            try:
                result = build_runtime("rule", "memory", domain_id="economic").run("指标为gdp_total 洪山区趋势")
            finally:
                if old is None:
                    os.environ.pop("SPATIAL_AGENT_ECONOMIC_DATA", None)
                else:
                    os.environ["SPATIAL_AGENT_ECONOMIC_DATA"] = old
            self.assertEqual(result.status.value, "COMPLETED")
            self.assertEqual(result.plan.output["type"], "economic_timeseries_result")
            self.assertEqual(result.steps[0].result["status"], "ready")
            self.assertEqual(result.steps[1].result["data_profile"]["primary"], "document_evidence")
            self.assertIn("趋势", result.answer)

    def test_natural_query_prefix_and_indicator_label_do_not_pollute_region(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "economic.json"
            path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
            old = os.environ.get("SPATIAL_AGENT_ECONOMIC_DATA")
            os.environ["SPATIAL_AGENT_ECONOMIC_DATA"] = str(path)
            try:
                result = build_runtime("rule", "memory", domain_id="economic").run(
                    "查询洪山区地区生产总值"
                )
            finally:
                if old is None:
                    os.environ.pop("SPATIAL_AGENT_ECONOMIC_DATA", None)
                else:
                    os.environ["SPATIAL_AGENT_ECONOMIC_DATA"] = old
            self.assertEqual(result.status.value, "COMPLETED")
            self.assertEqual(result.request_facts["entities"]["regions"], ["洪山区"])
            self.assertEqual(result.steps[0].result["status"], "ready")

    def test_region_connector_does_not_become_part_of_region_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "economic.json"
            payload = _payload()
            payload["records"].append(dict(payload["records"][0], region_id="420100", region="武汉市", geography_level="city"))
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            old = os.environ.get("SPATIAL_AGENT_ECONOMIC_DATA")
            os.environ["SPATIAL_AGENT_ECONOMIC_DATA"] = str(path)
            try:
                result = build_runtime("rule", "memory", domain_id="economic").run("指标为gdp_total 洪山区和武汉市比较")
            finally:
                if old is None:
                    os.environ.pop("SPATIAL_AGENT_ECONOMIC_DATA", None)
                else:
                    os.environ["SPATIAL_AGENT_ECONOMIC_DATA"] = old
            self.assertEqual(result.status.value, "COMPLETED")
            self.assertEqual(result.steps[0].result["metrics"]["region_count"], 2)
            self.assertNotIn("和武汉市", result.request_facts["entities"]["regions"])

    def test_llm_planner_context_contains_only_registered_economic_tools(self):
        class _Client:
            def __init__(self):
                self.messages = []

            def complete_json(self, messages, schema):
                self.messages.append(messages)
                return {
                    "goal": "analyze an economic indicator time series",
                    "steps": [
                        {
                            "id": "query-economic-indicator",
                            "tool": "economic_indicator_query",
                            "args": {
                                "dataset": "wuhan_hongshan_economic_indicators",
                                "operation": "trend",
                                "indicator": "gdp_total",
                                "regions": ["洪山区"],
                                "period_type": "annual",
                            },
                            "depends_on": [],
                        }
                    ],
                    "output": {"type": "economic_timeseries_result", "summary": True},
                }

        runtime = build_runtime("rule", "memory", domain_id="economic")
        packet = runtime._build_context_packet("指标为gdp_total 洪山区趋势", "指标为gdp_total 洪山区趋势", "m263-llm", None)
        client = _Client()
        planner = LLMPlanner(
            client,
            runtime._registry.names,
            planner_guidance=planner_guidance(domain_registry().resolve("economic")),
        )
        plan = planner.plan("指标为gdp_total 洪山区趋势", context=packet.payload)
        self.assertEqual(plan.steps[0].tool, "economic_indicator_query")
        self.assertEqual(plan.output["type"], "economic_timeseries_result")
        self.assertIn("economic_source_evidence", json.dumps(client.messages, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
