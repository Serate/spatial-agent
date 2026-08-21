"""M148-E: bounded Docker/offline recorded-model replay acceptance slice.

This test is intentionally opt-in.  It runs the two existing redacted
``m127_domain_replay_suite.json`` cases through a test-only recorded client,
then exercises AgentService, the durable run artifact, HTTP async polling and
restart recovery.  The recorded client never opens a network connection.

Scope is deliberately explicit:

* executed: real container dependencies and mounted GIS data for the GIS case,
  Text/GIS Domain Packs, LLMPlanner, ToolRegistry, AgentService, SQLite,
  artifact export/recovery, and the development HTTP entry point;
* not executed: a live model/provider request, production Uvicorn at port 8088,
  or browser/Console rendering.  Those require separate injection or external
  processes and must not be represented as offline replay evidence.

Run explicitly inside the production image, for example::

    docker exec -e SPATIAL_AGENT_M148_DOCKER_REPLAY=1 \
      ai-agent-spatial-agent-1 python -m unittest \
      tests.test_m148_docker_replay -v

The file is not part of the default compact test allowlist.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from agent.artifact_store import ArtifactStore
from agent.domain_contract import planner_guidance
from agent.llm_planner import LLMPlanner
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tools import ToolRegistry
from evaluation.contract_harness import compare_results
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK
from serve_api import AgentApiHandler


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "m127_domain_replay_suite.json"
OPT_IN = "SPATIAL_AGENT_M148_DOCKER_REPLAY"
TERMINAL = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
    "REJECTED",
    "NEEDS_CLARIFICATION",
}
_PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|private|Users|tmp)/)")
_FORBIDDEN_TERMS = ("api_key", "authorization", "raw_response", "secret")


class _RecordedModelClient:
    """Test-only model seam; it returns a copied fixture and records calls."""

    def __init__(self, response: Mapping[str, Any], metrics: Mapping[str, Any], calls: list):
        self._response = copy.deepcopy(dict(response))
        self._metrics = dict(metrics)
        self._calls = calls

    def complete_json(self, messages, schema):
        self._calls.append({"message_count": len(messages), "schema_type": schema.get("type")})
        return copy.deepcopy(self._response)

    def metrics(self):
        return dict(self._metrics)


def _load_cases() -> list[Mapping[str, Any]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list):
        raise AssertionError("m127 replay fixture must contain fixtures")
    selected = {
        str(item.get("domain")): item
        for item in fixtures
        if isinstance(item, Mapping)
        and str(item.get("fixture_id")) in {"text-open-summary", "gis-complex-overview"}
    }
    if set(selected) != {"text", "gis"}:
        raise AssertionError("m127 fixture must provide exactly one Text and one GIS case")
    for domain, fixture in selected.items():
        turns = fixture.get("turns")
        if not isinstance(turns, list) or len(turns) != 1:
            raise AssertionError(domain + " replay case must remain one bounded turn")
        if not isinstance(turns[0].get("response"), Mapping):
            raise AssertionError(domain + " replay response is missing")
    return [selected["text"], selected["gis"]]


def _runtime_factory_for(
    fixture: Mapping[str, Any],
    calls: list,
):
    domain = str(fixture["domain"])
    turn = fixture["turns"][0]
    response = turn["response"]
    metrics = dict(fixture.get("provider_metrics") or {})
    metrics.update(
        {
            "provider": "offline-recorded-fixture",
            "execution_mode": "offline_replay",
            "fixture_id": str(fixture["fixture_id"]),
            "status": "success",
        }
    )
    domain_pack = TEXT_DOMAIN_PACK if domain == "text" else GIS_DOMAIN_PACK

    def factory(planner: str, backend: str, **kwargs: Any) -> AgentRuntime:
        if planner != "openai":
            raise AssertionError("M148 replay must use the LLMPlanner seam")
        provider = domain_pack.tool_provider(backend_name=backend, root=ROOT)
        registry = ToolRegistry.from_provider(provider)
        client = _RecordedModelClient(response, metrics, calls)
        planner_adapter = LLMPlanner(
            client,
            registry.names,
            planner_guidance=planner_guidance(domain_pack),
        )
        return AgentRuntime(
            planner_adapter,
            registry,
            state_store=kwargs.get("state_store"),
            conversation_store=kwargs.get("conversation_store"),
            memory=kwargs.get("memory"),
            observability=kwargs.get("observability"),
            backend_name=backend,
            planner_name=planner,
            domain_pack=domain_pack,
        )

    return factory


def _http_json(port: int, method: str, path: str, payload: Mapping[str, Any] | None = None):
    connection = HTTPConnection("127.0.0.1", port, timeout=30)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    status = response.status
    connection.close()
    if path.startswith("/artifacts/"):
        return status, raw
    return status, json.loads(raw.decode("utf-8"))


def _wait_for_async(port: int, run_id: str) -> Mapping[str, Any]:
    deadline = time.monotonic() + 90
    latest: Mapping[str, Any] | None = None
    while time.monotonic() < deadline:
        status, latest = _http_json(port, "GET", "/runs/" + run_id + "/async")
        if status != 200:
            raise AssertionError("async polling returned HTTP " + str(status))
        if latest.get("status") in TERMINAL:
            return latest
        time.sleep(0.05)
    raise AssertionError("async replay did not reach terminal state: {!r}".format(latest))


def _assert_safe_evidence(testcase: unittest.TestCase, evidence: Any) -> None:
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    lower = encoded.lower()
    for term in _FORBIDDEN_TERMS:
        testcase.assertNotIn(term, lower)
    testcase.assertIsNone(_PRIVATE_PATH.search(encoded), encoded)


class M148DockerReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(OPT_IN, "").lower() not in {"1", "true", "yes"}:
            raise unittest.SkipTest(
                "bounded Docker replay is opt-in; set " + OPT_IN + "=1"
            )

    def test_text_and_gis_replay_cross_agent_artifact_async_and_recovery(self):
        summaries = []
        for fixture in _load_cases():
            domain = str(fixture["domain"])
            backend = "local" if domain == "gis" else "memory"
            calls_before_restart: list = []
            calls_after_restart: list = []
            with tempfile.TemporaryDirectory(prefix="m148-replay-") as directory:
                root = Path(directory)
                artifact_root = root / "runs"
                artifacts = ArtifactStore(artifact_root)
                state_db = root / "state.db"
                first = AgentService(
                    artifact_store=artifacts,
                    state_db_path=str(state_db),
                    runtime_factory=_runtime_factory_for(fixture, calls_before_restart),
                )
                second = None
                server = None
                thread = None
                try:
                    request = str(fixture["turns"][0]["request"])
                    expected = fixture["turns"][0]["expected"]
                    sync = first.run(
                        request=request,
                        session_id="m148-e-sync-" + domain,
                        planner="openai",
                        backend=backend,
                        export_artifact=True,
                    )
                    self.assertEqual(sync["status"], expected["expected_status"])
                    self.assertEqual(sync["result"]["type"], expected["expected_result_type"])
                    self.assertEqual(
                        sync["result"]["model_evidence"]["execution_mode"],
                        "offline_replay",
                    )
                    self.assertEqual(sync["result"]["model_evidence"]["fixture_id"], fixture["fixture_id"])
                    self.assertEqual(len(calls_before_restart), 1)
                    _assert_safe_evidence(self, sync["result"]["model_evidence"])
                    _assert_safe_evidence(self, sync["result"].get("deployment_evidence"))

                    sync_artifact_path = Path(sync["artifact_ref"])
                    self.assertTrue(sync_artifact_path.is_file())
                    sync_artifact = json.loads(sync_artifact_path.read_text(encoding="utf-8"))
                    self.assertEqual(sync_artifact["artifact_schema_version"], "spatial-agent.run-artifact.v1")
                    self.assertEqual(sync_artifact["result"]["model_evidence"]["execution_mode"], "offline_replay")
                    self.assertNotIn("raw_response", json.dumps(sync_artifact).lower())
                    self.assertNotIn("api_key", json.dumps(sync_artifact).lower())
                    self.assertEqual(compare_results([sync, sync_artifact]), [])

                    handler_service = first
                    handler_artifact_root = artifact_root

                    class ReplayHandler(AgentApiHandler):
                        service = handler_service
                        artifact_root = handler_artifact_root
                        geojson_root = handler_artifact_root / "geojson"

                    server = ThreadingHTTPServer(("127.0.0.1", 0), ReplayHandler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    port = server.server_address[1]
                    status, submitted = _http_json(
                        port,
                        "POST",
                        "/runs/async",
                        {
                            "request": request,
                            "session_id": "m148-e-async-" + domain,
                            "planner": "openai",
                            "backend": backend,
                            "export_artifact": True,
                            "idempotency_key": "m148-e-" + domain,
                        },
                    )
                    self.assertEqual(status, 200, submitted)
                    async_run_id = submitted["run_id"]
                    polled = _wait_for_async(port, async_run_id)
                    self.assertEqual(polled["status"], "COMPLETED")
                    self.assertIn(
                        polled["result_evidence"]["state"],
                        {"success", "degraded"},
                    )
                    if polled["result_evidence"]["state"] == "degraded":
                        self.assertNotEqual(
                            polled["result_evidence"].get("degradation_status"),
                            "none",
                        )
                    self.assertEqual(polled["result_evidence"]["result_type"], expected["expected_result_type"])
                    _assert_safe_evidence(self, polled["result_evidence"])

                    status, async_result = _http_json(port, "GET", "/runs/" + async_run_id)
                    self.assertEqual(status, 200)
                    self.assertEqual(async_result["result"]["model_evidence"]["execution_mode"], "offline_replay")
                    async_artifact_path = Path(async_result["artifact_ref"])
                    status, artifact_bytes = _http_json(
                        port,
                        "GET",
                        "/artifacts/runs/" + async_artifact_path.name,
                    )
                    self.assertEqual(status, 200)
                    async_artifact = json.loads(artifact_bytes.decode("utf-8"))
                    self.assertEqual(async_artifact["result"]["model_evidence"]["execution_mode"], "offline_replay")
                    self.assertIn("async_result_evidence", async_artifact)
                    _assert_safe_evidence(self, async_artifact["async_result_evidence"])
                finally:
                    if server is not None:
                        server.shutdown()
                        server.server_close()
                    if thread is not None:
                        thread.join(timeout=3)
                    first.close()

                second = AgentService(
                    artifact_store=artifacts,
                    state_db_path=str(state_db),
                    runtime_factory=_runtime_factory_for(fixture, calls_after_restart),
                )
                try:
                    recovered = second.get_run(async_run_id, planner="openai", backend=backend)
                    recovered_observation = second.get_async_observability(async_run_id)
                    self.assertEqual(recovered["status"], "COMPLETED")
                    self.assertEqual(
                        recovered["result"]["model_evidence"]["execution_mode"],
                        "offline_replay",
                    )
                    self.assertEqual(
                        recovered_observation["result_evidence"]["state"],
                        polled["result_evidence"]["state"],
                    )
                    self.assertEqual(
                        recovered_observation["result_evidence"],
                        polled["result_evidence"],
                    )
                    self.assertEqual(calls_after_restart, [])
                    _assert_safe_evidence(self, recovered_observation["result_evidence"])

                    handler_service = second
                    handler_artifact_root = artifact_root

                    class RecoveredReplayHandler(AgentApiHandler):
                        service = handler_service
                        artifact_root = handler_artifact_root
                        geojson_root = handler_artifact_root / "geojson"

                    server = ThreadingHTTPServer(("127.0.0.1", 0), RecoveredReplayHandler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    status, http_recovered = _http_json(
                        server.server_address[1],
                        "GET",
                        "/runs/" + async_run_id + "/async",
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(
                        http_recovered["result_evidence"],
                        recovered_observation["result_evidence"],
                    )
                finally:
                    if server is not None:
                        server.shutdown()
                        server.server_close()
                    if thread is not None:
                        thread.join(timeout=3)
                    second.close()

            summaries.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "domain": domain,
                    "backend": backend,
                    "status": "COMPLETED",
                    "model_execution_mode": "offline_replay",
                    "model_calls_before_restart": len(calls_before_restart),
                    "model_calls_after_restart": len(calls_after_restart),
                }
            )

        print(
            json.dumps(
                {
                    "harness": "m148-docker-offline-replay-v1",
                    "cases": summaries,
                    "not_executed_external_steps": [
                        "live model/provider request",
                        "production Uvicorn endpoint with recorded-model injection",
                        "browser/Console rendering",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
