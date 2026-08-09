import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CONFIG_PATH = Path("config") / "openai.local.json"


def load_openai_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load OpenAI planner settings from env vars and an optional local JSON file."""

    config_path = Path(path or os.environ.get("OPENAI_CONFIG_FILE", DEFAULT_CONFIG_PATH))
    config: Dict[str, Any] = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))

    return {
        "api_key": os.environ.get("OPENAI_API_KEY") or config.get("OPENAI_API_KEY"),
        "model": os.environ.get("OPENAI_MODEL") or config.get("model"),
        "wire_api": os.environ.get("OPENAI_WIRE_API") or config.get("wire_api", "responses"),
        "max_output_tokens": _int_setting(
            os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", config.get("max_output_tokens"))
        ),
        "timeout_seconds": _float_setting(
            os.environ.get("OPENAI_TIMEOUT_SECONDS", config.get("timeout_seconds"))
        ),
        "max_retries": _int_setting(
            os.environ.get("OPENAI_MAX_RETRIES", config.get("max_retries"))
        ),
        "retry_backoff_seconds": _float_setting(
            os.environ.get(
                "OPENAI_RETRY_BACKOFF_SECONDS", config.get("retry_backoff_seconds")
            )
        ),
        "retry_backoff_max_seconds": _float_setting(
            os.environ.get(
                "OPENAI_RETRY_BACKOFF_MAX_SECONDS",
                config.get("retry_backoff_max_seconds"),
            )
        ),
        "api_url": os.environ.get("OPENAI_API_URL") or config.get("api_url"),
        "base_url": os.environ.get("OPENAI_BASE_URL") or config.get("base_url"),
        "reasoning_effort": os.environ.get("OPENAI_REASONING_EFFORT")
        or config.get("model_reasoning_effort"),
        "auth_location": os.environ.get("OPENAI_AUTH_LOCATION") or config.get("auth_location"),
        "api_key_query_param": os.environ.get("OPENAI_API_KEY_QUERY_PARAM")
        or config.get("api_key_query_param"),
    }


def _int_setting(value):
    return int(value) if value not in (None, "") else None


def _float_setting(value):
    return float(value) if value not in (None, "") else None
