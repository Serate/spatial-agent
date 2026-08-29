"""M275: domain-neutral Composite request/result/evidence contracts."""

from __future__ import annotations

import unittest

from agent.application.composite_contract import (
    CompositeContractError,
    build_composite_result_contract,
    normalize_composite_request,
    normalize_composite_section,
)
from agent.contract_versions import COMPOSITE_EVIDENCE_SCHEMA_VERSION
from agent.data_kinds import build_data_profile
from agent.nested_schema import NestedSchemaError, normalize_result_contract


def _request() -> dict:
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "组合查看区域空间条件与经济趋势",
        "components": [
            {
                "component_id": "space",
                "domain_id": "gis",
                "request": "查询区域边界和栅格概况",
                "planner": "rule",
                "backend": "local",
            },
            {
                "component_id": "economy",
                "domain_id": "economic",
                "request": "查询 GDP 年度趋势",
                "planner": "rule",
                "backend": "memory",
                "depends_on": ["space"],
            },
        ],
    }


def _children() -> dict:
    return {
        "space": {
            "run_id": "gis-run.json",
            "domain_id": "gis",
            "status": "COMPLETED",
            "answer": "空间数据已准备完成。",
            "artifact_ref": "gis-run.json",
            "result": {
                "type": "spatial_overview_result",
                "data_profile": build_data_profile(("composite", "vector", "raster")),
                "views": {
                    "schema_version": "spatial-agent.views.v1",
                    "panels": {
                        "map": {
                            "kind": "map",
                            "title": "空间范围",
                        }
                    },
                },
                "evidence_registry": {
                    "schema_version": "spatial-agent.evidence-registry.v1",
                    "available": True,
                    "entry_count": 1,
                    "entries": [{"id": "result", "schema_version": "spatial-agent.result-envelope.v1", "available": True, "state": "available", "reference": "result"}],
                },
            },
        },
        "economy": {
            "run_id": "economic-run.json",
            "domain_id": "economic",
            "status": "COMPLETED",
            "answer": "GDP 呈上升趋势。",
            "artifact_ref": "economic-run.json",
            "result": {
                "type": "economic_timeseries_result",
                "data_profile": build_data_profile(("timeseries", "document_evidence")),
                "views": {
                    "schema_version": "spatial-agent.views.v1",
                    "panels": {
                        "generic": {
                            "kind": "comparison_chart",
                            "title": "经济趋势",
                        }
                    },
                },
                "evidence_registry": {
                    "schema_version": "spatial-agent.evidence-registry.v1",
                    "available": True,
                    "entry_count": 1,
                    "entries": [{"id": "result", "schema_version": "spatial-agent.result-envelope.v1", "available": True, "state": "available", "reference": "result"}],
                },
            },
        },
    }


class M275CompositeContractTests(unittest.TestCase):
    def test_request_normalizes_and_rejects_dependency_cycles(self):
        normalized = normalize_composite_request(_request())
        self.assertTrue(normalized["fingerprint"].startswith("sha256:"))
        self.assertEqual(
            [item["component_id"] for item in normalized["components"]],
            ["space", "economy"],
        )

        cyclic = _request()
        cyclic["components"][0]["depends_on"] = ["economy"]
        with self.assertRaises(CompositeContractError) as context:
            normalize_composite_request(cyclic)
        self.assertEqual(context.exception.code, "composite_dependency_cycle")

    def test_mixed_profiles_views_and_evidence_share_one_envelope(self):
        result = build_composite_result_contract(_request(), _children())
        self.assertEqual(result["type"], "composite_result")
        self.assertEqual(result["data_profile"]["primary"], "composite")
        self.assertEqual(
            result["data_profile"]["kinds"],
            ["composite", "vector", "raster", "timeseries", "document_evidence"],
        )
        self.assertEqual(result["composite"]["state"], "completed")
        self.assertEqual(
            [item["component_id"] for item in result["composite"]["components"]],
            ["space", "economy"],
        )
        panels = result["views"]["panels"]
        self.assertIn("composite", panels)
        self.assertIn("space__map", panels)
        self.assertIn("economy__generic", panels)
        self.assertIn(
            "composite_evidence",
            [item["id"] for item in result["evidence_registry"]["entries"]],
        )
        self.assertEqual(
            result["composite"]["evidence"]["schema_version"],
            COMPOSITE_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(normalize_result_contract(result), result)

    def test_required_failure_is_not_silently_reported_as_success(self):
        children = _children()
        children["economy"] = {
            "domain_id": "economic",
            "status": "FAILED",
            "error_code": "economic_data_unavailable",
            "error": "经济数据暂不可用",
            "result": {
                "type": "economic_timeseries_result",
                "data_profile": build_data_profile(("timeseries",)),
            },
        }
        result = build_composite_result_contract(_request(), children)
        self.assertEqual(result["composite"]["state"], "failed")
        self.assertEqual(result["lifecycle"]["state"], "failed")
        failed = result["composite"]["evidence"]["failed_component_ids"]
        self.assertEqual(failed, ["economy"])
        self.assertEqual(
            result["composite"]["components"][1]["failure"]["code"],
            "economic_data_unavailable",
        )

    def test_missing_component_is_structured_blocked_state(self):
        result = build_composite_result_contract(_request(), {"space": _children()["space"]})
        self.assertEqual(result["composite"]["state"], "blocked")
        economy = result["composite"]["components"][1]
        self.assertEqual(economy["state"], "blocked")
        self.assertEqual(economy["failure"]["code"], "component_result_unavailable")
        self.assertEqual(
            normalize_composite_section(result["composite"]),
            result["composite"],
        )

    def test_composite_nested_boundary_rejects_missing_or_unknown_section(self):
        result = build_composite_result_contract(_request(), _children())
        missing = dict(result)
        missing.pop("composite")
        with self.assertRaises(NestedSchemaError):
            normalize_result_contract(missing)

        unknown = dict(result)
        unknown["composite"] = {**result["composite"], "schema_version": "future.v9"}
        with self.assertRaises(NestedSchemaError):
            normalize_result_contract(unknown)


if __name__ == "__main__":
    unittest.main()
