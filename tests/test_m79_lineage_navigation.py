"""M79 lineage navigation: history / comparison / retry open the original run
detail (answer, trace, map, GeoJSON, release evidence, context) without
re-invoking the model.
"""

import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.errors import ToolError
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tools import ToolRegistry
from result_contract import build_history_lineage, build_result_contract


def _registry():
    definitions = {
        name: {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": False},
        }
        for name in ("make_value", "fail_value", "use_value")
    }
    calls = {}

    class Adapter:
        def invoke(self, name, arguments):
            calls[name] = calls.get(name, 0) + 1
            if name == "make_value":
                return {"value": "retained"}
            if name == "fail_value":
                if calls[name] == 1:
                    raise ToolError("simulated backend failure")
                return {"value": "recovered"}
            if name == "use_value":
                return {"ok": True}
            raise AssertionError(name)

    return ToolRegistry(definitions, Adapter()), calls


class FailurePlanner:
    def plan(self, request):
        return TaskPlan(
            goal="exercise retry lineage",
            steps=[
                PlanStep("first", "make_value", {}, []),
                PlanStep("second", "fail_value", {}, ["first"]),
                PlanStep("third", "use_value", {}, ["second"]),
            ],
        )


class M79LineageNavigationTests(unittest.TestCase):
    def test_artifact_persists_durable_detail_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(str(Path(tmpdir) / "runs"))
            service = AgentService(artifact_store=store)
            result = service.run(
                "查询DEM栅格元数据",
                export_artifact=True,
                export_geojson=True,
            )
            path = Path(result["artifact_ref"])
            self.assertTrue(path.exists())
            artifact = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["run_id"], result["run_id"])
            self.assertEqual(artifact["session_id"], result.get("session_id"))
            self.assertEqual(artifact["status"], "COMPLETED")
            self.assertEqual(artifact["result_type"], result.get("result_type"))
            self.assertEqual(artifact["geojson_ref"], result.get("geojson_ref"))
            self.assertIn("artifact_ref", artifact)
            self.assertIn("trace_summary", artifact)
            self.assertIn("provenance", artifact)

    def test_artifact_read_run_returns_payload_or_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(str(Path(tmpdir) / "runs"))
            result = AgentService(artifact_store=store).run("你好", export_artifact=True)
            payload = store.read_run(result["run_id"])
            self.assertIsNotNone(payload)
            self.assertEqual(payload["run_id"], result["run_id"])
            self.assertEqual(payload["answer"], result["answer"])
            self.assertIsNone(store.read_run("missing-run-id"))
            self.assertIsNone(store.read_run(""))
            self.assertIsNone(store.read_run(None))

    def test_get_run_serves_degraded_detail_from_artifact_after_restart(self):
        # A fresh service (no in-memory state) that only shares the artifact
        # store simulates a process restart. Opening the run detail must not
        # re-invoke the model: the stored answer must come back unchanged.
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(str(Path(tmpdir) / "runs"))
            original = AgentService(artifact_store=store).run(
                "查询DEM栅格元数据",
                export_artifact=True,
            )
            restarted = AgentService(artifact_store=store)
            detail = restarted.get_run(original["run_id"])
            self.assertEqual(detail["run_id"], original["run_id"])
            self.assertEqual(detail["status"], original["status"])
            self.assertEqual(detail["answer"], original["answer"])
            self.assertEqual(detail["request"], original["request"])
            self.assertIn("result", detail)
            self.assertEqual(
                detail["result"]["lineage"]["run_id"], original["run_id"]
            )
            self.assertTrue(detail["result"]["lineage"]["answer"]["available"])
            self.assertTrue(detail["result"]["lineage"]["trace"]["available"])
            self.assertTrue(detail["result"]["lineage"]["artifact"]["available"])
            self.assertIn("trace_summary", detail)
            self.assertIn("provenance", detail)

    def test_get_run_raises_when_no_store_and_no_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService(artifact_store=ArtifactStore(str(Path(tmpdir) / "runs")))
            with self.assertRaises(ValueError):
                service.get_run("never-ran-run-id")

    def test_history_records_carry_navigational_run_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService(artifact_store=ArtifactStore(str(Path(tmpdir) / "runs")))
            service.run("你好", export_artifact=True)
            service.run("查询DEM栅格元数据", export_artifact=True)
            history = service.list_runs(limit=10)
            records = history["runs"]
            self.assertGreaterEqual(len(records), 2)
            for record in records:
                self.assertTrue(record.get("run_id"))
                lineage = record.get("lineage") or {}
                self.assertEqual(lineage.get("run_id"), record.get("run_id"))
                kinds = [ref.get("kind") for ref in lineage.get("references", [])]
                self.assertIn("run", kinds)
                self.assertIn("answer", kinds)
                self.assertIn("trace", kinds)

    def test_history_lineage_defers_trace_until_detail_open(self):
        lineage = build_history_lineage(
            {"run_id": "run-1", "status": "COMPLETED", "request": "你好"}
        )
        self.assertFalse(lineage["trace"]["available"])
        self.assertTrue(lineage["trace"]["deferred"])
        self.assertEqual(lineage["run_id"], "run-1")

    def test_comparison_rows_carry_run_ids_for_navigation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService(artifact_store=ArtifactStore(str(Path(tmpdir) / "runs")))
            comparison = service.compare_buildability("洪山区", [15, 20])
            rows = comparison["results"]
            self.assertGreaterEqual(len(rows), 2)
            run_ids = [row.get("run_id") for row in rows]
            self.assertTrue(all(run_ids))
            self.assertEqual(
                sorted(comparison["lineage"]["run_ids"]), sorted(run_ids)
            )
            for row in rows:
                detail = service.get_run(row["run_id"])
                self.assertEqual(detail["run_id"], row["run_id"])
                self.assertIn("result", detail)

    def test_region_comparison_rows_keep_child_run_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService(artifact_store=ArtifactStore(str(Path(tmpdir) / "runs")))
            comparison = service.compare_buildability_regions(["洪山区", "江夏区"], threshold=20)
            rows = comparison["results"]
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row.get("run_id") for row in rows))
            self.assertEqual(
                sorted(comparison["lineage"]["run_ids"]),
                sorted(row["run_id"] for row in rows),
            )

    def test_retry_keeps_run_id_and_marks_lineage_retry(self):
        registry_instance, _ = _registry()
        runtime = AgentRuntime(FailurePlanner(), registry_instance, max_retries=0)
        failed = runtime.run("fail")
        self.assertEqual(failed.status.value, "FAILED")

        recovered = runtime.retry_failed(failed.run_id)
        self.assertEqual(recovered.run_id, failed.run_id)
        self.assertEqual(recovered.status.value, "COMPLETED")
        self.assertEqual(recovered.retry_count, 1)

        payload = recovered.to_dict()
        payload["trace_summary"] = ["trace"]
        contract = build_result_contract(payload)
        self.assertTrue(contract["lineage"]["retry"]["available"])
        self.assertEqual(contract["lineage"]["retry"]["count"], 1)
        self.assertEqual(contract["lineage"]["retry"]["ref"], failed.run_id)


if __name__ == "__main__":
    unittest.main()
