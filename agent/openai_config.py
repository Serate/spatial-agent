import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CONFIG_PATH = Path("config") / "openai.local.json"
_DEFAULT_ANSWER_OUTPUT_TOKENS = 4096


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
        "structured_output_mode": os.environ.get("OPENAI_STRUCTURED_OUTPUT_MODE")
        or config.get("structured_output_mode", "json_schema"),
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


def load_answer_generation_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load a bounded, latency-oriented config for the final answer pass.

    Planning and answer generation are separate provider calls with different
    failure budgets.  A user-facing answer should not inherit a planner's
    long timeout, retry, or large structured-output budget.  The same key,
    model, endpoint, and wire mode are retained unless explicitly overridden.
    """

    config = load_openai_config(path)
    source = {}
    config_path = Path(path or os.environ.get("OPENAI_CONFIG_FILE", DEFAULT_CONFIG_PATH))
    if config_path.exists():
        source = json.loads(config_path.read_text(encoding="utf-8"))

    planner_timeout = config.get("timeout_seconds")
    default_timeout = min(float(planner_timeout), 20.0) if planner_timeout else 20.0
    # Keep the user-facing answer budget independent from the compact planner
    # budget. A 2048-token planner cap must not shorten a normal answer.
    default_tokens = _DEFAULT_ANSWER_OUTPUT_TOKENS
    answer_timeout = _float_setting(
        os.environ.get("OPENAI_ANSWER_TIMEOUT_SECONDS", source.get("answer_timeout_seconds"))
    )
    answer_tokens = _int_setting(
        os.environ.get("OPENAI_ANSWER_MAX_OUTPUT_TOKENS", source.get("answer_max_output_tokens"))
    )
    answer_retries = _int_setting(
        os.environ.get("OPENAI_ANSWER_MAX_RETRIES", source.get("answer_max_retries"))
    )
    config["timeout_seconds"] = answer_timeout if answer_timeout is not None else default_timeout
    config["max_output_tokens"] = answer_tokens if answer_tokens is not None else default_tokens
    config["max_retries"] = answer_retries if answer_retries is not None else 0
    return config


def _int_setting(value):
    return int(value) if value not in (None, "") else None


def _float_setting(value):
    return float(value) if value not in (None, "") else None
