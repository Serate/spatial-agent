"""Small standard-library HTTP compatibility adapter.

The product HTTP contract lives in ``HTTPApplication`` and ``http_routes``.
This module only translates ``http.server`` requests into that contract.  It
is intentionally framework-specific and contains no domain or business
dispatch logic.
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from agent.application.http_routes import resolve_route
from agent.application.http_transport import (
    decode_json_body,
    encode_json_body,
    error_projection,
    load_artifact_json,
    parse_request_target,
    query_params,
    safe_artifact_path,
)
from agent.domain_http import assert_domain_payload, parse_domain_path
from agent.domain_routing_entry import DomainRoutingApplicationError
from agent.environment_status import environment_status
from agent.run_events import page_contains_terminal_event, validate_event_cursor, validate_event_limit
from agent.web_assets import WEB_ASSETS, console_asset, console_index, console_root
from agent.workflow_templates import WorkflowTemplateError


class StdlibAgentApiHandler(BaseHTTPRequestHandler):
    """Framework adapter retained for local scripts and legacy callers."""

    host: Any = None
    service: Any = None
    routing: Any = None
    composite_application: Any = None
    composite_planning_application: Any = None
    artifact_root = Path("outputs/runs")
    geojson_root = Path("outputs/geojson")
    web_root = console_root()

    def _http_application(self):
        """Return the semantic application supplied by the entrypoint."""
        raise NotImplementedError("entrypoint must provide _http_application")

    def _legacy_runtime_snapshot(self, max_files: int):
        raise ValueError("runtime capability service is unavailable")

    def _legacy_release_evidence(self, max_files: int):
        raise ValueError("release evidence service is unavailable")

    def do_GET(self):
        try:
            parsed, selection = self._domain_request(parse_request_target(self.path))
        except Exception as exc:
            self._write_error(exc)
            return

        if selection is not None and parsed.path in {
            "/health",
            "/health/live",
            "/",
            "/index.html",
            "/observability/health",
            "/tools/dynamic",
        }:
            self._write_json(404, {"error": "not found"})
            return
        if parsed.path == "/health/live":
            self._write_json(200, {"status": "ok"})
            return
        if parsed.path == "/health":
            self._write_json(200, {"status": "ok", **environment_status()})
            return
        if selection is None and parsed.path == "/domains":
            self._write_json(200, self.host.catalog())
            return
        if selection is None and parsed.path == "/domain-routing/catalog":
            self._write_json(200, self._http_application().read("routing_catalog"))
            return
        if selection is None and parsed.path == "/domain-routing/metrics":
            self._write_json(200, self._http_application().read("routing_metrics"))
            return
        if parsed.path in {"/", "/index.html"}:
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
            if name not in WEB_ASSETS:
                self._write_json(404, {"error": "web asset not found"})
                return
            asset = console_asset(name)
            if asset is None:
                self._write_json(404, {"error": "web asset not found"})
            else:
                self._write_file(asset, "application/javascript")
            return
        if parsed.path.startswith("/artifacts/"):
            if self._serve_artifact(parsed.path):
                return

        route = resolve_route("GET", parsed.path)
        if route is not None:
            if route.action == "run_events":
                self._serve_events(route.resource_id, parsed)
                return
            try:
                query_payload = self._query_payload(route.action, parsed)
                if route.action == "runtime_capabilities" and self.service is None:
                    result = self._legacy_runtime_snapshot(query_payload["max_files"])
                elif route.action == "release_evidence" and self.service is None:
                    result = self._legacy_release_evidence(query_payload["max_files"])
                else:
                    result = self._http_application().read(
                        route.action,
                        query_payload,
                        resource_id=route.resource_id,
                    )
            except ValueError as exc:
                self._write_error(exc, not_found=route.resource_id is not None)
            except Exception as exc:
                self._write_error(exc)
            else:
                self._write_json(200, result)
            return

        composite_action = self._composite_read_action(parsed.path)
        if composite_action is not None:
            try:
                result = self._http_application().read(
                    composite_action, resource_id=parsed.path.strip("/").split("/")[1]
                )
            except ValueError as exc:
                self._write_error(exc, not_found=True)
            except Exception as exc:
                self._write_error(exc)
            else:
                self._write_json(200, result)
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self):
        try:
            parsed, selection = self._domain_request(parse_request_target(self.path))
            body = self._read_json()
            if selection is not None:
                assert_domain_payload(selection, body)
            route = resolve_route("POST", parsed.path)
            if route is None:
                self._write_json(404, {"error": "not found"})
                return
            result = self._http_application().execute(
                route.action,
                body,
                run_id=route.resource_id,
                template_id=route.template_id,
            )
        except DomainRoutingApplicationError as exc:
            self._write_error(exc, not_found=exc.code == "domain_routing_decision_not_found")
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
            parsed, _selection = self._domain_request(parse_request_target(self.path))
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 2 or parts[0] != "sessions" or not parts[1]:
                self._write_json(404, {"error": "not found", "error_code": "not_found"})
                return
            result = self._http_application().execute(
                "session_delete", {}, run_id=parts[1]
            )
        except ValueError as exc:
            self._write_error(exc)
            return
        except Exception as exc:
            self._write_error(exc)
            return
        self._write_json(200, result)

    def _query_payload(self, action: str, parsed) -> dict[str, Any]:
        values = query_params(parsed)
        payload = {key: items[0] for key, items in values.items() if items}
        if action in {"action_executions", "runs", "sessions", "session_runs", "tool_approvals"}:
            default = 50 if action in {"sessions", "tool_approvals"} else 20
            payload["limit"] = int(payload.get("limit", default))
        elif action == "memory":
            payload["limit"] = int(payload.get("limit", 20))
            payload["global_scope"] = payload.get("global", "0").lower() in {"1", "true", "yes"}
        elif action in {"runtime_capabilities", "release_evidence"}:
            payload["max_files"] = int(payload.get("max_files", 10))
            if payload["max_files"] < 1 or payload["max_files"] > 10:
                raise ValueError("max_files must be between 1 and 10")
        return payload

    def _serve_events(self, run_id: Optional[str], parsed) -> None:
        if not run_id:
            self._write_error(ValueError("run_id is required"), not_found=True)
            return
        try:
            values = query_params(parsed)
            header_cursor = self.headers.get("Last-Event-ID")
            cursor = validate_event_cursor(
                header_cursor if header_cursor is not None else (values.get("after") or [None])[0]
            )
            limit = validate_event_limit((values.get("limit") or [100])[0])
            reader = self._http_application()
            payload = reader.read(
                "run_events", {"after": cursor, "limit": limit}, resource_id=run_id
            )
        except ValueError as exc:
            self._write_error(exc, not_found=True)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            while True:
                events = payload.get("events") or []
                for event in events:
                    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(f"id: {event['sequence']}\nevent: run_event\ndata: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
                cursor = int(payload.get("next_cursor") or cursor)
                if page_contains_terminal_event(events) or (payload.get("terminal") and not payload.get("has_more")):
                    return
                self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
                time.sleep(0.75)
                payload = reader.read(
                    "run_events", {"after": cursor, "limit": limit}, resource_id=run_id
                )
        except (BrokenPipeError, ConnectionResetError):
            return

    @staticmethod
    def _composite_read_action(path: str) -> Optional[str]:
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "composite-runs" and parts[1]:
            return "composite_run_detail"
        if len(parts) == 3 and parts[0] == "composite-runs" and parts[1] and parts[2] in {
            "observability", "evidence", "view"
        }:
            return "composite_" + parts[2]
        return None

    def _serve_artifact(self, path: str) -> bool:
        parts = path.strip("/").split("/")
        if len(parts) not in {3, 4} or parts[0] != "artifacts" or not parts[2]:
            return False
        if Path(parts[2]).name != parts[2]:
            self._write_json(404, {"error": "artifact not found", "error_code": "not_found"})
            return True
        if len(parts) == 4 and parts[3] not in {"manifest", "evidence"}:
            return False
        artifact = self._artifact_file(parts[1], parts[2])
        if artifact is None:
            self._write_json(404, {"error": "artifact not found", "error_code": "not_found"})
            return True
        path_obj, content_type = artifact
        if len(parts) == 3:
            if not path_obj.is_file():
                self._write_json(404, {"error": "artifact not found", "error_code": "not_found"})
                return True
            self._write_file(path_obj, content_type)
            return True
        try:
            payload = load_artifact_json(path_obj)
            action = "artifact_manifest" if parts[3] == "manifest" else "artifact_evidence"
            result = self._http_application().read(
                action, {"artifact_payload": payload, "artifact_ref": path_obj.name}
            )
        except Exception as exc:
            self._write_error(exc, not_found=True)
        else:
            self._write_json(200, result)
        return True

    def _artifact_file(self, group: str, name: str):
        roots = {
            "runs": (self.artifact_root, "application/json", "run"),
            "actions": (self.artifact_root, "application/json", "action"),
            "geojson": (self.geojson_root, "application/geo+json", "geojson"),
        }
        selected = roots.get(group)
        if selected is None:
            return None
        root, content_type, kind = selected
        # A caller may deliberately provide an isolated artifact root (the
        # historical handler seam and local tooling both do this).  In that
        # case it must win over the Service's persistent store root.
        explicit_artifact_root = "artifact_root" in type(self).__dict__
        if (
            group in {"runs", "actions"}
            and self.service is not None
            and not explicit_artifact_root
        ):
            store_root = getattr(getattr(self.service, "_artifact_store", None), "_root", None)
            if store_root is not None:
                root = Path(store_root)
        domain_id = getattr(self, "_request_domain_id", None)
        if not domain_id:
            return None
        candidate = safe_artifact_path(
            Path(root),
            name,
            ".geojson" if kind == "geojson" else ".json",
            "action-" if kind == "action" else "",
            domain_id=domain_id,
            metadata_root=self.artifact_root if kind == "geojson" else None,
        )
        return (candidate, content_type) if candidate is not None else None

    def _domain_request(self, parsed):
        # Requests handled by one ThreadingHTTPServer instance can arrive on
        # the same handler object in compatibility tests and custom servers.
        # Rebind from the class seam for every request so a previous
        # domain-scoped selection cannot leak into the next request.
        self.service = type(self).service
        self._request_domain_id = getattr(self.service, "_resolved_domain_id", None)
        scope = parse_domain_path(parsed.path)
        if scope is None:
            return parsed, None
        if not self._request_domain_id:
            raise ValueError("service Domain is not bound")
        if self.host is None:
            raise ValueError("multi-domain host is unavailable")
        selection = self.host.select(scope.domain_id)
        self.service = self.host.service(selection)
        self._request_domain_id = selection.domain_id
        return parsed._replace(path=scope.path), selection

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return decode_json_body(self.rfile.read(length))

    def _write_json(self, status_code: int, payload: Any):
        body = encode_json_body(payload)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_error(self, exc: Exception, *, not_found=False, service_unavailable=False):
        status, payload = error_projection(
            exc, not_found=not_found, service_unavailable=service_unavailable
        )
        self._write_json(status, payload)

    def _write_file(self, path: Path, content_type: str):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


__all__ = ["StdlibAgentApiHandler"]
