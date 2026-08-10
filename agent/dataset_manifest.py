"""Reproducible dataset manifest generation and verification.

The manifest contains bounded metadata and file fingerprints, never raw GIS
content.  Hash verification is explicit because production health checks must
not unexpectedly read multi-gigabyte rasters on every request.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from .dataset_catalog import DatasetCatalog, DatasetEntry, controlled_provenance


MANIFEST_VERSION = 1
_HASH_CHUNK_SIZE = 1024 * 1024


def build_dataset_manifest(
    catalog: DatasetCatalog,
    *,
    max_files_per_dataset: Optional[int] = None,
    include_hashes: bool = True,
) -> Dict[str, Any]:
    """Build a deterministic manifest for the currently resolved catalog."""

    datasets = {}
    for entry in sorted(catalog.list_entries(), key=lambda item: item.name):
        paths = entry.files if max_files_per_dataset is None else entry.files[:max_files_per_dataset]
        datasets[entry.name] = {
            "kind": entry.kind,
            "format": entry.format,
            "role": entry.role,
            "provenance": entry.provenance,
            "files": [
                _file_fingerprint(catalog.root, path, include_hash=include_hashes)
                for path in sorted(paths)
            ],
        }
    return {
        "manifest_version": MANIFEST_VERSION,
        "root_label": Path(catalog.root).name or "dataset-root",
        "datasets": datasets,
    }


def verify_dataset_manifest(
    catalog: DatasetCatalog,
    manifest: Mapping[str, Any],
    *,
    verify_hashes: bool = True,
) -> Dict[str, Any]:
    """Compare a manifest with the current catalog without exposing full paths."""

    if not isinstance(manifest, Mapping):
        return _verification("unavailable", ["manifest must be an object"])
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        return _verification("unavailable", ["unsupported manifest_version"])
    expected_datasets = manifest.get("datasets")
    if not isinstance(expected_datasets, Mapping):
        return _verification("unavailable", ["manifest.datasets must be an object"])

    actual = {entry.name: entry for entry in catalog.list_entries()}
    mismatches = []
    verified_files = 0
    expected_names = set(expected_datasets)
    actual_names = set(actual)
    for name in sorted(expected_names - actual_names):
        mismatches.append(f"dataset missing from catalog: {name}")
    for name in sorted(actual_names - expected_names):
        mismatches.append(f"dataset missing from manifest: {name}")

    for name in sorted(expected_names & actual_names):
        expected = expected_datasets[name]
        entry = actual[name]
        if not isinstance(expected, Mapping):
            mismatches.append(f"dataset manifest entry is invalid: {name}")
            continue
        for field, value in (("kind", entry.kind), ("format", entry.format), ("role", entry.role)):
            if expected.get(field) != value:
                mismatches.append(f"{name}.{field} differs")
        if controlled_provenance(expected.get("provenance")) != entry.provenance:
            mismatches.append(f"{name}.provenance differs")
        expected_files = expected.get("files")
        if not isinstance(expected_files, list):
            mismatches.append(f"{name}.files must be an array")
            continue
        expected_by_path = {
            item.get("path"): item
            for item in expected_files
            if isinstance(item, Mapping) and isinstance(item.get("path"), str)
        }
        actual_by_path = {
            _relative_path(catalog.root, path): path for path in entry.files
        }
        for path in sorted(set(expected_by_path) - set(actual_by_path)):
            mismatches.append(f"{name} file missing: {path}")
        for path in sorted(set(actual_by_path) - set(expected_by_path)):
            mismatches.append(f"{name} file not in manifest: {path}")
        for path in sorted(set(expected_by_path) & set(actual_by_path)):
            expected_file = expected_by_path[path]
            current = _file_fingerprint(
                catalog.root,
                actual_by_path[path],
                include_hash=verify_hashes and bool(expected_file.get("sha256")),
            )
            for field in ("exists", "size_bytes"):
                if expected_file.get(field) != current.get(field):
                    mismatches.append(f"{name}/{path}.{field} differs")
            if verify_hashes and expected_file.get("sha256") != current.get("sha256"):
                mismatches.append(f"{name}/{path}.sha256 differs")
            if current.get("exists"):
                verified_files += 1

    status = "ready" if not mismatches else "degraded"
    return _verification(status, mismatches, verified_files=verified_files, hashes_verified=verify_hashes)


def load_manifest(path: str | os.PathLike[str]) -> Dict[str, Any]:
    """Load a manifest from disk with a stable UTF-8 JSON contract."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _file_fingerprint(root: str, path: str, *, include_hash: bool) -> Dict[str, Any]:
    candidate = Path(path)
    result: Dict[str, Any] = {
        "path": _relative_path(root, path),
        "exists": candidate.is_file(),
        "size_bytes": candidate.stat().st_size if candidate.is_file() else 0,
    }
    if include_hash and result["exists"]:
        result["sha256"] = _sha256(candidate)
    return result


def _relative_path(root: str, path: str) -> str:
    return os.path.normpath(os.path.relpath(str(Path(path).resolve()), str(Path(root).resolve()))).replace("\\", "/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _verification(
    status: str,
    mismatches: Iterable[str],
    *,
    verified_files: int = 0,
    hashes_verified: bool = False,
) -> Dict[str, Any]:
    issues = list(mismatches)
    return {
        "status": status,
        "metadata_only": True,
        "hashes_verified": hashes_verified,
        "verified_files": verified_files,
        "mismatch_count": len(issues),
        "mismatches": issues[:50],
    }
