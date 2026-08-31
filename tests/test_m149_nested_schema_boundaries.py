"""M149-D nested schema rejection/degradation contract matrix.

This is an intentionally small negative matrix for the public HTTP, async,
and artifact boundaries.  It does not exercise the historical full suite and
does not call a model or a GIS backend.

The contract permits either of two safe outcomes for an unknown nested
schema: reject the record, or return a bounded unavailable/degraded fallback.
It never permits the unknown value to be interpreted as the current schema or
to cross a Domain boundary.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from serve_api import AgentApiHandler


KNOWN_RESULT = "spatial-agent.result-envelope.v1"
KNOWN_WORKSPACE = "spatial-agent.workspace.v1"
KNOWN_VIEWS = "spatial-agent.views.v1"
KNOWN_VIEW = "spatial-agent.view.v1"
KNOWN_ARTIFACT = "spatial-agent.run-artifact.v1"
KNOWN_ASYNC = "spatial-agent.async-result-evidence.v1"

def _text_runtime_factory(planner: str, backend: str, **kwargs: Any):
    return build_text_runtime(planner, backend, **kwargs)


def _request(port: int, path: str):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    raw = response.read()
    status = response.status
    content_type = response.getheader("Content-Type", "")
    connection.close()
    if "json" in content_type.lower():
        return status, json.loads(raw.decode("utf-8"))
    return status, raw


def _base_artifact(run_id: str, domain_id: str = "text") -> dict[str, Any]:
    """Return a complete bounded artifact without invoking a runtime."""

    result = {
        "schema_version": KNOWN_RESULT,
        "type": "text_summary_result",
        "summary": "脱敏结果",
        "workspace": {
            "schema_version": KNOWN_WORKSPACE,
            "panels": ["generic"],
            "view_specs": [
                {
                    "id": "generic",
                    "renderer": "generic",
                    "schema_version": KNOWN_VIEW,
                }
            ],
        },
        "views": {
            "schema_version": KNOWN_VIEWS,
            "panels": {
                "generic": {
                    "schema_version": KNOWN_VIEW,
                    "kind": "text_summary",
                    "state": "available",
                    "artifact_available": True,
                }
            },
        },
    }
    async_evidence = {
        "schema_version": KNOWN_ASYNC,
        "available": True,
        "state": "success",
        "status": "COMPLETED",
        "result_type": "text_summary_result",
        "degradation_status": "none",
        "workspace": {
            "schema_version": KNOWN_WORKSPACE,
            "panels": ["generic"],
            "view_specs": [
                {
                    "id": "generic",
                    "renderer": "generic",
                    "schema_version": KNOWN_VIEW,
                }
            ],
        },
        "views": {
            "schema_version": KNOWN_VIEWS,
            "panels": {
                "generic": {
                    "schema_version": KNOWN_VIEW,
                    "kind": "text_summary",
                    "state": "available",
                    "artifact_available": True,
                }
            },
        },
        "artifact": {"available": True, "ref": run_id + ".json"},
    }
    return {
        "artifact_schema_version": KNOWN_ARTIFACT,
        "run_id": run_id,
        "status": "COMPLETED",
        "domain_id": domain_id,
        "request": "脱敏嵌套 schema 负向样例",
        "result_type": "text_summary_result",
        "answer": "脱敏结果",
        "steps": [],
        "result": result,
        "async_requested": True,
        "async_result_evidence": async_evidence,
    }


def _mutators() -> tuple[tuple[str, Callable[[dict[str, Any], str], None]], ...]:
    """Return one mutation for every nested schema seam in M149 scope."""

    def result_envelope(artifact: dict[str, Any], value: str) -> None:
        artifact["result"]["schema_version"] = value

    def workspace(artifact: dict[str, Any], value: str) -> None:
        artifact["result"]["workspace"]["schema_version"] = value
        artifact["async_result_evidence"]["workspace"]["schema_version"] = value

    def views(artifact: dict[str, Any], value: str) -> None:
        artifact["result"]["views"]["schema_version"] = value
        artifact["async_result_evidence"]["views"]["schema_version"] = value

    def view_panel(artifact: dict[str, Any], value: str) -> None:
        artifact["result"]["views"]["panels"]["generic"]["schema_version"] = value
        artifact["async_result_evidence"]["views"]["panels"]["generic"][
            "schema_version"
        ] = value

    return (
        ("result", result_envelope),
        ("workspace", workspace),
        ("views", views),
        ("view_panel", view_panel),
    )


def _write_artifact(
    root: Path,
    run_id: str,
    *,
    domain_id: str = "text",
    mutate: Callable[[dict[str, Any], str], None] | None = None,
) -> str:
    payload = _base_artifact(run_id, domain_id=domain_id)
    marker = "spatial-agent.m149-unknown-" + run_id
    if mutate is not None:
        mutate(payload, marker)
    path = root / (run_id + ".json")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return marker


def _assert_rejected_or_sanitized(
    testcase: unittest.TestCase,
    payload: Any,
    marker: str,
    *,
    require_degraded: bool = True,
) -> None:
    """Accept only explicit rejection or a bounded known-schema fallback."""

    if payload is None:
        return
    testcase.assertIsInstance(payload, Mapping)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    testcase.assertNotIn(marker, encoded)
    result = payload.get("result") if isinstance(payload, Mapping) else None
    if isinstance(result, Mapping):
        testcase.assertEqual(result.get("schema_version"), KNOWN_RESULT)
        workspace = result.get("workspace")
        views = result.get("views")
        if isinstance(workspace, Mapping) and workspace.get("schema_version"):
            testcase.assertEqual(workspace["schema_version"], KNOWN_WORKSPACE)
        if isinstance(views, Mapping) and views.get("schema_version"):
            testcase.assertEqual(views["schema_version"], KNOWN_VIEWS)
        panels = views.get("panels") if isinstance(views, Mapping) else {}
        panel = panels.get("generic") if isinstance(panels, Mapping) else None
        if isinstance(panel, Mapping) and panel.get("schema_version"):
            testcase.assertEqual(panel["schema_version"], KNOWN_VIEW)
        if require_degraded:
            degradation = result.get("degradation")
            degradation_status = (
                degradation.get("status") if isinstance(degradation, Mapping) else None
            )
            unavailable_panel = isinstance(panel, Mapping) and (
                panel.get("state") == "unavailable"
                or panel.get("kind") == "unavailable"
            )
            testcase.assertTrue(
                degradation_status in {"degraded", "unavailable"} or unavailable_panel,
                "accepted nested schema without an explicit degraded/unavailable marker",
            )


class M149NestedSchemaBoundaryTests(unittest.TestCase):
    def test_artifact_store_rejects_or_sanitizes_unknown_nested_schema(self):
        with tempfile.TemporaryDirectory(prefix="m149-schema-") as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            for name, mutate in _mutators():
                with self.subTest(schema=name):
                    run_id = "m149-artifact-" + name
                    marker = _write_artifact(root, run_id, mutate=mutate)
                    loaded = store.read_run(run_id, domain_id="text")
                    _assert_rejected_or_sanitized(self, loaded, marker)

    def test_http_run_and_async_reject_or_degrade_without_domain_fallback(self):
        with tempfile.TemporaryDirectory(prefix="m149-http-") as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            handler_service = service

            class TextHandler(AgentApiHandler):
                service = handler_service
                artifact_root = root
                geojson_root = root / "geojson"

            server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                for name, mutate in _mutators():
                    with self.subTest(schema=name, endpoint="run"):
                        run_id = "m149-http-" + name
                        marker = _write_artifact(root, run_id, mutate=mutate)
                        status, payload = _request(port, "/runs/" + run_id)
                        self.assertIn(status, {404, 200})
                        if status == 200:
                            _assert_rejected_or_sanitized(self, payload, marker)

                # The async endpoint exposes the async evidence projection,
                # so a malformed result-envelope-only field is not part of
                # this endpoint's contract.  The workspace/views/panel cases
                # are deliberately applied to both persisted projections.
                for name, mutate in _mutators()[1:]:
                    with self.subTest(schema=name, endpoint="async"):
                        run_id = "m149-http-async-" + name
                        marker = _write_artifact(root, run_id, mutate=mutate)
                        status, payload = _request(port, "/runs/" + run_id + "/async")
                        self.assertIn(status, {404, 200})
                        if status == 200:
                            self.assertIsInstance(payload, Mapping)
                            evidence = payload.get("result_evidence")
                            self.assertIsInstance(evidence, Mapping)
                            self.assertNotIn(
                                marker,
                                json.dumps(evidence, ensure_ascii=False),
                            )
                            self.assertEqual(evidence.get("state"), "unavailable")
                            self.assertIn(
                                evidence.get("reason_code"),
                                {
                                    "async_result_evidence_unknown_schema",
                                    "nested_schema_unknown",
                                    "nested_schema_unknown_version",
                                    "result_contract_unknown_schema",
                                },
                            )
                            self.assertEqual(
                                evidence.get("schema_version"), KNOWN_ASYNC
                            )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

    def test_artifact_http_boundary_rejects_unknown_nested_schema_and_cross_domain(self):
        with tempfile.TemporaryDirectory(prefix="m149-artifact-http-") as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            service = AgentService(
                artifact_store=store,
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            handler_service = service

            class TextHandler(AgentApiHandler):
                service = handler_service
                artifact_root = root
                geojson_root = root / "geojson"

            server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                for name, mutate in _mutators():
                    with self.subTest(schema=name):
                        run_id = "m149-download-" + name
                        _write_artifact(root, run_id, mutate=mutate)
                        status, _ = _request(
                            port,
                            "/artifacts/runs/" + run_id + ".json",
                        )
                        self.assertEqual(status, 404)

                # A malformed GIS artifact must not become visible through a
                # Text service merely because its nested schema is rejected.
                foreign_id = "m149-foreign-gis"
                _write_artifact(
                    root,
                    foreign_id,
                    domain_id="gis",
                    mutate=_mutators()[0][1],
                )
                for endpoint in (
                    "/runs/" + foreign_id,
                    "/runs/" + foreign_id + "/async",
                    "/artifacts/runs/" + foreign_id + ".json",
                ):
                    with self.subTest(endpoint=endpoint, cross_domain=True):
                        status, _ = _request(port, endpoint)
                        self.assertEqual(status, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

    def test_production_artifact_boundary_rejects_unknown_nested_schema(self):
        try:
            import production_api
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("FastAPI is not installed in this environment")
            raise

        with tempfile.TemporaryDirectory(prefix="m149-production-") as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            run_id = "m149-production-views"
            _write_artifact(root, run_id, mutate=_mutators()[2][1])
            original_service = production_api.service
            original_root = production_api.ARTIFACT_ROOT
            try:
                production_api.service = AgentService(
                    artifact_store=store,
                    runtime_factory=_text_runtime_factory, domain_id="text",
                )
                production_api.ARTIFACT_ROOT = root
                with self.assertRaises(production_api.HTTPException) as error:
                    production_api.run_artifact(run_id + ".json")
            finally:
                production_api.service.close()
                production_api.service = original_service
                production_api.ARTIFACT_ROOT = original_root
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
