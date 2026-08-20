import argparse
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agent.api_contract import (
    async_run_kwargs,
    cancel_kwargs,
    comparison_kwargs,
    constrained_comparison_kwargs,
    error_response,
    error_status,
    region_comparison_kwargs,
    retry_kwargs,
    preview_kwargs,
    run_kwargs,
    workflow_action_result,
)
from agent.environment_status import environment_status
from agent.domain_registry import domain_registry
from agent.service import AgentService
from agent.runtime_capabilities import runtime_capability_snapshot
from agent.release_evidence import release_evidence_snapshot
from agent.workflow_templates import (
    WorkflowTemplateError,
    workflow_template_catalog,
)


_legacy_runtime_capability_snapshot = runtime_capability_snapshot


def runtime_capability_snapshot(max_files: int = 10) -> dict:
    """Compatibility function retained for isolated runtime snapshot tests."""
    return _legacy_runtime_capability_snapshot(max_files=max_files)


class AgentApiHandler(BaseHTTPRequestHandler):
    service = AgentService()
    service.start_reaper()
    artifact_root = Path("outputs/runs")
    geojson_root = Path("outputs/geojson")
    web_root = Path(__file__).parent / "web"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            payload = {"status": "ok"}
            payload.update(environment_status())
            self._write_json(200, payload)
            return
        if parsed.path == "/capabilities":
            query = parse_qs(parsed.query)
            planner = query.get("planner", ["rule"])[0]
            backend = query.get("backend", ["memory"])[0]
            if self.service is None:
                self._write_json(503, {"error": "service unavailable"})
            else:
                self._write_json(200, self.service.capabilities(planner=planner, backend=backend))
            return
        if parsed.path == "/domains":
            self._write_json(200, domain_registry().catalog())
            return
        if parsed.path == "/actions":
            query = parse_qs(parsed.query)
            planner = query.get("planner", ["rule"])[0]
            backend = query.get("backend", ["memory"])[0]
            if self.service is None:
                self._write_json(503, {"error": "service unavailable"})
            else:
                self._write_json(200, self.service.actions(planner=planner, backend=backend))
            return
        if parsed.path.startswith("/action-executions/"):
            execution_id = parsed.path[len("/action-executions/") :].strip("/")
            if not execution_id:
                self._write_json(404, {"error": "not found"})
                return
            try:
                result = self.service.get_action_execution(execution_id)
            except ValueError as exc:
                self._write_json(404, error_response(exc, not_found=True))
            else:
                self._write_json(200, result)
            return
        if parsed.path == "/action-executions":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", [20])[0])
                self._write_json(200, self.service.list_action_executions(limit=limit))
            except ValueError as exc:
                self._write_json(400, error_response(exc))
            return
        if parsed.path == "/workflows":
            self._write_json(200, {"templates": workflow_template_catalog()})
            return
        if parsed.path.startswith("/workflows/"):
            self._write_json(404, {"error": "not found"})
            return
        if parsed.path == "/capabilities/runtime":
            query = parse_qs(parsed.query)
            try:
                max_files = int(query.get("max_files", [10])[0])
                if max_files < 1 or max_files > 10:
                    raise ValueError("max_files must be between 1 and 10")
                if self.service is None:
                    snapshot = runtime_capability_snapshot(max_files=max_files)
                else:
                    snapshot = self.service.runtime_capabilities(
                        max_files=max_files,
                        backend="local",
                    )
                self._write_json(200, snapshot)
            except ValueError as exc:
                self._write_json(400, error_response(exc))
            return
        if parsed.path == "/release-evidence":
            query = parse_qs(parsed.query)
            try:
                max_files = int(query.get("max_files", [10])[0])
                if max_files < 1 or max_files > 10:
                    raise ValueError("max_files must be between 1 and 10")
                if self.service is None:
                    evidence = release_evidence_snapshot(max_files=max_files)
                else:
                    evidence = self.service.release_evidence(
                        max_files=max_files,
                        planner=query.get("planner", ["rule"])[0],
                        backend=query.get("backend", ["local"])[0],
                    )
                self._write_json(200, evidence)
            except ValueError as exc:
                self._write_json(400, error_response(exc))
            return
        if parsed.path.startswith("/runs/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[1] and parts[2] in ("observability", "async"):
                try:
                    result = self.service.get_async_observability(parts[1])
                except ValueError as exc:
                    self._write_json(404, error_response(exc, not_found=True))
                else:
                    self._write_json(200, result)
                return
            if len(parts) == 2 and parts[1]:
                query = parse_qs(parsed.query)
                try:
                    result = self.service.get_run(
                        parts[1],
                        planner=query.get("planner", ["rule"])[0],
                        backend=query.get("backend", ["memory"])[0],
                    )
                except ValueError as exc:
                    self._write_json(404, error_response(exc, not_found=True))
                else:
                    self._write_json(200, result)
                return
        if parsed.path == "/runs":
            self._write_json(200, self.service.list_runs())
            return
        if parsed.path.startswith("/sessions/") and parsed.path.endswith("/runs"):
            session_id = parsed.path[len("/sessions/") : -len("/runs")].strip("/")
            if session_id:
                self._write_json(200, self.service.list_session_runs(session_id))
                return
        if parsed.path == "/sessions":
            self._write_json(200, self.service.list_sessions())
            return
        if parsed.path == "/metrics":
            self._write_json(200, self.service.metrics())
            return
        if parsed.path == "/memory":
            query = parse_qs(parsed.query)
            try:
                result = self.service.list_memory(
                    session_id=query.get("session_id", [None])[0],
                    query=query.get("query", [None])[0],
                    limit=int(query.get("limit", ["20"])[0]),
                    global_scope=query.get("global", ["0"])[0] in ("1", "true", "yes"),
                )
            except ValueError as exc:
                self._write_json(400, error_response(exc))
            else:
                self._write_json(200, result)
            return
        if parsed.path == "/observability/health":
            state = self.service._state.observability
            self._write_json(200, {
                "schema_version": "spatial-agent.observability.v1",
                "enabled": state.enabled,
                "event_count": state.event_count,
            })
            return
        if parsed.path == "/tools/dynamic":
            self._write_json(200, self.service.list_dynamic_tools())
            return
        if parsed.path in ("/", "/index.html"):
            self._write_file(self.web_root / "index.html", "text/html")
            return
        artifact = self._artifact_file(parsed.path)
        if artifact is not None:
            path, content_type = artifact
            if not path.exists() or not path.is_file():
                self._write_json(404, {"error": "artifact not found"})
                return
            self._write_file(path, content_type)
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        is_retry = parsed.path.startswith("/runs/") and parsed.path.endswith("/retry")
        is_cancel = parsed.path.startswith("/runs/") and parsed.path.endswith("/cancel")
        is_preview = parsed.path == "/runs/preview"
        is_async_run = parsed.path == "/runs/async"
        is_comparison = parsed.path == "/comparisons"
        is_region_comparison = parsed.path == "/region-comparisons"
        is_constrained_comparison = parsed.path == "/constrained-comparisons"
        is_domain_action = parsed.path.startswith("/actions/")
        is_tool_register = parsed.path == "/tools"
        is_session_create = parsed.path == "/sessions"
        is_session_clear = parsed.path.startswith("/sessions/") and parsed.path.endswith("/clear")
        workflow_action = None
        workflow_template_id = None
        workflow_parts = parsed.path.strip("/").split("/")
        if len(workflow_parts) == 3 and workflow_parts[0] == "workflows" and workflow_parts[2] in ("validate", "revise"):
            workflow_template_id = workflow_parts[1]
            workflow_action = workflow_parts[2]
        if parsed.path != "/runs" and not is_preview and not is_async_run and not is_retry and not is_cancel and not is_comparison and not is_region_comparison and not is_constrained_comparison and not is_domain_action and not is_tool_register and not is_session_create and not is_session_clear and workflow_action is None:
            self._write_json(404, {"error": "not found"})
            return
        try:
            payload = self._read_json()
            if workflow_action is not None:
                result = workflow_action_result(workflow_template_id, workflow_action, payload)
            elif is_tool_register:
                result = self.service.register_tool(
                    name=payload.get("name", ""),
                    definition=payload.get("definition", {}),
                    handler=AgentService.estimate_area_handler,
                )
            elif is_preview:
                result = self.service.preview(**preview_kwargs(payload))
            elif is_async_run:
                result = self.service.run_async(**async_run_kwargs(payload))
            elif is_session_create:
                result = self.service.create_session()
            elif is_session_clear:
                session_id = parsed.path[len("/sessions/") : -len("/clear")].strip("/")
                result = self.service.clear_session(session_id)
            elif is_comparison:
                result = self.service.compare_buildability(**comparison_kwargs(payload))
            elif is_region_comparison:
                result = self.service.compare_buildability_regions(**region_comparison_kwargs(payload))
            elif is_constrained_comparison:
                result = self.service.compare_constrained_buildability(**constrained_comparison_kwargs(payload))
            elif is_domain_action:
                action_id = parsed.path[len("/actions/") :].strip("/")
                if not action_id:
                    self._write_json(404, {"error": "not found"})
                    return
                result = self.service.execute_action(
                    action_id,
                    payload,
                    planner=payload.get("planner", "rule"),
                    backend=payload.get("backend", "local"),
                    idempotency_key=payload.get("idempotency_key"),
                )
            elif is_retry or is_cancel:
                parts = parsed.path.strip("/").split("/")
                expected_action = "retry" if is_retry else "cancel"
                if len(parts) != 3 or not parts[1] or parts[2] != expected_action:
                    self._write_json(404, {"error": "not found"})
                    return
                if is_cancel:
                    result = self.service.cancel(run_id=parts[1], **cancel_kwargs(payload))
                else:
                    result = self.service.retry(run_id=parts[1], **retry_kwargs(payload))
            else:
                result = self.service.run(**run_kwargs(payload))
        except (ValueError, WorkflowTemplateError) as exc:
            self._write_json(error_status(exc), error_response(exc))
            return
        except Exception as exc:
            self._write_json(error_status(exc), error_response(exc))
            return
        self._write_json(200, result)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/sessions/"):
            self._write_json(404, {"error": "not found"})
            return
        try:
            session_id = parsed.path[len("/sessions/") :].strip("/")
            result = self.service.delete_session(session_id)
        except ValueError as exc:
            self._write_json(400, error_response(exc))
            return
        except Exception as exc:
            self._write_json(500, error_response(exc))
            return
        self._write_json(200, result)

    def log_message(self, format, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _artifact_file(self, path):
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "artifacts":
            return None
        roots = {"runs": (self.artifact_root, "application/json"), "actions": (self.artifact_root, "application/json"), "geojson": (self.geojson_root, "application/geo+json")}
        if parts[1] not in roots or Path(parts[2]).name != parts[2]:
            return None
        root, content_type = roots[parts[1]]
        explicit_artifact_root = "artifact_root" in type(self).__dict__
        if parts[1] in ("runs", "actions") and self.service is not None and not explicit_artifact_root:
            store_root = getattr(getattr(self.service, "_artifact_store", None), "_root", None)
            if store_root is not None:
                root = Path(store_root)
        candidate = (root / parts[2]).resolve()
        if root.resolve() not in candidate.parents:
            return None
        expected_suffix = ".geojson" if parts[1] == "geojson" else ".json"
        if candidate.suffix != expected_suffix:
            return None
        if parts[1] == "actions" and not candidate.name.startswith("action-"):
            return None
        return candidate, content_type

    def _write_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args():
    parser = argparse.ArgumentParser(description="Serve the Spatial Agent HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    return parser.parse_args()


def main():
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AgentApiHandler)
    print(f"Spatial Agent API listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
