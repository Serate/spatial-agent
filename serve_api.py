import argparse
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from agent.environment_status import environment_status
from agent.service import AgentService


class AgentApiHandler(BaseHTTPRequestHandler):
    service = AgentService()
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
        if parsed.path == "/runs":
            self._write_json(200, self.service.list_runs())
            return
        if parsed.path == "/metrics":
            self._write_json(200, self.service.metrics())
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
        is_comparison = parsed.path == "/comparisons"
        if parsed.path != "/runs" and not is_retry and not is_cancel and not is_comparison:
            self._write_json(404, {"error": "not found"})
            return
        try:
            payload = self._read_json()
            if is_comparison:
                result = self.service.compare_buildability(
                    admin_name=payload.get("admin_name", ""),
                    thresholds=payload.get("thresholds", []),
                    planner=payload.get("planner", "rule"),
                    backend=payload.get("backend", "local"),
                )
            elif is_retry or is_cancel:
                parts = parsed.path.strip("/").split("/")
                expected_action = "retry" if is_retry else "cancel"
                if len(parts) != 3 or not parts[1] or parts[2] != expected_action:
                    self._write_json(404, {"error": "not found"})
                    return
                if is_cancel:
                    result = self.service.cancel(
                        run_id=parts[1],
                        planner=payload.get("planner", "rule"),
                        backend=payload.get("backend", "memory"),
                    )
                else:
                    result = self.service.retry(
                        run_id=parts[1],
                        planner=payload.get("planner", "rule"),
                        backend=payload.get("backend", "memory"),
                        export_artifact=bool(payload.get("export_artifact", False)),
                        export_geojson=bool(payload.get("export_geojson", False)),
                        geojson_max_features=payload.get("geojson_max_features", 100),
                    )
            else:
                result = self.service.run(
                    request=payload.get("request", ""),
                    session_id=payload.get("session_id", "default"),
                    planner=payload.get("planner", "rule"),
                    backend=payload.get("backend", "memory"),
                    export_artifact=bool(payload.get("export_artifact", False)),
                    export_geojson=bool(payload.get("export_geojson", False)),
                    geojson_max_features=payload.get("geojson_max_features", 100),
                    timeout_seconds=payload.get("timeout_seconds"),
                )
        except ValueError as exc:
            self._write_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self._write_json(500, {"error": str(exc)})
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
        roots = {"runs": (self.artifact_root, "application/json"), "geojson": (self.geojson_root, "application/geo+json")}
        if parts[1] not in roots or Path(parts[2]).name != parts[2]:
            return None
        root, content_type = roots[parts[1]]
        candidate = (root / parts[2]).resolve()
        if root.resolve() not in candidate.parents:
            return None
        expected_suffix = ".json" if parts[1] == "runs" else ".geojson"
        if candidate.suffix != expected_suffix:
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
