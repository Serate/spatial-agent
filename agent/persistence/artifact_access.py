"""Bounded, domain-aware artifact file access for HTTP entry points."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agent.nested_schema import NestedSchemaError, normalize_result_contract


def resolve_artifact_path(
    root: Path,
    name: str,
    *,
    kind: str,
    domain_id: Optional[str],
    metadata_root: Optional[Path] = None,
) -> Optional[Path]:
    """Return a readable artifact only when its persisted Domain matches.

    HTTP handlers must not infer authorization from a filename.  GeoJSON
    exports created by older versions do not carry a Domain field, so their
    sibling run artifact is used as bounded metadata when available; unbound
    files are readable only through an explicitly selected legacy Domain
    adapter.
    """

    if kind not in {"run", "action", "geojson"}:
        raise ValueError("unsupported artifact kind")
    if not isinstance(name, str) or not name or len(name) > 256:
        return None
    if "/" in name or "\\" in name or name in {".", ".."}:
        return None
    expected_suffix = ".geojson" if kind == "geojson" else ".json"
    prefix = "action-" if kind == "action" else ""
    if not name.endswith(expected_suffix) or (prefix and not name.startswith(prefix)):
        return None

    root = Path(root).resolve()
    candidate = (root / name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if kind in {"run", "action"} and isinstance(payload.get("result"), dict):
        try:
            normalize_result_contract(payload["result"])
        except NestedSchemaError:
            # File download is a raw artifact boundary; unlike run recovery,
            # it has no result envelope to rebuild, so reject the file.
            return None

    stored_domain = payload.get("domain_id")
    if kind == "geojson" and not stored_domain:
        properties = payload.get("properties")
        if isinstance(properties, dict):
            stored_domain = properties.get("domain_id")
        if not stored_domain and metadata_root is not None:
            sibling = Path(metadata_root).resolve() / (candidate.stem + ".json")
            if sibling.is_file():
                try:
                    sibling_payload = json.loads(sibling.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    sibling_payload = None
                if isinstance(sibling_payload, dict):
                    stored_domain = sibling_payload.get("domain_id")
    if not stored_domain:
        if not domain_id:
            return None
        stored_domain = str(domain_id).strip()[:80]
    if domain_id and stored_domain != str(domain_id)[:80]:
        return None
    return candidate
