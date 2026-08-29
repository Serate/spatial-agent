"""Compact M327-C coverage for the shared typed-result summary contract."""

from __future__ import annotations

import json
import unittest

from agent.answer_generation import build_answer_context, build_composite_answer_context
from agent.application.composite_contract import build_composite_result_contract
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.result_summary import (
    RESULT_SUMMARY_SCHEMA_VERSION,
    ResultSummaryError,
    build_result_summary,
    normalize_result_summary,
)
from result_contract import build_result_contract


def _profile(*kinds: str) -> dict[str, object]:
    return {
        "schema_version": "spatial-agent.data-profile.v1",
        "primary": kinds[0],
        "kinds": list(kinds),
    }


class M327ResultSummaryProjectionTests(unittest.TestCase):
    def test_vector_raster_metrics_and_text_share_one_block_shape(self):
        payload = {
            "status": "COMPLETED",
            "answer": "四类资料均已整理，可以查看综合结论。",
            "typed_sections": [
                {
                    "block_id": "boundary",
                    "title": "空间范围",
                    "data_profile": _profile("vector"),
                    "state": "completed",
                    "conclusion": "已获得研究范围边界。",
                    "facts": {"feature_count": 4, "geometry": {"coordinates": [1, 2]}},
                    "evidence": {"available": True, "sources": ["boundary-source"]},
                },
                {
                    "block_id": "elevation",
                    "title": "高程数据",
                    "data_profile": _profile("raster"),
                    "state": "completed",
                    "conclusion": "高程统计已完成。",
                    "facts": {"minimum": 1.123456789, "maximum": 9.987654321},
                    "evidence": {"available": True, "sources": ["dem-source"]},
                },
                {
                    "block_id": "indicators",
                    "title": "指标统计",
                    "data_profile": _profile("metrics", "timeseries"),
                    "state": "completed",
                    "conclusion": "指标统计已完成。",
                    "facts": {"count": 12, "trend": "上升"},
                    "evidence": {"available": True, "sources": ["indicator-source"]},
                },
                {
                    "block_id": "notes",
                    "title": "文字说明",
                    "data_profile": _profile("text"),
                    "state": "completed",
                    "conclusion": "文字资料已归纳。",
                    "facts": {"paragraph_count": 3},
                    "evidence": {"available": True, "sources": ["document-source"]},
                },
            ],
        }

        summary = build_result_summary(payload)

        self.assertEqual(summary["schema_version"], RESULT_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(
            [item["kind"] for item in summary["blocks"]],
            ["vector", "raster", "metrics", "text"],
        )
        self.assertEqual(summary["blocks"][1]["facts"]["minimum"], 1.123457)
        self.assertEqual(summary["evidence"]["source_count"], 4)
        for block in summary["blocks"]:
            self.assertEqual(
                set(block),
                {
                    "block_id", "title", "kind", "kinds", "data_profile", "result_type", "state",
                    "status", "conclusion", "facts", "limitations", "evidence",
                },
            )

    def test_summary_redacts_internal_values_and_normalizes_persisted_shape(self):
        summary = build_result_summary(
            {
                "status": "COMPLETED",
                "typed_sections": [
                    {
                        "block_id": "safe",
                        "data_profile": _profile("text"),
                        "facts": {
                            "api_key": "secret",
                            "result_ref": "memory://private",
                            "coordinates": [1, 2],
                            "count": 2,
                        },
                        "evidence": {"available": False},
                    }
                ],
            }
        )
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertNotIn("secret", encoded)
        self.assertNotIn("memory://", encoded)
        self.assertNotIn("coordinates", encoded)
        self.assertEqual(summary["blocks"][0]["facts"], {"count": 2})
        self.assertEqual(normalize_result_summary(summary), summary)
        with self.assertRaises(ResultSummaryError):
            normalize_result_summary({**summary, "schema_version": "future.v2"})


class M327ResultSummaryIntegrationTests(unittest.TestCase):
    def test_result_contract_and_answer_context_expose_same_summary(self):
        result = AgentRunResult(
            run_id="m327-summary",
            status=RunStatus.COMPLETED,
            request="查询栅格统计",
            plan=TaskPlan(
                "查询栅格统计",
                [PlanStep("raster", "read", {})],
                {"type": "raster_statistics_result"},
            ),
            steps=[
                StepRun(
                    "raster",
                    "read",
                    {},
                    status="COMPLETED",
                    result={
                        "data_profile": _profile("raster"),
                        "statistics": {"minimum": 2.3456789, "maximum": 8.0},
                    },
                )
            ],
        )

        context = build_answer_context(result)
        contract = build_result_contract(result.to_dict())

        self.assertEqual(
            context["result_summary"]["schema_version"],
            RESULT_SUMMARY_SCHEMA_VERSION,
        )
        self.assertEqual(context["result_summary"]["blocks"][0]["kind"], "raster")
        self.assertEqual(
            context["result_summary"]["blocks"][0]["facts"]["statistics"]["minimum"],
            2.345679,
        )
        self.assertEqual(
            contract["result_summary"]["blocks"][0]["kind"],
            context["result_summary"]["blocks"][0]["kind"],
        )

    def test_composite_answer_context_uses_shared_blocks_for_multiple_types(self):
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "综合资料分析",
            "components": [
                {"component_id": "space", "domain_id": "gis", "request": "空间范围"},
                {"component_id": "indicator", "domain_id": "indicators", "request": "指标统计"},
            ],
        }
        result = build_composite_result_contract(
            request,
            {
                "space": {
                    "status": "COMPLETED",
                    "result": {
                        "type": "boundary_result",
                        "data_profile": _profile("vector"),
                        "answer": "空间范围已获得。",
                    },
                },
                "indicator": {
                    "status": "COMPLETED",
                    "result": {
                        "type": "indicator_metrics_result",
                        "data_profile": _profile("metrics"),
                        "answer": "指标统计已完成。",
                    },
                },
            },
        )

        context = build_composite_answer_context(result)

        self.assertEqual(
            [item["kind"] for item in context["result_summary"]["blocks"]],
            ["vector", "metrics"],
        )
        self.assertEqual(
            context["components"], context["result_summary"]["blocks"]
        )


if __name__ == "__main__":
    unittest.main()
