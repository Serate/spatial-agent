import json
import unittest
from copy import deepcopy

from evaluation.contract_harness import compare_results, normalize_result


def _payload():
    return {
        "status": "COMPLETED",
        "run_id": "run-original",
        "artifact_schema_version": "spatial-agent.run-artifact.v1",
        "artifact_ref": r"D:\private\runs\run-original.json",
        "answer": "结果已完成",
        "steps": [],
        "trace_summary": [],
        "async_observability": {
            "run_id": "run-original",
            "request_fingerprint": "request:original",
            "timestamps": {"finished_at": "2026-08-21T00:00:00Z"},
            "result_evidence": {
                "schema_version": "spatial-agent.async-result-evidence.v1",
                "state": "degraded",
                "status": "COMPLETED",
                "degradation_status": "degraded",
                "artifact": {
                    "available": True,
                    "ref": r"D:\private\runs\run-original.json",
                },
                "views": {
                    "schema_version": "spatial-agent.views.v1",
                    "panels": {
                        "map": {
                            "kind": "map",
                            "state": "available",
                            "artifact_available": True,
                            "ref": "/private/map.geojson",
                        }
                    },
                },
            },
        },
        "result": {
            "type": "spatial_analysis_result",
            "title": "空间分析",
            "lineage": {
                "artifact": {
                    "available": True,
                    "ref": r"D:\private\runs\run-original.json",
                }
            },
            "degradation": {
                "schema_version": "spatial-agent.degradation.v1",
                "status": "degraded",
                "items": [
                    {
                        "code": "raster_alignment_degraded",
                        "severity": "warning",
                        "message": "首次输出说明",
                        "source": r"D:\private\data\dem.tif",
                    }
                ],
            },
            "views": {
                "schema_version": "spatial-agent.views.v1",
                "panels": {
                    "map": {
                        "kind": "map",
                        "state": "available",
                        "artifact_available": True,
                        "title": "地图",
                        "bounds": [1, 2, 3, 4],
                    }
                },
            },
            "planning": {},
        },
    }


class M148ContractHarnessTests(unittest.TestCase):
    def test_evidence_projection_ignores_transport_detail_and_old_shape_is_valid(self):
        first = _payload()
        second = deepcopy(first)
        second["run_id"] = "run-other"
        second["artifact_ref"] = "/var/lib/agent/runs/run-other.json"
        second["async_observability"]["run_id"] = "run-other"
        second["async_observability"]["request_fingerprint"] = "request:other"
        second["async_observability"]["timestamps"]["finished_at"] = "later"
        second["async_observability"]["result_evidence"]["artifact"]["ref"] = (
            "run-other.json"
        )
        second["async_observability"]["result_evidence"]["views"]["panels"]["map"][
            "ref"
        ] = "other-map.geojson"
        second["result"]["lineage"]["artifact"]["ref"] = "run-other.json"
        second["result"]["degradation"]["items"][0].update(
            {
                "severity": "info",
                "message": "另一条说明",
                "source": "other-source",
            }
        )
        second["result"]["views"]["panels"]["map"].update(
            {"title": "另一标题", "bounds": [5, 6, 7, 8]}
        )

        self.assertEqual(compare_results([first, second]), [])
        projection = normalize_result(first).as_dict()
        self.assertEqual(
            projection["artifact_schema"], "spatial-agent.run-artifact.v1"
        )
        self.assertTrue(projection["artifact_available"])
        self.assertEqual(
            projection["async_result_evidence"]["schema_version"],
            "spatial-agent.async-result-evidence.v1",
        )
        self.assertEqual(
            projection["degradation_and_view_states"]["degradation"]["codes"],
            ["raster_alignment_degraded"],
        )
        self.assertEqual(
            projection["degradation_and_view_states"]["views"]["panels"]["map"],
            {"kind": "map", "state": "available", "artifact_available": True},
        )

        legacy = {
            "status": "COMPLETED",
            "result": {
                "type": "legacy_result",
                "views": {"panels": {"steps": {"kind": "steps"}}},
            },
        }
        legacy_projection = normalize_result(legacy).as_dict()
        self.assertIsNone(legacy_projection["artifact_schema"])
        self.assertIsNone(legacy_projection["async_result_evidence"])
        self.assertFalse(legacy_projection["artifact_available"])

    def test_evidence_version_state_code_kind_and_availability_drift_is_reported(self):
        cases = (
            ("artifact_schema", "spatial-agent.run-artifact.v2", "$.artifact_schema"),
            (
                "async_state",
                "unavailable",
                "$.async_result_evidence.state",
            ),
            (
                "degradation_code",
                "different_code",
                "$.degradation_and_view_states.degradation.codes",
            ),
            (
                "view_kind",
                "table",
                "$.degradation_and_view_states.views.panels.map.kind",
            ),
            (
                "view_state",
                "unavailable",
                "$.degradation_and_view_states.views.panels.map.state",
            ),
            ("artifact_available", False, "$.artifact_available"),
        )
        for name, value, expected_path in cases:
            with self.subTest(name=name):
                changed = _payload()
                if name == "artifact_schema":
                    changed["artifact_schema_version"] = value
                elif name == "async_state":
                    changed["async_observability"]["result_evidence"]["state"] = value
                elif name == "degradation_code":
                    changed["result"]["degradation"]["items"][0]["code"] = value
                elif name == "view_kind":
                    changed["result"]["views"]["panels"]["map"]["kind"] = value
                elif name == "view_state":
                    changed["result"]["views"]["panels"]["map"]["state"] = value
                else:
                    changed["result"]["lineage"]["artifact"]["available"] = value

                differences = compare_results([_payload(), changed])
                self.assertTrue(
                    any(item.startswith("entry[0] vs entry[1]: " + expected_path) for item in differences),
                    differences,
                )

        stable = normalize_result(_payload()).as_dict()
        evidence_json = json.dumps(
            {
                "artifact_schema": stable["artifact_schema"],
                "async_result_evidence": stable["async_result_evidence"],
                "degradation_and_view_states": stable["degradation_and_view_states"],
                "artifact_available": stable["artifact_available"],
            },
            ensure_ascii=False,
        )
        self.assertNotIn("run-original", evidence_json)
        self.assertNotIn("private", evidence_json)
        self.assertNotIn("finished_at", evidence_json)


if __name__ == "__main__":
    unittest.main()
