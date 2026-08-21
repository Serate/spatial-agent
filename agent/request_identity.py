"""Build a stable, transport-neutral identity for a user request."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from agent.contract_versions import REQUEST_IDENTITY_SCHEMA_VERSION

# Request identity is deliberately narrower than plan identity.  A planner,
# backend, or execution result may change while the request itself remains
# the same; those values must not make cross-entry comparisons drift.
_MAX_DEPTH = 8
_MAX_ITEMS = 128
_MAX_STRING = 4096
_MAX_KEY = 160


def build_request_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    """Return a credential-free identity for the semantic request content.

    The returned value contains no user text or transport identifiers, only a
    version and a SHA-256 fingerprint.  ``session_id``, planner/backend
    configuration, lifecycle state, answers, trace data, and tool results are
    intentionally outside this identity; plan changes belong to the separate
    plan-identity contract.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("request identity payload must be a mapping")

    request = payload.get("request")
    resolved_request = payload.get("resolved_request")
    if resolved_request is None:
        resolved_request = request
    semantic = {
        "request": _canonical_value(request),
        "resolved_request": _canonical_value(resolved_request),
        "workflow": _canonical_value(payload.get("workflow")),
        "spatial_context": _canonical_value(payload.get("spatial_context")),
    }
    canonical = {
        "schema_version": REQUEST_IDENTITY_SCHEMA_VERSION,
        "semantic": semantic,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": REQUEST_IDENTITY_SCHEMA_VERSION,
        "fingerprint": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def normalize_request_identity(value: Any) -> dict[str, str] | None:
    """Keep a stored identity bounded and safe for public result contracts."""

    if not isinstance(value, Mapping):
        return None
    version = value.get("schema_version")
    fingerprint = value.get("fingerprint")
    if not isinstance(version, str) or version != REQUEST_IDENTITY_SCHEMA_VERSION:
        return None
    if not isinstance(fingerprint, str) or not fingerprint.startswith("sha256:"):
        return None
    digest = fingerprint[7:]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return None
    return {
        "schema_version": REQUEST_IDENTITY_SCHEMA_VERSION,
        "fingerprint": fingerprint,
    }


def _canonical_value(value: Any, *, depth: int = 0) -> Any:
    """Convert supported semantic values to deterministic JSON data."""

    if depth >= _MAX_DEPTH:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str):
            return value[:_MAX_STRING]
        return value
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda item: str(item[0]))[:_MAX_ITEMS]
        return {
            str(key)[:_MAX_KEY]: _canonical_value(item, depth=depth + 1)
            for key, item in items
        }
    if isinstance(value, (list, tuple)):
        return [
            _canonical_value(item, depth=depth + 1)
            for item in list(value)[:_MAX_ITEMS]
        ]
    return str(value)[:_MAX_STRING]


__all__ = [
    "REQUEST_IDENTITY_SCHEMA_VERSION",
    "build_request_identity",
    "normalize_request_identity",
]
