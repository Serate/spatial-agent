import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict


def environment_status() -> Dict:
    """Return safe runtime capability information for the console and health check."""
    has_geopandas = importlib.util.find_spec("geopandas") is not None
    has_rasterio = importlib.util.find_spec("rasterio") is not None
    dataset_root = Path(os.environ.get("SPATIAL_AGENT_DATASET_ROOT", "D:/dataset/agent"))
    openai_key = os.environ.get("OPENAI_API_KEY")
    config_file = Path(os.environ.get("OPENAI_CONFIG_FILE", "config/openai.local.json"))
    return {
        "python": sys.executable,
        "capabilities": {
            "memory_backend": True,
            "local_gis_backend": has_geopandas and has_rasterio and dataset_root.exists(),
            "live_llm": bool(openai_key) or config_file.exists(),
        },
        "dependencies": {
            "geopandas": has_geopandas,
            "rasterio": has_rasterio,
        },
        "data": {
            "dataset_root_exists": dataset_root.exists(),
        },
    }
