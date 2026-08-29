"""Release-time binding between source datasets and derived raster outputs."""

import hashlib
import json
from typing import Any, Dict, Iterable

from .dataset_catalog import DatasetCatalog
from .dataset_manifest import build_dataset_manifest


BINDING_VERSION = 1
DEFAULT_SOURCE_DATASETS = ("admin_areas", "dem", "land_use")


def build_source_binding(
    catalog: DatasetCatalog,
    dataset_names: Iterable[str] = DEFAULT_SOURCE_DATASETS,
) -> Dict[str, Any]:
    """Create a deterministic, hash-backed source snapshot for a derivation."""

    names = tuple(dict.fromkeys(str(name) for name in dataset_names))
    manifest = build_dataset_manifest(catalog, include_hashes=True)
    datasets = {
        name: manifest["datasets"].get(
            name,
            {"kind": None, "format": None, "role": "", "provenance": {}, "files": []},
        )
        for name in names
    }
    canonical = {"binding_version": BINDING_VERSION, "datasets": datasets}
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    missing = [
        name
        for name, item in datasets.items()
        if not item.get("files") or any(not file.get("exists") for file in item["files"])
    ]
    return {
        **canonical,
        "fingerprint": "sha256:" + digest,
        "verification_mode": "sha256",
        "missing_datasets": missing,
    }


def verify_source_binding(catalog: DatasetCatalog, binding: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute a binding and report source changes without exposing paths."""

    if not isinstance(binding, dict):
        return _verification("unavailable", ["source binding must be an object"])
    if binding.get("binding_version") != BINDING_VERSION:
        return _verification("unavailable", ["unsupported source binding version"])
    bound_datasets = binding.get("datasets")
    if not isinstance(bound_datasets, dict) or not bound_datasets:
        return _verification("unavailable", ["source binding has no datasets"])
    names = bound_datasets.keys()
    current = build_source_binding(catalog, names)
    mismatches = []
    if not isinstance(binding.get("fingerprint"), str):
        mismatches.append("source binding fingerprint is missing")
    elif binding["fingerprint"] != current["fingerprint"]:
        mismatches.append("source datasets changed since derivation")
    if current.get("missing_datasets"):
        mismatches.append("source dataset files are missing")
    return _verification(
        "ready" if not mismatches else "degraded",
        mismatches,
        fingerprint=current["fingerprint"],
        datasets=list(names),
        verified_files=sum(
            len(item.get("files") or []) for item in current["datasets"].values()
        ),
    )


def _verification(
    status: str,
    mismatches,
    *,
    fingerprint: str = "",
    datasets=None,
    verified_files: int = 0,
) -> Dict[str, Any]:
    issues = list(mismatches)
    return {
        "status": status,
        "verification_mode": "sha256",
        "hashes_verified": status == "ready",
        "fingerprint": fingerprint,
        "datasets": list(datasets or []),
        "verified_files": verified_files,
        "mismatch_count": len(issues),
        "mismatches": issues[:20],
    }
