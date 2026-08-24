"""Controlled natural-language answer generation for completed runs.

The Runtime owns facts and evidence.  This module only projects a bounded,
redacted fact packet to a structured model call and validates the returned
user-facing answer.  Callers must keep a deterministic Domain Composer as the
fallback when the model is unavailable or returns an unsafe shape.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import PlanningError


ANSWER_GENERATION_SCHEMA_VERSION = "spatial-agent.answer-generation.v1"
ANSWER_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["answer"],
    "additionalProperties": False,
    "properties": {
        "answer": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1800,
        }
    },
}

_MAX_REQUEST_CHARS = 800
_MAX_CONTEXT_CHARS = 12000
_MAX_STEP_COUNT = 16
_MAX_MAPPING_ITEMS = 32
_MAX_LIST_ITEMS = 12
_MAX_STRING_CHARS = 240
_OMITTED_KEYS = {
    "api_key",
    "authorization",
    "credentials",
    "password",
    "secret",
    "token",
    "raw_response",
    "prompt",
    "messages",
    "geometry",
    "coordinates",
    "features",
    "geojson",
    "result_ref",
    "artifact_ref",
    "path",
    "file_path",
    "dataset_path",
}


@dataclass(frozen=True)
class AnswerGenerationResult:
    """Validated answer plus safe operational evidence."""

    answer: str
    evidence: dict[str, Any]


def build_answer_context(result: Any) -> dict[str, Any]:
    """Build a bounded fact packet without exposing raw tool payloads.

    The packet deliberately keeps tool names and scalar/nested statistics so
    the model can explain results, while excluding geometry, paths, refs,
    prompts and credentials.  It is a transport context, not a public result
    contract and must never be persisted as model input.
    """

    plan = getattr(result, "plan", None)
    output = getattr(plan, "output", {}) if plan is not None else {}
    output = output if isinstance(output, Mapping) else {}
    steps = []
    for step in list(getattr(result, "steps", []) or [])[:_MAX_STEP_COUNT]:
        item: dict[str, Any] = {
            "id": _safe_text(getattr(step, "id", ""), 96),
            "tool": _safe_text(getattr(step, "tool", ""), 96),
            "status": _safe_text(getattr(step, "status", ""), 32),
        }
        projected = _project_value(getattr(step, "result", None), key="result")
        if projected not in (None, {}, []):
            item["facts"] = projected
        error = getattr(step, "error", None)
        if error:
            item["error"] = _safe_text(error, 240)
        steps.append(item)

    packet: dict[str, Any] = {
        "schema_version": ANSWER_GENERATION_SCHEMA_VERSION,
        "request": _safe_text(getattr(result, "request", ""), _MAX_REQUEST_CHARS),
        "goal": _safe_text(getattr(plan, "goal", "") if plan else "", 400),
        "result_type": _safe_text(output.get("type"), 96),
        "status": _safe_text(getattr(getattr(result, "status", None), "value", getattr(result, "status", "")), 32),
        "assumptions": [
            _safe_text(item, 200)
            for item in (getattr(plan, "assumptions", []) or [])[:8]
            if isinstance(item, (str, int, float))
        ],
        "steps": steps,
    }
    # Keep the serialized packet bounded even when a custom Domain returns a
    # particularly wide scalar result.
    encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > _MAX_CONTEXT_CHARS:
        packet["steps"] = steps[:8]
        encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > _MAX_CONTEXT_CHARS:
            packet["steps"] = [
                {
                    "id": item.get("id"),
                    "tool": item.get("tool"),
                    "status": item.get("status"),
                    "error": item.get("error"),
                }
                for item in packet["steps"]
            ]
    return packet


class LLMAnswerGenerator:
    """Generate a concise answer from a validated, bounded fact packet."""

    def __init__(self, client: Any):
        self._client = client

    def generate(self, result: Any) -> AnswerGenerationResult:
        context = build_answer_context(result)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是面向普通用户的分析结果解读助手。只根据可信事实回答，不得补造事实、坐标、"
                    "数量或规划结论。结论优先，把说明要点写在 answer 字符串中；内部状态、工具名、"
                    "result_ref、memory:// 和 JSON 字段都要翻译成自然中文。若数据不完整，明确说明影响。"
                    "只返回一个 JSON 对象，且只能有 answer 字段；answer 必须是 1800 字符以内的非空字符串。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        payload = self._client.complete_json(messages, ANSWER_GENERATION_SCHEMA)
        if not isinstance(payload, Mapping):
            raise PlanningError("answer generator output must be an object")
        if set(payload) != {"answer"}:
            raise PlanningError("answer generator output contains unexpected fields")
        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise PlanningError("answer generator output must include a non-empty answer")
        answer = answer.strip()
        if len(answer) > 1800:
            raise PlanningError("answer generator output exceeds the answer limit")
        if any(marker in answer for marker in ("memory://", "artifact://", "result_ref")):
            raise PlanningError("answer generator output contains an internal reference")
        return AnswerGenerationResult(
            answer=answer,
            evidence=project_answer_generation_evidence(
                self._client_metrics(),
                status="success",
                available=True,
            ),
        )

    def failure_evidence(self, reason_code: str) -> dict[str, Any]:
        """Expose only bounded client metrics for Runtime fallback handling."""

        return fallback_answer_generation_evidence(
            reason_code,
            metrics=self._client_metrics(),
        )

    def _client_metrics(self) -> Mapping[str, Any]:
        metrics = getattr(self._client, "metrics", None)
        value = metrics() if callable(metrics) else {}
        return value if isinstance(value, Mapping) else {}


def fallback_answer_generation_evidence(
    reason_code: str,
    *,
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return safe evidence when template fallback was used."""

    evidence = project_answer_generation_evidence(
        metrics or {},
        status="fallback",
        available=False,
    )
    evidence["reason_code"] = _safe_text(reason_code, 96) or "generation_unavailable"
    return evidence


def project_answer_generation_evidence(
    value: Mapping[str, Any] | None,
    *,
    status: str | None = None,
    available: bool | None = None,
) -> dict[str, Any]:
    """Allowlist answer-generation metrics for result/async/artifact surfaces."""

    source = value if isinstance(value, Mapping) else {}
    normalized_status = _safe_text(
        status if status is not None else source.get("status", "unavailable"),
        32,
    )
    execution_mode = source.get("execution_mode")
    existing_mode = source.get("mode")
    result: dict[str, Any] = {
        "schema_version": ANSWER_GENERATION_SCHEMA_VERSION,
        "available": bool(
            available if available is not None else source.get("available", False)
        ),
        "status": normalized_status,
        "mode": (
            "template_fallback"
            if normalized_status == "fallback"
            else existing_mode
            if existing_mode in {"live_model", "template_fallback"}
            else "live_model"
            if execution_mode == "live_model"
            else "template_fallback"
            if normalized_status == "fallback"
            else "unknown"
        ),
    }
    for key in ("provider", "model", "wire_api", "error_type", "reason_code"):
        if source.get(key):
            result[key] = _safe_text(source[key], 96)
    for key in ("attempts", "retries"):
        try:
            number = int(source.get(key))
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 32:
            result[key] = number
    try:
        latency = float(source.get("latency_ms"))
        if math.isfinite(latency) and latency >= 0:
            result["latency_ms"] = round(min(latency, 86_400_000), 3)
    except (TypeError, ValueError):
        pass
    usage = source.get("usage")
    if isinstance(usage, Mapping):
        safe_usage = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                number = int(usage.get(key))
            except (TypeError, ValueError):
                continue
            if 0 <= number <= 10_000_000:
                safe_usage[key] = number
        if safe_usage:
            result["usage"] = safe_usage
    return result


def _project_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    normalized_key = str(key or "").lower()
    if normalized_key in _OMITTED_KEYS or any(token in normalized_key for token in ("password", "secret", "token")):
        return None
    if value is None or isinstance(value, (bool, int, str)):
        return _safe_text(value, _MAX_STRING_CHARS) if isinstance(value, str) else value
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if depth >= 4:
        return "…"
    if isinstance(value, Mapping):
        projected = {}
        for name, child in list(value.items())[:_MAX_MAPPING_ITEMS]:
            child_key = str(name)[:96]
            child_value = _project_value(child, key=child_key, depth=depth + 1)
            if child_value is not None:
                projected[child_key] = child_value
        return projected
    if isinstance(value, (list, tuple)):
        return [
            child
            for child in (
                _project_value(item, key=normalized_key, depth=depth + 1)
                for item in list(value)[:_MAX_LIST_ITEMS]
            )
            if child is not None
        ]
    return _safe_text(value, _MAX_STRING_CHARS)


def _safe_text(value: Any, limit: int) -> str:
    text = str(value or "")
    return text[:limit]


__all__ = [
    "ANSWER_GENERATION_SCHEMA_VERSION",
    "ANSWER_GENERATION_SCHEMA",
    "AnswerGenerationResult",
    "LLMAnswerGenerator",
    "build_answer_context",
    "fallback_answer_generation_evidence",
    "project_answer_generation_evidence",
]
