import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from agent.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from evaluation.contract_harness import compare_action_effects
from serve_api import AgentApiHandler


class M189ActionEffectCrossEntryTests(unittest.TestCase):
    def test_service_artifact_history_async_and_restart_share_effect(self):
        with tempfile.TemporaryDirectory(prefix="m189-effect-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            try:
                waiting = service.run(
                    "查询DEM栅格元数据",
                    session_id="m189-effect",
                    require_confirmation=True,
                    export_artifact=True,
                )
                response = service.cancel(
                    waiting["run_id"], idempotency_key="m189-cancel"
                )
                detail = service.get_run(waiting["run_id"])
                artifact = store.read_run(waiting["run_id"], domain_id="gis")
                history = next(
                    item
                    for item in service.list_runs()["runs"]
                    if item["run_id"] == waiting["run_id"]
                )
                async_evidence = normalize_async_result_evidence(
                    build_async_result_evidence(
                        detail["result"], status=detail["status"]
                    ),
                    status=detail["status"],
                )
            finally:
                service.close()

            restarted = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            try:
                replay = restarted.cancel(
                    waiting["run_id"], idempotency_key="m189-cancel"
                )
            finally:
                restarted.close()

        entries = [response, detail, artifact, history, async_evidence, replay]
        self.assertEqual(compare_action_effects(entries), [])
        self.assertTrue(
            all(
                item.get("action_receipt", {}).get("effect", {}).get(
                    "result_available"
                )
                for item in entries[:5]
            )
        )

    def test_http_response_detail_and_artifact_share_effect(self):
        with tempfile.TemporaryDirectory(prefix="m189-http-effect-") as directory:
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
                        "session_id": "m189-http-effect",
                        "require_confirmation": True,
                        "export_artifact": True,
                    },
                )
                response = _request_json(
                    port,
                    "POST",
                    "/runs/{}/cancel".format(pending["run_id"]),
                    {"idempotency_key": "m189-http-cancel"},
                )
                detail = _request_json(
                    port, "GET", "/runs/{}".format(pending["run_id"])
                )
                artifact = store.read_run(pending["run_id"], domain_id="gis")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        self.assertEqual(compare_action_effects([response, detail, artifact]), [])

    def test_two_workers_replay_one_effect_without_duplicate_dispatch(self):
        with tempfile.TemporaryDirectory(prefix="m189-workers-effect-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"), artifact_store=store
            )
            second = AgentService(
                state_db_path=str(root / "state.db"), artifact_store=store
            )
            try:
                waiting = first.run(
                    "查询DEM栅格元数据",
                    session_id="m189-workers-effect",
                    require_confirmation=True,
                    export_artifact=True,
                )
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [
                        executor.submit(
                            worker.cancel,
                            waiting["run_id"],
                            idempotency_key="m189-worker-cancel",
                        )
                        for worker in (first, second)
                    ]
                    responses = []
                    for future in futures:
                        try:
                            responses.append(future.result())
                        except ValueError as exc:
                            self.assertIn("already in progress", str(exc))
                if len(responses) == 1:
                    responses.append(
                        first.cancel(
                            waiting["run_id"],
                            idempotency_key="m189-worker-cancel",
                        )
                    )
                detail = second.get_run(waiting["run_id"])
                artifact = store.read_run(waiting["run_id"], domain_id="gis")
            finally:
                first.close()
                second.close()

        self.assertEqual(compare_action_effects(responses + [detail, artifact]), [])
        self.assertEqual(len(responses), 2)


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
