import unittest
from pathlib import Path

from tests.console_source import read_console_source

from agent.models import AgentRunResult, RunStatus
from agent.trace_formatter import format_trace
from result_contract import build_result_contract


class M99ReplanningContractTests(unittest.TestCase):
    def test_result_envelope_and_lineage_share_versioned_replanning_evidence(self):
        payload = {
            "run_id": "replan-contract",
            "status": "COMPLETED",
            "request": "恢复空间分析",
            "answer": "已降级完成",
            "result_type": "dataset_health_result",
            "replan_events": [
                {
                    "failed_step_id": "screening",
                    "failed_tool": "get_zonal_buildability_analysis",
                    "failure_category": "tool_gate",
                    "replanned_step_ids": ["health", "fallback"],
                    "latency_ms": 12.3456,
                    "occurred_at": 100.1234,
                    "error": "must not cross the result contract",
                }
            ],
        }

        contract = build_result_contract(payload)
        evidence = contract["replanning"]
        self.assertEqual(evidence["schema_version"], "spatial-agent.replanning.v1")
        self.assertTrue(evidence["available"])
        self.assertEqual(evidence["count"], 1)
        self.assertNotIn("error", evidence["events"][0])
        self.assertEqual(contract["lineage"]["replanning"]["count"], 1)

    def test_malformed_events_are_ignored_and_bounded(self):
        events = [None, {"failed_step_id": "missing-tool"}]
        events.extend(
            {
                "failed_step_id": "step-{}".format(index),
                "failed_tool": "tool",
                "replanned_step_ids": ["x"] * 40,
            }
            for index in range(12)
        )
        evidence = build_result_contract({"result_type": "unknown", "replan_events": events})[
            "replanning"
        ]
        self.assertEqual(evidence["count"], 8)
        self.assertLessEqual(len(evidence["events"][0]["replanned_step_ids"]), 24)

    def test_trace_explains_adaptive_replan(self):
        result = AgentRunResult(
            run_id="trace-replan",
            status=RunStatus.COMPLETED,
            request="恢复分析",
            replan_events=[
                {
                    "failed_step_id": "screening",
                    "failed_tool": "screen_tool",
                    "replanned_step_ids": ["health", "fallback"],
                }
            ],
        )
        trace = format_trace(result)
        self.assertTrue(any("Adaptive replan" in line for line in trace))
        self.assertTrue(any("screening" in line and "fallback" in line for line in trace))

    def test_console_prefers_result_envelope_replanning_evidence(self):
        source = read_console_source(Path(__file__).parents[1])
        self.assertIn("envelope.replanning", source)
        self.assertIn("data.replan_events", source)


if __name__ == "__main__":
    unittest.main()
