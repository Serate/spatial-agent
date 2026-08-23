import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.artifact_store import ArtifactStore
from agent.geojson_exporter import export_run_summary as write_geojson
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.service import AgentService


TERMINAL_STATUSES = {
    "COMPLETED",
    "FAILED",
    "REJECTED",
    "NEEDS_CLARIFICATION",
}


class _GeometryRuntime:
    """Small runtime fixture that emits one real geometry-bearing result."""

    def run(
        self,
        request,
        session_id="default",
        timeout_seconds=None,
        run_id=None,
        expected_plan_fingerprint=None,
        expected_evidence_fingerprint=None,
        **kwargs,
    ):
        run_id = run_id or "fixture-run"
        plan = TaskPlan(
            goal="验证几何证据",
            steps=[PlanStep("boundary", "fixture_geometry", {}, [])],
            output={"type": "admin_area_result", "title": "行政区边界"},
        )
        step = StepRun(
            id="boundary",
            tool="fixture_geometry",
            args={},
            status="COMPLETED",
            attempts=1,
            result={
                "result_ref": "fixture://geometry/boundary",
                "geometry_source": "geopackage",
                "geometry_crs": "EPSG:4326",
            },
        )
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            request=request,
            session_id=session_id,
            plan=plan,
            steps=[step],
            answer="已生成几何证据。",
        )

    def export_result(self, result_ref, max_features=100):
        return {
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [114.3, 30.5]},
                    "properties": {"name": "fixture"},
                }
            ],
            "geometry_source": "geopackage",
            "crs": "EPSG:4326",
        }


def _wait_for_terminal(service, run_id, timeout=8.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = service.get_run(run_id)
        if last["status"] in TERMINAL_STATUSES:
            return last
        time.sleep(0.02)
    raise AssertionError("async run did not reach terminal state: {!r}".format(last))


def _canonical_envelope(payload):
    envelope = json.loads(json.dumps(payload["result"], ensure_ascii=False))

    def normalize_run_id_fields(value):
        if isinstance(value, dict):
            normalized = {}
            for key, item in value.items():
                if key in {"run_id", "subject_id", "result_run_id"} and item:
                    normalized[key] = "<run>"
                else:
                    normalized[key] = normalize_run_id_fields(item)
            if value.get("schema_version") == "spatial-agent.artifact-reference.v1":
                kind = value.get("kind")
                marker = "<artifact>" if kind == "run" else "<geojson>"
                if kind in {"run", "geojson"}:
                    normalized["ref"] = marker
                    if isinstance(normalized.get("access"), dict):
                        normalized["access"]["path"] = marker
            return normalized
        if isinstance(value, list):
            return [normalize_run_id_fields(item) for item in value]
        return value

    envelope["geometry"]["geojson_ref"] = "<geojson>"
    envelope["references"] = [
        {
            **reference,
            "ref": "<artifact>"
            if reference.get("kind") == "artifact"
            else "<geojson>"
            if reference.get("kind") == "geojson"
            else reference.get("ref"),
        }
        if reference.get("kind") in {"artifact", "geojson"}
        else reference
        for reference in envelope["references"]
    ]
    lineage = envelope.get("lineage") or {}
    if lineage:
        lineage["run_id"] = "<run>"
        for key in ("artifact", "geojson"):
            item = lineage.get(key) or {}
            if item.get("ref"):
                item["ref"] = "<artifact>" if key == "artifact" else "<geojson>"
        lineage["references"] = [
            {
                **reference,
                "ref": (
                    "<artifact>" if reference.get("kind") == "artifact"
                    else "<geojson>" if reference.get("kind") == "geojson"
                    else "<run>" if reference.get("kind") in {"run", "answer", "trace"}
                    else reference.get("ref")
                ),
            }
            for reference in lineage.get("references", [])
        ]
    return normalize_run_id_fields(envelope)


class M66EvidenceMatrixTests(unittest.TestCase):
    def _run_case(self, request, geometry_runtime=False, asynchronous=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geojson_root = root / "geojson"
            service = AgentService(
                artifact_store=ArtifactStore(str(root / "runs")),
                state_db_path=str(root / "state.db"),
            )
            runtime_patch = patch.object(
                service,
                "_runtime",
                return_value=_GeometryRuntime(),
            ) if geometry_runtime else None
            exporter_patch = patch(
                "agent.service.export_run_summary",
                side_effect=lambda payload, geometry_features=None: write_geojson(
                    payload,
                    root=str(geojson_root),
                    geometry_features=geometry_features,
                ),
            )
            try:
                if runtime_patch:
                    runtime_patch.start()
                exporter_patch.start()
                kwargs = {
                    "request": request,
                    "session_id": "m66-matrix",
                    "planner": "rule",
                    "backend": "memory",
                    "export_artifact": True,
                    "export_geojson": True,
                }
                if asynchronous:
                    submitted = service.run_async(**kwargs)
                    current = _wait_for_terminal(service, submitted["run_id"])
                else:
                    current = service.run(**kwargs)
                restored = AgentService(state_db_path=str(root / "state.db")).get_run(
                    current["run_id"]
                )
                # Validate references while the temporary artifact roots still
                # exist; callers receive immutable payload snapshots below.
                self._assert_references_and_files(current)
                self._assert_references_and_files(restored)
                return (
                    json.loads(json.dumps(current, ensure_ascii=False)),
                    json.loads(json.dumps(restored, ensure_ascii=False)),
                )
            finally:
                exporter_patch.stop()
                if runtime_patch:
                    runtime_patch.stop()
                service._async_executor.shutdown(wait=True)

    def _assert_references_and_files(self, payload):
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertTrue(payload.get("artifact_ref"))
        self.assertTrue(payload.get("geojson_ref"))
        artifact = Path(payload["artifact_ref"])
        geojson = Path(payload["geojson_ref"])
        self.assertTrue(artifact.is_file(), artifact)
        self.assertTrue(geojson.is_file(), geojson)

        artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
        geojson_payload = json.loads(geojson.read_text(encoding="utf-8"))
        self.assertEqual(artifact_payload["run_id"], payload["run_id"])
        self.assertEqual(artifact_payload["status"], payload["status"])
        self.assertEqual(geojson_payload["properties"]["run_id"], payload["run_id"])
        self.assertEqual(
            geojson_payload["properties"]["result_type"], payload["result_type"]
        )
        self.assertEqual(payload["result"]["geometry"]["geojson_ref"], payload["geojson_ref"])
        self.assertTrue(
            any(
                reference.get("kind") == "geojson"
                and reference.get("ref") == Path(payload["geojson_ref"]).name
                and reference.get("artifact_reference", {}).get("ref")
                == Path(payload["geojson_ref"]).name
                for reference in payload["result"]["references"]
            )
        )
        return geojson_payload

    def test_sync_async_poll_and_restart_preserve_no_geometry_envelope_and_refs(self):
        sync, sync_restored = self._run_case(
            "查询洪山区行政区边界", asynchronous=False
        )
        async_polled, async_restored = self._run_case(
            "查询洪山区行政区边界", asynchronous=True
        )

        for payload in (sync, sync_restored, async_polled, async_restored):
            geometry = payload["result"]["geometry"]
            self.assertEqual(geometry["status"], "no_geometry")
            self.assertFalse(geometry["available"])
            self.assertEqual(geometry["feature_count"], 0)
            self.assertFalse(geometry["truncated"])

        self.assertEqual(_canonical_envelope(sync), _canonical_envelope(sync_restored))
        self.assertEqual(
            _canonical_envelope(async_polled), _canonical_envelope(async_restored)
        )
        self.assertEqual(_canonical_envelope(sync), _canonical_envelope(async_polled))

    def test_real_geometry_evidence_survives_async_poll_and_service_restart(self):
        polled, restored = self._run_case(
            "验证几何证据", geometry_runtime=True, asynchronous=True
        )
        for payload in (polled, restored):
            geometry = payload["result"]["geometry"]
            self.assertEqual(geometry["status"], "real_geometry")
            self.assertTrue(geometry["available"])
            self.assertEqual(geometry["feature_count"], 1)
            self.assertFalse(geometry["truncated"])
            self.assertEqual(geometry["sources"], ["geopackage"])
            self.assertEqual(geometry["crs"], ["EPSG:4326"])

        self.assertEqual(_canonical_envelope(polled), _canonical_envelope(restored))
        self.assertEqual(polled["artifact_ref"], restored["artifact_ref"])
        self.assertEqual(polled["geojson_ref"], restored["geojson_ref"])


if __name__ == "__main__":
    unittest.main()
