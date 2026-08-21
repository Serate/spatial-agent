"""M146 async polling and recovery view-evidence contract."""

import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from agent.service_async import build_async_result_evidence
from domains.text.runtime import build_text_runtime
from result_contract import build_result_contract
from serve_api import AgentApiHandler


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service, run_id, timeout=6.0):
    terminal = {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "REJECTED",
        "NEEDS_CLARIFICATION",
    }
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = service.get_run(run_id)
        if latest.get("status") in terminal:
            return latest
        time.sleep(0.01)
    raise AssertionError("async run did not reach terminal state: {!r}".format(latest))


def _get_json(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, payload


class M146AsyncViewEvidenceTests(unittest.TestCase):
    def test_projection_has_one_state_vocabulary_and_never_leaks_paths(self):
        runtime = build_text_runtime()
        completed = runtime.run("请摘要这段文本。")
        success = build_result_contract(
            {**completed.to_dict(), "result_type": "text_summary_result"},
            registry=runtime.result_registry(),
        )
        degraded = build_result_contract(
            {
                "result_type": "text_summary_result",
                "status": "COMPLETED",
                "degradation": {"status": "degraded", "items": []},
                "steps": [],
            },
            registry=runtime.result_registry(),
        )
        unavailable = build_result_contract(
            {
                "result_type": "text_summary_result",
                "status": "FAILED",
                "error": "摘要工具失败",
                "artifact_ref": r"D:\private\outputs\runs\failed.json",
                "steps": [],
            },
            registry=runtime.result_registry(),
        )

        success_evidence = build_async_result_evidence(success, status="COMPLETED")
        degraded_evidence = build_async_result_evidence(degraded, status="COMPLETED")
        unavailable_evidence = build_async_result_evidence(
            unavailable,
            status="FAILED",
            artifact_ref=r"D:\private\outputs\runs\failed.json",
        )

        self.assertEqual(success_evidence["state"], "success")
        self.assertEqual(degraded_evidence["state"], "degraded")
        self.assertEqual(unavailable_evidence["state"], "unavailable")
        self.assertEqual(unavailable_evidence["artifact"]["ref"], "failed.json")
        self.assertNotIn("D:/private", json.dumps(unavailable_evidence))
        self.assertEqual(
            success_evidence["views"]["panels"]["generic"]["state"],
            "available",
        )
        self.assertEqual(
            unavailable_evidence["views"]["panels"]["generic"]["state"],
            "unavailable",
        )

    def test_sqlite_restart_and_http_polling_preserve_view_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = str(root / "state.db")
            artifacts = ArtifactStore(root / "artifacts")
            first_service = AgentService(
                state_db_path=database,
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            submitted = first_service.run_async(
                request="请摘要这段异步文本并保留视图证据。",
                session_id="m146-async",
                planner="rule",
                backend="memory",
                export_artifact=True,
                idempotency_key="m146-async-key",
            )
            try:
                completed = _wait_for_terminal(first_service, submitted["run_id"])
                first_observation = first_service.get_async_observability(
                    submitted["run_id"]
                )
            finally:
                first_service.close()

            second_service = AgentService(
                state_db_path=database,
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            try:
                restored = second_service.get_run(submitted["run_id"])
                restarted_observation = second_service.get_async_observability(
                    submitted["run_id"]
                )

                class TextHandler(AgentApiHandler):
                    service = second_service

                server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    status, http_observation = _get_json(
                        server.server_address[1],
                        "/runs/{}".format(submitted["run_id"]) + "/async",
                    )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
            finally:
                second_service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(status, 200)
        for observation in (first_observation, restarted_observation, http_observation):
            evidence = observation["result_evidence"]
            self.assertEqual(evidence["state"], "success")
            self.assertEqual(evidence["result_type"], "text_summary_result")
            self.assertEqual(evidence["workspace"]["panels"], ["generic"])
            self.assertEqual(evidence["views"]["panels"]["generic"]["kind"], "text_summary")
            self.assertTrue(evidence["artifact"]["available"])
        self.assertEqual(
            first_observation["result_evidence"],
            restarted_observation["result_evidence"],
        )
        self.assertEqual(
            restarted_observation["result_evidence"],
            http_observation["result_evidence"],
        )
        self.assertEqual(
            restored["result"]["views"]["panels"]["generic"]["kind"],
            "text_summary",
        )


if __name__ == "__main__":
    unittest.main()
