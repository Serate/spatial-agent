"""Framework-neutral HTTP transport helpers.

``HTTPApplication`` owns HTTP semantics.  This module owns the small pieces
that differ only because one adapter is FastAPI and the other is
``http.server``: target/query parsing, JSON bytes, error projections, and
safe artifact payload access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import ParseResult, parse_qs, urlparse

from agent.api_contract import error_response, error_status
from agent.artifact_access import resolve_artifact_path


def parse_request_target(raw_path: str) -> ParseResult:
    """Parse a request target consistently for the stdlib adapter."""

    return urlparse(str(raw_path or "/"))


def query_params(parsed: ParseResult | str) -> Dict[str, list[str]]:
    """Return decoded query parameters with blank values retained."""

    query = parsed.query if isinstance(parsed, ParseResult) else str(parsed or "")
    return parse_qs(query, keep_blank_values=True)


def query_value(
    parsed: ParseResult, name: str, default: str = ""
) -> str:
    values = query_params(parsed).get(name)
    return values[0] if values else default


def decode_json_body(raw: bytes) -> Any:
    """Decode one UTF-8 JSON body; an empty body is the empty object."""

    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def encode_json_body(payload: Any) -> bytes:
    """Encode the shared response representation used by stdlib HTTP."""

    return json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")


def error_projection(
    exc: Exception,
    *,
    not_found: bool = False,
    service_unavailable: bool = False,
) -> tuple[int, Dict[str, Any]]:
    """Project an exception once for both transport adapters."""

    return (
        error_status(
            exc,
            not_found=not_found,
            service_unavailable=service_unavailable,
        ),
        error_response(
            exc,
            not_found=not_found,
            service_unavailable=service_unavailable,
        ),
    )


def safe_artifact_path(
    root: Path,
    name: str,
    suffix: str,
    prefix: str = "",
    *,
    domain_id: str = "gis",
    metadata_root: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve a bounded artifact path without exposing filesystem traversal."""

    kind = "geojson" if suffix == ".geojson" else ("action" if prefix else "run")
    return resolve_artifact_path(
        root,
        name,
        kind=kind,
        domain_id=domain_id,
        metadata_root=metadata_root,
    )


def load_artifact_json(path: Path) -> Dict[str, Any]:
    """Read one artifact JSON object using the shared not-found contract."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("artifact not found") from exc
    if not isinstance(value, dict):
        raise ValueError("artifact not found")
    return value


__all__ = [
    "decode_json_body",
    "encode_json_body",
    "error_projection",
    "load_artifact_json",
    "parse_request_target",
    "query_params",
    "query_value",
    "safe_artifact_path",
]
