"""Canonical static asset seam for the Console HTTP adapters.

The FastAPI and standard-library transports intentionally share this small
interface.  They do not need to know whether assets come from the generated
tree or the source tree used by a local checkout.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "web" / "src"
DIST_ROOT = PROJECT_ROOT / "web" / "dist"
WEB_ASSETS = frozenset(
    {
        "styles.css",
        "console_app.js",
        "console_nested_schema.js",
        "console_decision_evidence.js",
        "console_evidence_registry.js",
        "console_workflow_evidence.js",
        "console_renderer_registry.js",
        "console_result_projection.js",
        "console_action_host.js",
        "console_interaction.js",
        "console_gis_plugin.js",
        "console_run_events.js",
        "console_answer_stream.js",
    }
)


def console_root() -> Path:
    """Return the built Console root, with a source-tree development fallback."""

    built_index = DIST_ROOT / "index.html"
    return DIST_ROOT if built_index.is_file() else SOURCE_ROOT


def console_index() -> Path:
    """Return the canonical index path for both HTTP transports."""

    return console_root() / "index.html"


def console_asset(name: str) -> Path | None:
    """Resolve one allowlisted asset without permitting path traversal."""

    filename = str(name or "")
    if Path(filename).name != filename or filename not in WEB_ASSETS:
        return None
    candidate = console_root() / filename
    return candidate if candidate.is_file() else None
