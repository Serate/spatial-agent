"""Controlled natural-language answer generation for completed runs.

The Runtime owns facts and evidence.  This module only projects a bounded,
redacted fact packet to a structured model call and validates the returned
user-facing answer.  Callers must keep a deterministic Domain Composer as the
fallback when the model is unavailable or returns an unsafe shape.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import PlanningError


ANSWER_GENERATION_SCHEMA_VERSION = "spatial-agent.answer-generation.v1"
COMPOSITE_ANSWER_SCHEMA_VERSION = "spatial-agent.composite-answer.v1"
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
COMPOSITE_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["answer"],
    "additionalProperties": False,
    "properties": {
        "answer": {
            "type": "object",
            "required": ["headline", "summary", "key_findings", "limitations"],
            "additionalProperties": False,
            "properties": {
                "headline": {"type": "string", "maxLength": 160},
                "summary": {"type": "string", "maxLength": 800},
                "key_findings": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {"type": "string", "maxLength": 320},
                },
                "limitations": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {"type": "string", "maxLength": 320},
                },
                "next_steps": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {"type": "string", "maxLength": 320},
                },
            },
        }
    },
}

_MAX_REQUEST_CHARS = 800
_MAX_CONTEXT_CHARS = 12000
_MAX_COMPONENTS = 8
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


@dataclass(frozen=True)
class CompositeAnswerGenerationResult:
    """Validated structured answer for a Composite Result."""

    answer: dict[str, Any]
    evidence: dict[str, Any]


def build_composite_answer_context(result: Mapping[str, Any]) -> dict[str, Any]:
    """Project only Composite facts needed for a user-facing answer."""

    from agent.composite_view import build_composite_view_projection

    projection = build_composite_view_projection(result)
    sections = [
        {
            "component_id": item.get("component_id"),
            "state": item.get("state"),
            "status": item.get("status"),
            "result_type": item.get("result_type"),
            "data_profile": item.get("data_profile"),
            "answer": item.get("answer"),
        }
        for item in projection.get("sections", [])
        if isinstance(item, Mapping) and item.get("kind") == "component"
    ]
    return {
        "schema_version": COMPOSITE_ANSWER_SCHEMA_VERSION,
        "state": projection.get("state"),
        "status": projection.get("status"),
        "components": sections[:_MAX_COMPONENTS],
        "fallback_answer": projection.get("answer"),
    }


class LLMCompositeAnswerGenerator:
    """Generate a bounded Composite answer without exposing internal refs."""

    def __init__(self, client: Any):
        self._client = client

    def generate(self, result: Mapping[str, Any]) -> CompositeAnswerGenerationResult:
        context = build_composite_answer_context(result)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是面向普通用户的分析结果解读助手。只能根据可信 Composite facts 回答，"
                    "不得补造事实、数量、坐标或规划许可结论。返回严格 JSON，只有 answer 字段，"
                    "answer 必须包含 headline、summary、key_findings、limitations；可选 next_steps；不要输出工具名、"
                    "fingerprint、result_ref、artifact 引用、prompt 或模型内部过程。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        payload = self._client.complete_json(messages, COMPOSITE_ANSWER_SCHEMA)
        if not isinstance(payload, Mapping) or set(payload) != {"answer"}:
            raise PlanningError("composite answer output contains unexpected fields")
        answer = _normalize_composite_answer(payload.get("answer"))
        encoded = json.dumps(answer, ensure_ascii=False)
        if any(marker in encoded for marker in ("memory://", "artifact://", "result_ref", "prompt")):
            raise PlanningError("composite answer contains an internal reference")
        return CompositeAnswerGenerationResult(
            answer=answer,
            evidence=project_answer_generation_evidence(
                self._client_metrics(), status="success", available=True
            ),
        )

    def generate_stream(
        self,
        result: Mapping[str, Any],
        *,
        on_delta,
    ) -> CompositeAnswerGenerationResult:
        """Stream a user-facing summary after Composite execution is complete.

        Composite facts and the final structured answer remain authoritative.
        The streamed text only fills the human-readable summary; deterministic
        key findings and limitations are retained as the structured fallback.
        """

        context = build_composite_answer_context(result)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是面向普通用户的分析结果解读助手。只能根据提供的可信事实，"
                    "用自然中文输出一段简洁总结，不要输出 JSON、工具名、内部引用、Prompt、"
                    "隐藏思维过程或未经事实支持的结论。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        stream = getattr(self._client, "stream_text", None)
        if not callable(stream):
            generated = self.generate(result)
            if callable(on_delta):
                on_delta(generated.answer.get("summary", ""))
            evidence = dict(generated.evidence)
            evidence["streaming"] = False
            return CompositeAnswerGenerationResult(
                answer=generated.answer,
                evidence=evidence,
            )
        chunks: list[str] = []
        size = 0
        try:
            for chunk in stream(messages, max_chars=800):
                text = _normalize_stream_text(chunk, max_length=min(800 - size, 800))
                if not text:
                    continue
                candidate = "".join(chunks) + text
                if _contains_internal_reference(candidate):
                    raise PlanningError("answer stream contains an internal reference")
                chunks.append(text)
                size += len(text)
                if callable(on_delta):
                    on_delta(text)
                if size >= 800:
                    break
        except (AttributeError, NotImplementedError) as exc:
            return self._fallback_stream(result, on_delta, exc)
        except PlanningError as exc:
            if _is_stream_unsupported(exc):
                return self._fallback_stream(result, on_delta, exc)
            raise
        summary = _normalize_stream_text("".join(chunks), max_length=800)
        if not summary:
            raise PlanningError("answer stream returned an empty summary")
        if _contains_internal_reference(summary):
            raise PlanningError("answer stream contains an internal reference")
        base = fallback_composite_answer(result, "streamed_summary").answer
        answer = dict(base)
        answer["summary"] = summary
        answer["headline"] = summary.splitlines()[0][:160] or answer.get("headline", "分析结果")
        return CompositeAnswerGenerationResult(
            answer=_normalize_composite_answer(answer),
            evidence=project_answer_generation_evidence(
                {**self._client_metrics(), "streaming": True},
                status="success",
                available=True,
            ),
        )

    def _client_metrics(self) -> Mapping[str, Any]:
        metrics = getattr(self._client, "metrics", None)
        value = metrics() if callable(metrics) else {}
        return value if isinstance(value, Mapping) else {}

    def _fallback_stream(self, result: Mapping[str, Any], on_delta, cause: Exception) -> CompositeAnswerGenerationResult:
        generated = self.generate(result)
        if callable(on_delta):
            on_delta(generated.answer.get("summary", ""))
        evidence = dict(generated.evidence)
        evidence["streaming"] = False
        evidence["fallback_reason"] = "stream_unsupported"
        return CompositeAnswerGenerationResult(answer=generated.answer, evidence=evidence)


def fallback_composite_answer(
    result: Mapping[str, Any], reason_code: str = "generation_unavailable"
) -> CompositeAnswerGenerationResult:
    """Use the deterministic Composite projection when model generation fails."""

    from agent.composite_view import build_composite_view_projection

    projection = build_composite_view_projection(result)
    return CompositeAnswerGenerationResult(
        answer=dict(projection["answer"]),
        evidence=fallback_answer_generation_evidence(reason_code),
    )


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

    def generate_stream(self, result: Any, *, on_delta) -> AnswerGenerationResult:
        """Generate a bounded natural-language answer through provider deltas."""

        stream = getattr(self._client, "stream_text", None)
        if not callable(stream):
            generated = self.generate(result)
            if callable(on_delta):
                on_delta(generated.answer)
            evidence = dict(generated.evidence)
            evidence["streaming"] = False
            return AnswerGenerationResult(answer=generated.answer, evidence=evidence)
        context = build_answer_context(result)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是面向普通用户的分析结果解读助手。只根据可信事实，用自然中文输出简洁答案；"
                    "不要输出 JSON、工具名、内部引用、Prompt、隐藏思维过程或未经事实支持的结论。"
                    "数据不完整时明确说明影响。答案不超过 1800 字。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        chunks: list[str] = []
        size = 0
        try:
            for chunk in stream(messages, max_chars=1800):
                text = _normalize_stream_text(chunk, max_length=min(1800 - size, 1800))
                if not text:
                    continue
                candidate = "".join(chunks) + text
                if _contains_internal_reference(candidate):
                    raise PlanningError("answer stream contains an internal reference")
                chunks.append(text)
                size += len(text)
                if callable(on_delta):
                    on_delta(text)
                if size >= 1800:
                    break
        except (AttributeError, NotImplementedError) as exc:
            return self._fallback_stream(result, on_delta, exc)
        except PlanningError as exc:
            if _is_stream_unsupported(exc):
                return self._fallback_stream(result, on_delta, exc)
            raise
        answer = _normalize_stream_text("".join(chunks), max_length=1800)
        if not answer:
            raise PlanningError("answer stream returned an empty answer")
        if _contains_internal_reference(answer):
            raise PlanningError("answer stream contains an internal reference")
        return AnswerGenerationResult(
            answer=answer,
            evidence=project_answer_generation_evidence(
                {**self._client_metrics(), "streaming": True},
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

    def _fallback_stream(self, result: Any, on_delta, cause: Exception) -> AnswerGenerationResult:
        generated = self.generate(result)
        if callable(on_delta):
            on_delta(generated.answer)
        evidence = dict(generated.evidence)
        evidence["streaming"] = False
        evidence["fallback_reason"] = "stream_unsupported"
        return AnswerGenerationResult(answer=generated.answer, evidence=evidence)


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
    evidence["reason_code"] = _safe_reason_code(reason_code)
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
            safe_value = _safe_evidence_text(source[key])
            if safe_value:
                result[key] = safe_value
    if normalized_status == "fallback" and "reason_code" not in result:
        result["reason_code"] = "generation_unavailable"
    if isinstance(source.get("streaming"), bool):
        result["streaming"] = source["streaming"]
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


def _safe_evidence_text(value: Any) -> str:
    text = _safe_text(value, 96)
    lowered = text.lower()
    if any(marker in lowered for marker in ("prompt", "memory://", "artifact://", "result_ref", "tool_args")):
        return ""
    return text


def _safe_reason_code(value: Any) -> str:
    text = _safe_text(value, 96)
    return text if re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", text) else "generation_unavailable"


def _normalize_stream_text(value: Any, *, max_length: int) -> str:
    """Normalize a visible delta without persisting provider metadata."""

    if not isinstance(value, str) or max_length <= 0:
        return ""
    return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")[:max_length]


def _contains_internal_reference(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("memory://", "artifact://", "result_ref", "prompt"))


def _is_stream_unsupported(error: PlanningError) -> bool:
    return getattr(error, "code", None) == "stream_unsupported"


def _normalize_composite_answer(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PlanningError("composite answer must be an object")
    allowed = {"headline", "summary", "key_findings", "limitations", "next_steps"}
    required = {"headline", "summary", "key_findings", "limitations"}
    if not required.issubset(set(value)) or not set(value).issubset(allowed):
        raise PlanningError("composite answer fields are invalid")
    answer: dict[str, Any] = {
        "headline": _safe_text(value.get("headline"), 160).strip(),
        "summary": _safe_text(value.get("summary"), 800).strip(),
    }
    if not answer["headline"] or not answer["summary"]:
        raise PlanningError("composite answer headline and summary are required")
    for key in ("key_findings", "limitations", "next_steps"):
        values = value.get(key)
        if values is None and key == "next_steps":
            values = []
        if not isinstance(values, list):
            raise PlanningError("composite answer lists are invalid")
        answer[key] = [_safe_text(item, 320).strip() for item in values[:8] if _safe_text(item, 320).strip()]
    return answer


__all__ = [
    "ANSWER_GENERATION_SCHEMA_VERSION",
    "ANSWER_GENERATION_SCHEMA",
    "COMPOSITE_ANSWER_SCHEMA_VERSION",
    "COMPOSITE_ANSWER_SCHEMA",
    "AnswerGenerationResult",
    "CompositeAnswerGenerationResult",
    "LLMCompositeAnswerGenerator",
    "LLMAnswerGenerator",
    "build_composite_answer_context",
    "build_answer_context",
    "fallback_composite_answer",
    "fallback_answer_generation_evidence",
    "project_answer_generation_evidence",
]
