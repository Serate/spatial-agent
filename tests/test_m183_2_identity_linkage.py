import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.action_identity import (
    ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION,
    build_action_receipt_identity_linkage,
)
from agent.artifact_store import ArtifactStore
from agent.recovery_action import project_action_receipt
from agent.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from agent.service import AgentService
from serve_api import AgentApiHandler
from evaluation.contract_harness import (
    compare_action_receipt_identity_linkages,
    normalize_action_receipt_identity_linkage,
)
from result_contract import build_result_contract


class M1832IdentityLinkageTests(unittest.TestCase):
    def test_linkage_binds_request_plan_result_and_evidence_without_transport_ids(self):
        payload = {
            "run_id": "run-linkage",
            "request": "查询文本摘要",
            "resolved_request": "查询文本摘要",
            "result_type": "text_summary_result",
            "plan": {"output": {"type": "text_summary_result"}},
            "plan_evidence": {
                "plan_identity": {
                    "version": "spatial-agent.plan-identity.v1",
                    "fingerprint": "sha256:plan-linkage",
                }
            },
            "status": "COMPLETED",
            "answer": "已完成",
            "steps": [],
        }
        contract = build_result_contract(payload)
        linkage = build_action_receipt_identity_linkage(
            {**payload, "result": contract}
        )
        receipt = project_action_receipt(
            {
                "action": "confirm",
                "status": "COMPLETED",
                "run_id": "run-linkage",
                "result_run_id": "run-linkage",
                "idempotency_key": "m1832-linkage",
                "input_fingerprint": "sha256:input",
                "identity_linkage": linkage,
            }
        )
        normalized = normalize_action_receipt_identity_linkage(
            {"action_receipt": receipt}
        ).as_dict()

        self.assertEqual(
            normalized["schema_version"], ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION
        )
        self.assertTrue(normalized["available"])
        self.assertEqual(
            normalized["request_identity"], contract["request_identity"]
        )
        self.assertEqual(
            normalized["plan_identity"],
            contract["planning"]["plan_identity"],
        )
        self.assertEqual(
            normalized["result_identity"]["type"], "text_summary_result"
        )
        self.assertEqual(
            normalized["evidence_identity"]["migration_state"], "current"
        )

        contract_with_receipt = build_result_contract(
            {**payload, "action_receipt": receipt}
        )
        async_evidence = normalize_async_result_evidence(
            build_async_result_evidence(contract_with_receipt, status="COMPLETED"),
            status="COMPLETED",
        )
        self.assertEqual(
            async_evidence["action_receipt"]["identity_linkage"],
            receipt["identity_linkage"],
        )

    def test_http_cancel_exposes_the_same_identity_linkage(self):
        with tempfile.TemporaryDirectory(prefix="m1832-http-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )

            class LinkageHandler(AgentApiHandler):
                pass

            LinkageHandler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), LinkageHandler)
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
                        "session_id": "m1832-http",
                        "require_confirmation": True,
                        "export_artifact": True,
                    },
                )
                response = _request_json(
                    port,
                    "POST",
                    "/runs/{}/cancel".format(pending["run_id"]),
                    {"idempotency_key": "m1832-http-cancel"},
                )
                artifact = store.read_run(response["run_id"], domain_id="gis")
                history = next(
                    item
                    for item in service.list_runs()["runs"]
                    if item["run_id"] == response["run_id"]
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        self.assertEqual(
            compare_action_receipt_identity_linkages(
                [response, artifact, history]
            ),
            [],
        )

    def test_cancel_linkage_survives_artifact_history_and_restart_replay(self):
        with tempfile.TemporaryDirectory(prefix="m1832-linkage-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            try:
                waiting = service.run(
                    "查询DEM栅格元数据",
                    session_id="m1832-linkage",
                    require_confirmation=True,
                    export_artifact=True,
                )
                response = service.cancel(
                    waiting["run_id"],
                    idempotency_key="m1832-cancel-1",
                )
                artifact = store.read_run(response["run_id"], domain_id="gis")
                history = next(
                    item
                    for item in service.list_runs()["runs"]
                    if item["run_id"] == response["run_id"]
                )
            finally:
                service.close()

            restarted = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            try:
                replay = restarted.cancel(
                    waiting["run_id"],
                    idempotency_key="m1832-cancel-1",
                )
            finally:
                restarted.close()

        entries = [response, artifact, history, replay]
        self.assertTrue(
            all(
                item["action_receipt"].get("identity_linkage", {}).get("available")
                for item in entries
            )
        )
        self.assertEqual(compare_action_receipt_identity_linkages(entries), [])
        self.assertEqual(
            response["action_receipt"]["identity_linkage"],
            replay["action_receipt"]["identity_linkage"],
        )


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


if __name__ == "__main__":
    unittest.main()
