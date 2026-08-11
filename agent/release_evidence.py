"""Build an explicit, bounded release report for the configured data volume."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from .analysis_ready_binding import verify_source_binding
from .data_quality import dataset_health_report
from .dataset_catalog import DatasetCatalog, DatasetEntry
from .dataset_manifest import load_manifest, verify_dataset_manifest


REPORT_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def release_evidence_snapshot(
    config_path: str | None = None,
    *,
    max_files: int = 10,
) -> Dict[str, Any]:
    """Run the explicit metadata/source/output publication checks."""

    configured = Path(
        config_path
        or os.environ.get(
            "SPATIAL_AGENT_DATASET_CONFIG", "config/datasets.local.example.json"
        )
    )
    base = {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_name": configured.name,
    }
    if not configured.is_file():
        return {
            **base,
            "status": "unavailable",
            "data_readiness": "unavailable",
            "metadata": {"status": "unavailable", "mismatches": ["dataset config is missing"]},
            "source_binding": _not_configured("dataset config is missing"),
            "output_manifest": _not_configured("dataset config is missing"),
            "manifest": _not_configured("dataset config is missing"),
        }

    try:
        catalog = DatasetCatalog.from_json(str(configured))
        health = dataset_health_report(catalog, max_files=max_files)
    except Exception as exc:
        reason = str(exc)[:240]
        return {
            **base,
            "status": "unavailable",
            "data_readiness": "unavailable",
            "metadata": {"status": "unavailable", "mismatches": [reason]},
            "source_binding": _not_configured(reason),
            "output_manifest": _not_configured(reason),
            "manifest": _not_configured(reason),
        }

    analysis_ready = health.get("analysis_ready") or {}
    metadata = {
        "status": health.get("status", "unknown"),
        "data_readiness": health.get("data_readiness", "unknown"),
        "core_status": health.get("core_status", "unknown"),
        "optional_status": health.get("optional_status", "unknown"),
        "analysis_ready": _analysis_ready_summary(analysis_ready),
        "updated_at": health.get("updated_at"),
    }

    raw_report = _load_analysis_report(catalog.analysis_ready_report_path)
    raw_binding = raw_report.get("source_binding") if raw_report else None
    if raw_binding:
        source_catalog = _source_catalog_from_binding(catalog, raw_binding)
        source = verify_source_binding(source_catalog or catalog, raw_binding)
    elif analysis_ready.get("status") in (None, "not_configured"):
        source = _not_configured("analysis-ready source binding is not configured")
    else:
        source = _not_configured("analysis-ready source binding is missing")

    manifest_payload = None
    if catalog.manifest_path and Path(catalog.manifest_path).is_file():
        try:
            manifest_payload = load_manifest(catalog.manifest_path)
            verification = verify_dataset_manifest(
                catalog, manifest_payload, verify_hashes=True
            )
            manifest = _verification_summary(verification)
        except Exception as exc:
            manifest = _not_configured(str(exc)[:240])
    elif catalog.manifest_path:
        manifest = _not_configured("manifest file is missing")
    else:
        manifest = _not_configured("dataset manifest is not configured")

    output = _output_verification(
        analysis_ready,
        raw_report,
        manifest_payload,
        manifest,
    )
    statuses = [metadata["data_readiness"], source["status"], output["status"]]
    required_statuses = [value for value in statuses if value != "not_configured"]
    overall = _aggregate_status(required_statuses)
    return {
        **base,
        "status": overall,
        "data_readiness": metadata["data_readiness"],
        "metadata": metadata,
        "source_binding": source,
        "output_manifest": output,
        "manifest": manifest,
    }


def _analysis_ready_summary(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = {
        "status": str(value.get("status", "not_configured"))[:20],
        "derived_version": str(value.get("derived_version", ""))[:128],
        "target_grid": dict(value.get("target_grid") or {}),
        "grid_alignment": dict(value.get("grid_alignment") or {}),
    }
    if isinstance(value.get("derivation"), Mapping):
        result["derivation"] = dict(value["derivation"])
    outputs = value.get("outputs")
    if isinstance(outputs, Mapping):
        result["outputs"] = {
            str(name)[:32]: Path(str(path)).name[:160]
            for name, path in outputs.items()
            if path
        }
    return result


def _load_analysis_report(path: str | None) -> Dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.is_file():
        return {}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_catalog_from_binding(
    catalog: DatasetCatalog, binding: Mapping[str, Any]
) -> DatasetCatalog | None:
    """Recreate the original source view when the active catalog uses derivatives."""

    datasets = binding.get("datasets")
    if not isinstance(datasets, Mapping) or not datasets:
        return None
    entries = {}
    for name, value in datasets.items():
        if not isinstance(value, Mapping):
            return None
        provenance = value.get("provenance") or {}
        files = value.get("files") or []
        paths = []
        for item in files:
            if not isinstance(item, Mapping) or not item.get("path"):
                return None
            path = Path(str(item["path"]))
            if path.is_absolute():
                paths.append(str(path))
            else:
                paths.append(str(Path(catalog.root) / path))
        entries[str(name)] = DatasetEntry(
            name=str(name),
            kind=str(value.get("kind", "")),
            format=str(value.get("format", "")),
            role=str(value.get("role", "")),
            files=paths,
            source=provenance.get("source"),
            version=provenance.get("version"),
            attribution=provenance.get("attribution"),
            license=provenance.get("license"),
        )
    return DatasetCatalog(catalog.root, entries)


def _output_verification(
    analysis_ready: Mapping[str, Any],
    raw_report: Mapping[str, Any],
    manifest_payload: Mapping[str, Any] | None,
    manifest: Mapping[str, Any],
) -> Dict[str, Any]:
    outputs = (raw_report.get("outputs") or analysis_ready.get("outputs") or {})
    if not isinstance(outputs, Mapping) or not outputs:
        return _not_configured("analysis-ready outputs are not configured")
    datasets = manifest_payload.get("datasets") if isinstance(manifest_payload, Mapping) else {}
    datasets = datasets if isinstance(datasets, Mapping) else {}
    mismatches = []
    details = {}
    verified_files = 0
    manifest_mismatches = manifest.get("mismatches") or []
    for name in ("dem", "land_use"):
        reported = Path(str(outputs.get(name, ""))).name if outputs.get(name) else ""
        entry = datasets.get(name) if isinstance(datasets, Mapping) else None
        files = entry.get("files") if isinstance(entry, Mapping) else []
        files = files if isinstance(files, list) else []
        names = [
            Path(str(item.get("path", ""))).name
            for item in files
            if isinstance(item, Mapping) and item.get("path")
        ]
        matching = [
            item
            for item in files
            if isinstance(item, Mapping)
            and Path(str(item.get("path", ""))).name == reported
        ]
        item = matching[0] if len(matching) == 1 else None
        mismatch_for_file = any(
            str(issue).startswith(f"{name}/") and reported in str(issue)
            for issue in manifest_mismatches
        )
        hash_verified = bool(
            item
            and item.get("exists") is True
            and _SHA256.fullmatch(str(item.get("sha256", "")))
            and not mismatch_for_file
        )
        matched = bool(reported) and names == [reported]
        if not matched:
            mismatches.append(f"{name} output does not match manifest")
        elif not hash_verified:
            mismatches.append(f"{name} output SHA-256 is not verified")
        if hash_verified:
            verified_files += 1
        details[name] = {
            "reported": reported,
            "manifest": names[:3],
            "matched": matched,
            "hash_verified": hash_verified,
        }
    status = "ready" if not mismatches else "degraded"
    return {
        "status": status,
        "verification_mode": "sha256",
        "hashes_verified": status == "ready",
        "verified_files": verified_files,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "outputs": details,
    }


def _verification_summary(value: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": value.get("status", "unknown"),
        "verification_mode": value.get("verification_mode", "sha256"),
        "hashes_verified": bool(value.get("hashes_verified", False)),
        "verified_files": int(value.get("verified_files") or 0),
        "mismatch_count": int(value.get("mismatch_count") or 0),
        "mismatches": list(value.get("mismatches") or [])[:20],
    }


def _not_configured(reason: str) -> Dict[str, Any]:
    return {
        "status": "not_configured",
        "verification_mode": "not_configured",
        "hashes_verified": False,
        "verified_files": 0,
        "mismatch_count": 0,
        "mismatches": [str(reason)[:240]],
    }


def _aggregate_status(statuses) -> str:
    if not statuses:
        return "not_configured"
    if any(status == "unavailable" for status in statuses):
        return "unavailable"
    if any(status == "degraded" for status in statuses):
        return "degraded"
    if all(status in ("ready", "recorded") for status in statuses):
        return "ready"
    if any(status == "not_configured" for status in statuses):
        return "not_configured"
    return "unknown"
