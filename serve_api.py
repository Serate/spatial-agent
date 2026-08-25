import argparse
import atexit
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent.environment_status import environment_status
from agent.application.http_transport import (
    decode_json_body,
    encode_json_body,
    error_projection,
    load_artifact_json,
    parse_request_target as urlparse,
    query_params as parse_qs,
    safe_artifact_path,
)
from agent.domain_http import assert_domain_payload, parse_domain_path
from agent.domain_registry import resolve_domain_id
from agent.domain_runtime_host import DomainRuntimeHost
from agent.domain_routing_entry import (
    DomainRoutingApplication,
    DomainRoutingApplicationError,
    routing_state_from_environment,
)
from agent.service import AgentService
from agent.application.http import HTTPApplication
from agent.web_assets import WEB_ASSETS, console_asset, console_index, console_root
from agent.runtime_capabilities import runtime_capability_snapshot
from agent.release_evidence import release_evidence_snapshot
from agent.workflow_templates import (
    WorkflowTemplateError,
)


_legacy_runtime_capability_snapshot = runtime_capability_snapshot


domain_host = DomainRuntimeHost()
domain_host.start()
legacy_service = domain_host.service(resolve_domain_id())
domain_routing = DomainRoutingApplication(
    domain_host,
    state=routing_state_from_environment(),
)


def runtime_capability_snapshot(max_files: int = 10) -> dict:
    """Compatibility function retained for isolated runtime snapshot tests."""
    return _legacy_runtime_capability_snapshot(max_files=max_files)


class AgentApiHandler(BaseHTTPRequestHandler):
    host = domain_host
    service = legacy_service
    routing = domain_routing
    artifact_root = Path("outputs/runs")
    geojson_root = Path("outputs/geojson")
    web_root = console_root()

    def _http_application(self) -> HTTPApplication:
        return HTTPApplication(
            self.service,
            routing=self.routing,
            action_handler=AgentService.estimate_area_handler,
            on_session_clear=lambda session_id: self.routing.forget_session(
                session_id, keep_binding=True
            ),
            on_session_delete=self.routing.forget_session,
        )

    def do_GET(self):
        try:
            parsed, selection = self._domain_request(urlparse(self.path))
        except Exception as exc:
            self._write_error(exc)
            return
        if selection is not None and parsed.path in (
            "/health",
            "/",
            "/index.html",
            "/observability/health",
            "/tools/dynamic",
        ):
            self._write_json(404, {"error": "not found", "error_code": "not_found"})
            return
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
                self._write_json(
                    200,
                    self._http_application().read(
                        "capabilities", {"planner": planner, "backend": backend}
                    ),
                )
            return
        if parsed.path == "/domains":
            self._write_json(200, self.host.catalog())
            return
        if selection is None and parsed.path == "/domain-routing/catalog":
            self._write_json(200, self._http_application().read("routing_catalog"))
            return
        if selection is None and parsed.path == "/domain-routing/metrics":
            self._write_json(200, self._http_application().read("routing_metrics"))
            return
        if parsed.path == "/actions":
            query = parse_qs(parsed.query)
            planner = query.get("planner", ["rule"])[0]
            backend = query.get("backend", ["memory"])[0]
            if self.service is None:
                self._write_json(503, {"error": "service unavailable"})
            else:
                self._write_json(
                    200,
                    self._http_application().read(
                        "actions", {"planner": planner, "backend": backend}
                    ),
                )
            return
        if parsed.path.startswith("/action-executions/"):
            execution_id = parsed.path[len("/action-executions/") :].strip("/")
            if not execution_id:
                self._write_json(404, {"error": "not found"})
                return
            try:
                result = self._http_application().read(
                    "action_execution", resource_id=execution_id
                )
            except ValueError as exc:
                self._write_error(exc, not_found=True)
            else:
                self._write_json(200, result)
            return
        if parsed.path == "/action-executions":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", [20])[0])
                self._write_json(
                    200,
                    self._http_application().read(
                        "action_executions", {"limit": limit}
                    ),
                )
            except ValueError as exc:
                self._write_error(exc)
            return
        if parsed.path == "/workflows":
            query = parse_qs(parsed.query)
            planner = query.get("planner", ["rule"])[0]
            backend = query.get("backend", ["memory"])[0]
            self._write_json(
                200,
                self._http_application().read(
                    "workflow", {"planner": planner, "backend": backend}
                ),
            )
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
                    snapshot = self._http_application().read(
                        "runtime_capabilities",
                        {"max_files": max_files, "backend": "local"},
                    )
                self._write_json(200, snapshot)
            except ValueError as exc:
                self._write_error(exc)
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
                    evidence = self._http_application().read(
                        "release_evidence",
                        {
                            "max_files": max_files,
                            "planner": query.get("planner", ["rule"])[0],
                            "backend": query.get("backend", ["local"])[0],
                        },
                    )
                self._write_json(200, evidence)
            except ValueError as exc:
                self._write_error(exc)
            return
        if parsed.path.startswith("/runs/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[1] and parts[2] == "evidence":
                try:
                    result = self._http_application().read(
                        "run_evidence", resource_id=parts[1]
                    )
                except ValueError as exc:
                    self._write_error(exc, not_found=True)
                else:
                    self._write_json(200, result)
                return
            if len(parts) == 3 and parts[1] and parts[2] == "interaction":
                query = parse_qs(parsed.query)
                try:
                    result = self._http_application().read(
                        "run_interaction",
                        {
                            "planner": query.get("planner", ["rule"])[0],
                            "backend": query.get("backend", ["memory"])[0],
                        },
                        resource_id=parts[1],
                    )
                except ValueError as exc:
                    self._write_error(exc, not_found=True)
                else:
                    self._write_json(200, result)
                return
            if len(parts) == 3 and parts[1] and parts[2] in ("observability", "async"):
                try:
                    result = self._http_application().read(
                        "async_observability", resource_id=parts[1]
                    )
                except ValueError as exc:
                    self._write_error(exc, not_found=True)
                else:
                    self._write_json(200, result)
                return
            if len(parts) == 2 and parts[1]:
                query = parse_qs(parsed.query)
                try:
                    result = self._http_application().read(
                        "run",
                        {
                            "planner": query.get("planner", ["rule"])[0],
                            "backend": query.get("backend", ["memory"])[0],
                        },
                        resource_id=parts[1],
                    )
                except ValueError as exc:
                    self._write_error(exc, not_found=True)
                else:
                    self._write_json(200, result)
                return
        if parsed.path.startswith("/decisions/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 2 and parts[1]:
                try:
                    result = self._http_application().read(
                        "decision", resource_id=parts[1]
                    )
                except ValueError as exc:
                    self._write_error(exc, not_found=True)
                else:
                    self._write_json(200, result)
                return
        if parsed.path == "/runs":
            query = parse_qs(parsed.query)
            self._write_json(
                200,
                self._http_application().read(
                    "runs", {"limit": int(query.get("limit", [20])[0])}
                ),
            )
            return
        if parsed.path.startswith("/sessions/") and parsed.path.endswith("/runs"):
            session_id = parsed.path[len("/sessions/") : -len("/runs")].strip("/")
            if session_id:
                query = parse_qs(parsed.query)
                self._write_json(
                    200,
                    self._http_application().read(
                        "session_runs",
                        {"limit": int(query.get("limit", [20])[0])},
                        resource_id=session_id,
                    ),
                )
                return
        if parsed.path == "/sessions":
            query = parse_qs(parsed.query)
            self._write_json(
                200,
                self._http_application().read(
                    "sessions", {"limit": int(query.get("limit", [50])[0])}
                ),
            )
            return
        if parsed.path == "/metrics":
            self._write_json(200, self._http_application().read("metrics"))
            return
        if parsed.path == "/memory":
            query = parse_qs(parsed.query)
            try:
                result = self._http_application().read(
                    "memory",
                    {
                        "session_id": query.get("session_id", [None])[0],
                        "query": query.get("query", [None])[0],
                        "limit": int(query.get("limit", ["20"])[0]),
                        "global_scope": query.get("global", ["0"])[0]
                        in ("1", "true", "yes"),
                    },
                )
            except ValueError as exc:
                self._write_error(exc)
            else:
                self._write_json(200, result)
            return
        if parsed.path == "/observability/health":
            self._write_json(
                200, self._http_application().read("observability_health")
            )
            return
        if parsed.path == "/tools/dynamic":
            self._write_json(200, self._http_application().read("dynamic_tools"))
            return
        if parsed.path in ("/", "/index.html"):
            self._write_file(console_index(), "text/html")
            return
        if parsed.path == "/styles.css":
            asset = console_asset("styles.css")
            if asset is None:
                self._write_json(404, {"error": "web asset not found"})
            else:
                self._write_file(asset, "text/css")
            return
        if parsed.path.startswith("/console_") and parsed.path.endswith(".js"):
            name = parsed.path.strip("/")
            if name in WEB_ASSETS:
                asset = console_asset(name)
                if asset is None:
                    self._write_json(404, {"error": "web asset not found"})
                    return
                self._write_file(asset, "application/javascript")
                return
            self._write_json(404, {"error": "web asset not found"})
            return
        if parsed.path.startswith("/artifacts/runs/") and parsed.path.endswith("/evidence"):
            name = parsed.path[len("/artifacts/runs/") : -len("/evidence")].strip("/")
            artifact = self._artifact_file("/artifacts/runs/" + name)
            if artifact is None:
                self._write_json(404, {"error": "artifact not found"})
                return
            path, _content_type = artifact
            try:
                payload = load_artifact_json(path)
            except (OSError, ValueError):
                self._write_json(404, {"error": "artifact not found"})
                return
            self._write_json(
                200,
                self._http_application().read(
                    "artifact_evidence",
                    {"artifact_payload": payload, "artifact_ref": path.name},
                ),
            )
            return
        if parsed.path.startswith("/artifacts/runs/") and parsed.path.endswith("/manifest"):
            name = parsed.path[len("/artifacts/runs/") : -len("/manifest")].strip("/")
            artifact = self._artifact_file("/artifacts/runs/" + name)
            if artifact is None:
                self._write_json(404, {"error": "artifact not found"})
                return
            path, _content_type = artifact
            try:
                payload = load_artifact_json(path)
            except (OSError, ValueError):
                self._write_json(404, {"error": "artifact not found"})
                return
            self._write_json(
                200,
                self._http_application().read(
                    "artifact_manifest",
                    {"artifact_payload": payload, "artifact_ref": path.name},
                ),
            )
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
        try:
            parsed, selection = self._domain_request(urlparse(self.path))
        except Exception as exc:
            self._write_error(exc)
            return
        is_retry = parsed.path.startswith("/runs/") and parsed.path.endswith("/retry")
        is_cancel = parsed.path.startswith("/runs/") and parsed.path.endswith("/cancel")
        is_preview = parsed.path == "/runs/preview"
        is_async_run = parsed.path == "/runs/async"
        is_decision_resolve = (
            parsed.path.startswith("/decisions/")
            and parsed.path.endswith("/resolve")
        )
        is_interaction = (
            parsed.path.startswith("/runs/")
            and parsed.path.endswith("/interaction")
        )
        is_comparison = selection is None and parsed.path == "/comparisons"
        is_region_comparison = selection is None and parsed.path == "/region-comparisons"
        is_constrained_comparison = selection is None and parsed.path == "/constrained-comparisons"
        is_domain_action = parsed.path.startswith("/actions/")
        is_tool_register = selection is None and parsed.path == "/tools"
        is_session_create = parsed.path == "/sessions"
        is_session_clear = parsed.path.startswith("/sessions/") and parsed.path.endswith("/clear")
        is_domain_select = selection is None and parsed.path == "/domain-routing/select"
        is_auto_run = selection is None and parsed.path == "/runs/auto"
        routing_override_id = None
        routing_clear_session_id = None
        routing_parts = parsed.path.strip("/").split("/")
        if (
            selection is None
            and len(routing_parts) == 4
            and routing_parts[0] == "domain-routing"
            and routing_parts[1] == "decisions"
            and routing_parts[2]
            and routing_parts[3] == "select"
        ):
            routing_override_id = routing_parts[2]
        if (
            selection is None
            and len(routing_parts) == 4
            and routing_parts[0] == "domain-routing"
            and routing_parts[1] == "sessions"
            and routing_parts[2]
            and routing_parts[3] == "clear"
        ):
            routing_clear_session_id = routing_parts[2]
        workflow_action = None
        workflow_template_id = None
        workflow_parts = parsed.path.strip("/").split("/")
        if len(workflow_parts) == 3 and workflow_parts[0] == "workflows" and workflow_parts[2] in ("validate", "revise"):
            workflow_template_id = workflow_parts[1]
            workflow_action = workflow_parts[2]
        if parsed.path != "/runs" and not is_preview and not is_async_run and not is_retry and not is_cancel and not is_interaction and not is_comparison and not is_region_comparison and not is_constrained_comparison and not is_domain_action and not is_tool_register and not is_session_create and not is_session_clear and not is_decision_resolve and not is_domain_select and not is_auto_run and routing_override_id is None and routing_clear_session_id is None and workflow_action is None:
            self._write_json(404, {"error": "not found"})
            return
        try:
            payload = self._read_json()
            if selection is not None:
                assert_domain_payload(selection, payload)
            if is_domain_select:
                result = self._http_application().execute("domain_select", payload)
            elif routing_override_id is not None:
                result = self._http_application().execute(
                    "domain_routing_override", payload, run_id=routing_override_id
                )
            elif routing_clear_session_id is not None:
                result = self._http_application().execute(
                    "domain_routing_clear", {}, run_id=routing_clear_session_id
                )
            elif is_auto_run:
                result = self._http_application().execute("run_auto", payload)
            elif workflow_action is not None:
                result = self._http_application().execute(
                    "workflow_" + workflow_action,
                    payload,
                    template_id=workflow_template_id,
                )
            elif is_tool_register:
                result = self._http_application().execute("tool_register", payload)
            elif is_preview:
                result = self._http_application().execute("preview", payload)
            elif is_async_run:
                result = self._http_application().execute("run_async", payload)
            elif is_decision_resolve:
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 3 or not parts[1] or parts[2] != "resolve":
                    self._write_json(404, {"error": "not found"})
                    return
                result = self._http_application().execute(
                    "resolve_decision", payload, run_id=parts[1]
                )
            elif is_interaction:
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 3 or not parts[1] or parts[2] != "interaction":
                    self._write_json(404, {"error": "not found"})
                    return
                result = self._http_application().execute(
                    "interaction", payload, run_id=parts[1]
                )
            elif is_session_create:
                result = self._http_application().execute("session_create", payload)
            elif is_session_clear:
                session_id = parsed.path[len("/sessions/") : -len("/clear")].strip("/")
                result = self._http_application().execute(
                    "session_clear", payload, run_id=session_id
                )
            elif is_comparison:
                result = self._http_application().execute("compare", payload)
            elif is_region_comparison:
                result = self._http_application().execute("region_compare", payload)
            elif is_constrained_comparison:
                result = self._http_application().execute(
                    "constrained_compare", payload
                )
            elif is_domain_action:
                action_id = parsed.path[len("/actions/") :].strip("/")
                if not action_id:
                    self._write_json(404, {"error": "not found"})
                    return
                result = self._http_application().execute(
                    "domain_action", payload, run_id=action_id
                )
            elif is_retry or is_cancel:
                parts = parsed.path.strip("/").split("/")
                expected_action = "retry" if is_retry else "cancel"
                if len(parts) != 3 or not parts[1] or parts[2] != expected_action:
                    self._write_json(404, {"error": "not found"})
                    return
                if is_cancel:
                    result = self._http_application().execute(
                        "cancel", payload, run_id=parts[1]
                    )
                else:
                    result = self._http_application().execute(
                        "retry", payload, run_id=parts[1]
                    )
            else:
                result = self._http_application().execute("run", payload)
        except DomainRoutingApplicationError as exc:
            self._write_error(
                exc,
                not_found=exc.code == "domain_routing_decision_not_found",
            )
            return
        except (ValueError, WorkflowTemplateError) as exc:
            self._write_error(exc)
            return
        except Exception as exc:
            self._write_error(exc)
            return
        self._write_json(200, result)

    def do_DELETE(self):
        try:
            parsed, _selection = self._domain_request(urlparse(self.path))
        except Exception as exc:
            self._write_error(exc)
            return
        if not parsed.path.startswith("/sessions/"):
            self._write_json(404, {"error": "not found"})
            return
        try:
            session_id = parsed.path[len("/sessions/") :].strip("/")
            result = self._http_application().execute(
                "session_delete", {}, run_id=session_id
            )
        except ValueError as exc:
            self._write_error(exc)
            return
        except Exception as exc:
            self._write_error(exc)
            return
        self._write_json(200, result)

    def log_message(self, format, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return decode_json_body(raw)

    def _domain_request(self, parsed):
        """Bind this handler request to the service selected by its URL."""
        self.service = type(self).service
        self._request_domain_id = getattr(self.service, "_resolved_domain_id", "gis")
        scope = parse_domain_path(parsed.path)
        if scope is None:
            return parsed, None
        host = getattr(type(self), "host", None)
        if host is None:
            raise ValueError("multi-domain host is unavailable")
        selection = host.select(scope.domain_id)
        self.service = host.service(selection)
        self._request_domain_id = selection.domain_id
        return parsed._replace(path=scope.path), selection

    def _write_json(self, status_code, payload):
        body = encode_json_body(payload)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_error(
        self,
        exc: Exception,
        *,
        not_found: bool = False,
        service_unavailable: bool = False,
    ) -> None:
        status, payload = error_projection(
            exc,
            not_found=not_found,
            service_unavailable=service_unavailable,
        )
        self._write_json(status, payload)

    def _artifact_file(self, path):
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "artifacts":
            return None
        roots = {
            "runs": (self.artifact_root, "application/json", "run"),
            "actions": (self.artifact_root, "application/json", "action"),
            "geojson": (self.geojson_root, "application/geo+json", "geojson"),
        }
        if parts[1] not in roots or Path(parts[2]).name != parts[2]:
            return None
        root, content_type, kind = roots[parts[1]]
        explicit_artifact_root = "artifact_root" in type(self).__dict__
        if parts[1] in ("runs", "actions") and self.service is not None and not explicit_artifact_root:
            store_root = getattr(getattr(self.service, "_artifact_store", None), "_root", None)
            if store_root is not None:
                root = Path(store_root)
        domain_id = getattr(self, "_request_domain_id", "gis")
        metadata_root = self.artifact_root if parts[1] == "geojson" else None
        suffix = ".geojson" if kind == "geojson" else ".json"
        prefix = "action-" if kind == "action" else ""
        candidate = safe_artifact_path(
            root,
            parts[2],
            suffix,
            prefix,
            domain_id=domain_id,
            metadata_root=metadata_root,
        )
        if candidate is None:
            return None
        return candidate, content_type

    def _write_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _close_default_service() -> None:
    """Release every Domain service owned by the development Host."""
    AgentApiHandler.host.close()


atexit.register(_close_default_service)


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
