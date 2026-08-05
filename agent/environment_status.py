import importlib.util
import os
import socket
import sys
from pathlib import Path
from typing import Dict
from urllib.parse import urlsplit

from agent.openai_config import load_openai_config


def environment_status() -> Dict:
    """Return safe runtime capability information for the console and health check."""
    has_geopandas = importlib.util.find_spec("geopandas") is not None
    has_rasterio = importlib.util.find_spec("rasterio") is not None
    dataset_root = Path(os.environ.get("SPATIAL_AGENT_DATASET_ROOT", "D:/dataset/agent"))
    openai_key = os.environ.get("OPENAI_API_KEY")
    config_file = Path(os.environ.get("OPENAI_CONFIG_FILE", "config/openai.local.json"))
    live_llm_configured = bool(openai_key) or config_file.exists()
    live_llm_network = _openai_network_available() if live_llm_configured else False
    return {
        "python": sys.executable,
        "capabilities": {
            "memory_backend": True,
            "local_gis_backend": has_geopandas and has_rasterio and dataset_root.exists(),
            "live_llm": live_llm_configured and live_llm_network,
            "live_llm_configured": live_llm_configured,
            "live_llm_network": live_llm_network,
        },
        "dependencies": {
            "geopandas": has_geopandas,
            "rasterio": has_rasterio,
        },
        "data": {
            "dataset_root_exists": dataset_root.exists(),
        },
    }


def _openai_network_available(timeout_seconds: float = 1.5) -> bool:
    """Check outbound socket availability to the configured LLM host without using tokens."""
    try:
        config = load_openai_config()
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
