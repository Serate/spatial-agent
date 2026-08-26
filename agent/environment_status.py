import importlib.util
import os
import socket
import sys
from pathlib import Path
from typing import Dict
from urllib.parse import urlsplit

from agent.openai_config import load_openai_config
from agent.capability_catalog import capability_catalog
from agent.provider_runtime import build_provider_health


def environment_status() -> Dict:
    """Return safe runtime capability information for the console and health check."""
    has_geopandas = importlib.util.find_spec("geopandas") is not None
    has_rasterio = importlib.util.find_spec("rasterio") is not None
    dataset_root = Path(os.environ.get("SPATIAL_AGENT_DATASET_ROOT", "D:/dataset/agent"))
    config_file = Path(os.environ.get("OPENAI_CONFIG_FILE", "config/openai.local.json"))
    try:
        openai_config = load_openai_config()
    except (OSError, ValueError, TypeError):
        openai_config = {}
    live_llm_configured = bool(os.environ.get("OPENAI_API_KEY")) or config_file.exists()
    live_llm_network = _openai_network_available(openai_config) if live_llm_configured else False
    provider_health = build_provider_health(
        openai_config,
        network_available=live_llm_network,
        network_checked=live_llm_configured,
    )
    gdal_data_available = _runtime_data_available("GDAL_DATA", "gdalvrt.xsd")
    proj_data_available = _runtime_data_available("PROJ_LIB", "proj.db")
    capabilities = {
        "memory_backend": True,
        "local_gis_backend": has_geopandas and has_rasterio and dataset_root.exists(),
        "live_llm": provider_health["status"] == "ready",
        "live_llm_configured": live_llm_configured,
        "live_llm_network": live_llm_network,
    }
    return {
        "python": sys.executable,
        "capabilities": capabilities,
        "capability_catalog": capability_catalog(
            environment="local" if capabilities["local_gis_backend"] else "memory"
        ),
        "dependencies": {
            "geopandas": has_geopandas,
            "rasterio": has_rasterio,
        },
        "provider_health": provider_health,
        "data": {
            "dataset_root_exists": dataset_root.exists(),
            "gdal_data_available": gdal_data_available,
            "proj_data_available": proj_data_available,
        },
    }


def _openai_network_available(
    config: Dict | None = None, timeout_seconds: float = 1.5
) -> bool:
    """Check outbound socket availability to the configured LLM host without using tokens."""
    try:
        config = config if isinstance(config, dict) else load_openai_config()
        url = config.get("api_url") or config.get("base_url") or "https://api.openai.com"
        parsed = urlsplit(url)
        host = parsed.hostname
        if not host:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _runtime_data_available(variable: str, marker: str) -> bool:
    """Check an explicitly configured GDAL/PROJ data directory safely."""
    configured = os.environ.get(variable)
    if not configured:
        # Development environments may let GDAL discover its own data path.
        return True
    return (Path(configured) / marker).is_file()
