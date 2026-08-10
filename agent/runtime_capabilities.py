"""Build an explicit, bounded runtime capability snapshot on demand."""

import os
from pathlib import Path
from typing import Any, Dict, Mapping

from .capability_catalog import capability_catalog, runtime_capability_catalog
from .data_quality import dataset_health_report
from .dataset_catalog import DatasetCatalog, controlled_provenance
from .environment_status import environment_status


def runtime_capability_snapshot(max_files: int = 10) -> Dict[str, Any]:
    status = environment_status()
    environment = "local" if status["capabilities"]["local_gis_backend"] else "memory"
    config_path = Path(
        os.environ.get("SPATIAL_AGENT_DATASET_CONFIG", "config/datasets.local.example.json")
    )
    if not config_path.is_file():
        return {
            **capability_catalog(environment=environment),
            "health_status": "unavailable",
            "error": "dataset capability config not found",
            "config_path": str(config_path),
            "data_provenance": {},
        }
    try:
        catalog = DatasetCatalog.from_json(str(config_path))
        health = dataset_health_report(catalog, max_files=max_files)
    except Exception as exc:
        return {
            **capability_catalog(environment=environment),
            "health_status": "unavailable",
            "error": str(exc)[:240],
            "config_path": str(config_path),
            "data_provenance": {},
        }
    snapshot = runtime_capability_catalog(health, environment=environment)
    data_provenance = {
        str(item.get("dataset")): controlled_provenance(item.get("provenance"))
        for item in health.get("datasets", [])
        if isinstance(item, Mapping) and item.get("dataset")
    }
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
    return snapshot
