"""Local stdlib compatibility entrypoint for the Spatial Agent.

FastAPI in ``production_api.py`` is the canonical product HTTP entrypoint.
This file intentionally contains only local startup and legacy exports; the
actual stdlib adapter lives in ``agent.application.stdlib_http`` and shares
the HTTPApplication, route table, transport error_projection, and Composition
Root with production.

The ``release-evidence`` route and the historical ``AgentApiHandler`` name are
kept for local GIS scripts and compatibility tests.
"""

from __future__ import annotations

import argparse
import atexit
import os
from pathlib import Path
from http.server import ThreadingHTTPServer

from agent.application.http import HTTPApplication
from agent.application.http_composition import (
    build_http_application,
    build_http_composition,
)
from agent.application.http_transport import (
    error_projection,
    load_artifact_json,
    safe_artifact_path,
)
from agent.application.stdlib_http import StdlibAgentApiHandler
from agent.domain_registry import resolve_domain_id
from agent.web_assets import WEB_ASSETS, console_asset, console_index, console_root
from domains.gis.adapters.release_evidence import release_evidence_snapshot
from domains.gis.adapters.runtime_capabilities import runtime_capability_snapshot


_legacy_runtime_capability_snapshot = runtime_capability_snapshot
_http_composition = build_http_composition(
    legacy_domain_id=resolve_domain_id("gis")
)
domain_host = _http_composition.host
legacy_service = _http_composition.service
domain_routing = _http_composition.routing
composite_application = _http_composition.composite
composite_planning_application = _http_composition.composite_planning


def runtime_capability_snapshot(max_files: int = 10) -> dict:
    """Compatibility function retained for isolated runtime snapshot tests."""
    return _legacy_runtime_capability_snapshot(max_files=max_files)


class AgentApiHandler(StdlibAgentApiHandler):
    """Legacy name backed by the shared standard-library adapter."""

    host = domain_host
    service = legacy_service
    routing = domain_routing
    artifact_root = Path(os.environ.get("SPATIAL_AGENT_ARTIFACT_ROOT", "outputs/runs"))
    geojson_root = Path(os.environ.get("SPATIAL_AGENT_GEOJSON_ROOT", "outputs/geojson"))
    web_root = console_root()

    def _http_application(self) -> HTTPApplication:
        # Resolve module globals at request time so old tests and local
        # adapters can replace a Service or Composite implementation safely.
        return build_http_application(
            self.service,
            routing=self.routing,
            composite=composite_application,
            composite_planning=composite_planning_application,
        )

    def _legacy_runtime_snapshot(self, max_files: int):
        return runtime_capability_snapshot(max_files=max_files)

    def _legacy_release_evidence(self, max_files: int):
        return release_evidence_snapshot(max_files=max_files)


def _close_default_service() -> None:
    """Release resources created by the local compatibility Composition Root."""
    composite_application.close()
    AgentApiHandler.service.close()
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
