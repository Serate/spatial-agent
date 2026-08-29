"""Build an explicit, bounded runtime capability snapshot on demand."""

import os
import time
from pathlib import Path
from typing import Any, Dict, Mapping

from agent.capability_catalog import runtime_capability_catalog
from .data_quality import dataset_health_report
from .dataset_catalog import DatasetCatalog, controlled_provenance
from agent.environment_status import environment_status
from agent.tools import ToolRegistry


class _CapabilityProbeAdapter:
    """Adapter used only to inspect the native provider contract.

    The runtime capability endpoint must not execute a business tool while it
    is building its snapshot. Native provider health is definition/adapter
    health, so an inert adapter is sufficient for this read-only probe.
    """

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("capability probe does not execute tools")


def tool_provider_snapshot() -> Dict[str, Any]:
    """Return bounded provider evidence without invoking a business tool."""
    schema_path = Path(__file__).resolve().parent.parent / "tools" / "schema" / "tool-definitions.json"
    try:
        registry = ToolRegistry.from_json(str(schema_path), _CapabilityProbeAdapter())
        return {
            "tool_provider": registry.provider_info(),
            "tool_provider_health": registry.provider_health(),
            "tool_governance": registry.governance_summary(),
        }
    except Exception:
        # Keep the runtime endpoint useful even when the static tool manifest
        # is damaged or missing; never expose the raw exception text here.
        return {
            "tool_provider": {"id": "unknown", "tool_count": 0},
            "tool_provider_health": {
                "schema_version": "spatial-agent.tool-provider-health.v1",
                "provider_id": "unknown",
                "status": "unavailable",
                "tool_count": 0,
                "definition_contract": {
                    "schema_version": "spatial-agent.tool-provider-contract.v1",
                    "provider_id": "unknown",
                    "status": "unavailable",
                    "tool_count": 0,
                    "validation": "not_available",
                },
                "reason_code": "tool_manifest_unavailable",
            },
            "tool_governance": {
                "schema_version": "spatial-agent.tool-governance.v1",
                "provider_id": "unknown",
                "tool_count": 0,
                "returned_tool_count": 0,
                "requires_approval_count": 0,
                "side_effect_tool_count": 0,
                "tools": [],
            },
        }


def runtime_capability_snapshot(max_files: int = 10) -> Dict[str, Any]:
    status = environment_status()
    environment = "local" if status["capabilities"]["local_gis_backend"] else "memory"
    provider = tool_provider_snapshot()
    config_path = Path(
        os.environ.get("SPATIAL_AGENT_DATASET_CONFIG", "config/datasets.local.example.json")
    )
    if not config_path.is_file():
        snapshot = runtime_capability_catalog({}, environment=environment, **provider)
        snapshot["health_status"] = "unavailable"
        snapshot["error"] = "dataset capability config not found"
        snapshot["config_path"] = str(config_path)
        snapshot["data_provenance"] = {}
        snapshot["updated_at"] = _utc_timestamp()
        snapshot["provider_health"] = status.get("provider_health", {})
        return snapshot
    try:
        catalog = DatasetCatalog.from_json(str(config_path))
        health = dataset_health_report(catalog, max_files=max_files)
    except Exception as exc:
        snapshot = runtime_capability_catalog({}, environment=environment, **provider)
        snapshot["health_status"] = "unavailable"
        snapshot["error"] = str(exc)[:240]
        snapshot["config_path"] = str(config_path)
        snapshot["data_provenance"] = {}
        snapshot["updated_at"] = _utc_timestamp()
        snapshot["provider_health"] = status.get("provider_health", {})
        return snapshot
    snapshot = runtime_capability_catalog(health, environment=environment, **provider)
    data_provenance = {
        str(item.get("dataset")): controlled_provenance(item.get("provenance"))
        for item in health.get("datasets", [])
        if isinstance(item, Mapping) and item.get("dataset")
    }
    for item in health.get("datasets", []):
        if not isinstance(item, Mapping) or not item.get("dataset"):
            continue
        dataset_name = str(item["dataset"])
        entry = catalog.get(dataset_name)
        discovery = getattr(entry, "discovery", {}) if entry is not None else {}
        if isinstance(discovery, Mapping) and discovery:
            evidence = snapshot.get("data_evidence", {}).get(dataset_name)
            if isinstance(evidence, Mapping):
                evidence["discovery"] = dict(discovery)
    snapshot["data_provenance"] = data_provenance
    snapshot["relationships"] = health.get("relationships", {})
    for capability in snapshot.get("capabilities", []):
        evidence = capability.get("runtime_evidence", {})
        datasets = evidence.get("datasets", {}) if isinstance(evidence, dict) else {}
        for name, item in datasets.items():
            if isinstance(item, dict):
                item["provenance"] = dict(data_provenance.get(name, {}))
    snapshot["config_path"] = str(config_path)
    snapshot["runtime"] = {
        "local_gis_backend": status["capabilities"]["local_gis_backend"],
        "geopandas": status["dependencies"]["geopandas"],
        "rasterio": status["dependencies"]["rasterio"],
    }
    snapshot["provider_health"] = status.get("provider_health", {})
    return snapshot


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
