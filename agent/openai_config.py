"""Compatibility facade for the canonical provider integration config."""

from agent.integration.openai_config import (
    load_answer_generation_config,
    load_openai_config,
)

__all__ = ["load_openai_config", "load_answer_generation_config"]
