import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.console_source import read_console_source

from agent.action_identity import build_action_receipt_identity_linkage
from agent.artifact_store import ArtifactStore
from agent.execution_timeline import (
    ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION,
    attach_action_receipt_timeline,
    normalize_execution_timeline,
)
from agent.recovery_action import project_action_receipt
from agent.service import AgentService
from agent.service_async import build_async_result_evidence
from evaluation.contract_harness import (
    compare_action_timelines,
    normalize_action_timeline_contract,
)
from result_contract import build_result_contract
from serve_api import AgentApiHandler


class M184ActionTimelineTests(unittest.TestCase):
    def test_text_and_gis_receipts_are_projected_as_bounded_action_events(self):
        for result_type in ("text_summary_result", "spatial_overview_result"):
            payload = _payload(result_type)
            contract = build_result_contract(payload)
            linkage = build_action_receipt_identity_linkage(
                {**payload, "result": contract}
            )
            receipt = project_action_receipt(
                {
                    "action": "confirm",
                    "status": "COMPLETED",
                    "run_id": payload["run_id"],
                    "result_run_id": payload["run_id"],
                    "idempotency_key": "m184-private-key",
                    "input_fingerprint": "sha256:private-input",
                    "identity_linkage": linkage,
                }
            )
            updated = attach_action_receipt_timeline(
                {**payload, "result": contract}, receipt
            )
            timeline = normalize_execution_timeline(
                updated["result"]["execution_timeline"]
            )
            action = next(
                item for item in timeline["events"] if item["kind"] == "action"
            )
            action_linkage = action["action_linkage"]
            self.assertEqual(
                action_linkage["schema_version"],
                ACTION_TIMELINE_LINKAGE_SCHEMA_VERSION,
            )
            self.assertEqual(action_linkage["action_id"], "confirm")
            self.assertTrue(action_linkage["identity_linkage"]["available"])
            self.assertNotIn("m184-private-key", str(action))
            self.assertNotIn("private-input", str(action))
            self.assertTrue(
                normalize_action_timeline_contract(updated).as_dict()["available"]
            )

    def test_artifact_and_async_projection_keep_the_same_action_timeline(self):
        payload = _payload("text_summary_result")
        contract = build_result_contract(payload)
        receipt = project_action_receipt(
            {
                "action": "cancel",
                "status": "COMPLETED",
                "run_id": payload["run_id"],
                "result_run_id": payload["run_id"],
                "identity_linkage": build_action_receipt_identity_linkage(
                    {**payload, "result": contract}
                ),
            }
        )
        updated = attach_action_receipt_timeline(
            {**payload, "result": contract}, receipt
        )
        with tempfile.TemporaryDirectory(prefix="m184-timeline-") as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            store.write_run(updated)
            artifact = store.read_run(payload["run_id"], domain_id="gis")
            async_evidence = build_async_result_evidence(
                artifact["result"], status="COMPLETED"
            )

        self.assertEqual(
            compare_action_timelines(
                [
                    updated,
                    artifact,
                    {"execution_timeline": async_evidence["execution_timeline"]},
                ]
            ),
            [],
        )

    def test_unknown_action_linkage_version_degrades_without_copying_fields(self):
        timeline = normalize_execution_timeline(
            {
                "schema_version": "spatial-agent.execution-timeline.v1",
                "available": True,
                "events": [
                    {
                        "kind": "action",
                        "action_linkage": {
                            "schema_version": "spatial-agent.action-timeline-linkage.v99",
                            "action_id": "secret-action",
                            "private": "must-not-cross-boundary",
                        },
                    }
                ],
            }
        )
        action = timeline["events"][0]["action_linkage"]
        self.assertFalse(action["available"])
        self.assertEqual(
            action["reason_code"],
            "action_timeline_linkage_unknown_schema",
        )
        self.assertNotIn("private", str(action))

    def test_console_renders_action_timeline_from_structured_result(self):
        source = read_console_source(Path(__file__).parents[1])
        self.assertIn("renderActionTimeline", source)
        self.assertIn("action-timeline", source)

    def test_http_response_detail_and_artifact_share_action_timeline(self):
        with tempfile.TemporaryDirectory(prefix="m184-http-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )

            class Handler(AgentApiHandler):
                pass

            Handler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                pending = _request_json(
                    port,
                    "POST",
                    "/runs",
                    {
                        "request": "查询DEM栅格元数据",
                        "session_id": "m184-http",
                        "require_confirmation": True,
                        "export_artifact": True,
                    },
                )
                response = _request_json(
                    port,
                    "POST",
                    "/runs/{}/cancel".format(pending["run_id"]),
                    {"idempotency_key": "m184-http-action"},
                )
                detail = _request_json(
                    port,
                    "GET",
                    "/runs/{}".format(pending["run_id"]),
                )
                artifact = store.read_run(pending["run_id"], domain_id="gis")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        self.assertEqual(
            compare_action_timelines([response, detail, artifact]), []
        )

    def test_two_service_workers_share_action_timeline_through_sqlite_cas(self):
        with tempfile.TemporaryDirectory(prefix="m184-workers-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            second = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            try:
                pending = first.run(
                    "查询DEM栅格元数据",
                    session_id="m184-workers",
                    require_confirmation=True,
                    export_artifact=True,
                )
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [
                        executor.submit(
                            service.cancel,
                            pending["run_id"],
                            idempotency_key="m184-worker-cancel",
                        )
                        for service in (first, second)
                    ]
                    responses = []
                    in_progress = 0
                    for future in futures:
                        try:
                            responses.append(future.result())
                        except ValueError as exc:
                            if "already in progress" not in str(exc):
                                raise
                            in_progress += 1
                if in_progress:
                    # The CAS owner has completed by the time both workers
                    # join.  A retry with the same key must replay the one
                    # receipt instead of dispatching cancel again.
                    responses.append(
                        first.cancel(
                            pending["run_id"],
                            idempotency_key="m184-worker-cancel",
                        )
                    )
                detail = second.get_run(pending["run_id"])
                artifact = store.read_run(pending["run_id"], domain_id="gis")
            finally:
                first.close()
                second.close()

        self.assertEqual(compare_action_timelines(responses + [detail, artifact]), [])


def _request_json(port, method, path, payload=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
    if response.status >= 400:
        raise AssertionError("HTTP {}: {}".format(response.status, data))
    return data


def _payload(result_type):
    return {
        "run_id": "m184-action-timeline",
        "request": "执行一个开放式请求",
        "resolved_request": "执行一个开放式请求",
        "result_type": result_type,
        "plan": {"output": {"type": result_type}},
        "plan_evidence": {
            "plan_identity": {
                "version": "spatial-agent.plan-identity.v1",
                "fingerprint": "sha256:m184-plan",
            }
        },
        "status": "COMPLETED",
        "answer": "已完成",
        "steps": [],
    }


if __name__ == "__main__":
    unittest.main()
