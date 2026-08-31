"""Controlled natural-language answer generation for completed runs.

The Runtime owns facts and evidence.  This module only projects a bounded,
redacted fact packet to a structured model call and validates the returned
user-facing answer.  Callers must keep a deterministic Domain Composer as the
fallback when the model is unavailable or returns an unsafe shape.
"""

from __future__ import annotations

import json
import inspect
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .errors import PlanningError
from agent.integration.structured_response import (
    call_structured_json,
    repair_structured_fields,
)
from .result_completeness import build_result_completeness
from .result_summary import build_result_summary
from .answer_quality import assess_answer, project_answer_quality
from .runtime_core.run_budget import RunBudget
from agent.evidence.answer_evidence import (
    ANSWER_GENERATION_SCHEMA_VERSION,
    fallback_answer_generation_evidence,
    project_answer_generation_evidence,
    _project_value,
    _safe_text,
    _safe_evidence_text,
    _safe_reason_code,
    _normalize_stream_text,
    _contains_internal_reference,
    _is_stream_fallback_eligible,
    _stream_fallback_reason,
    _normalize_composite_answer,
)


COMPOSITE_ANSWER_SCHEMA_VERSION = "spatial-agent.composite-answer.v1"
_MAX_ANSWER_CHARS = 6000
ANSWER_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["answer"],
    "additionalProperties": False,
    "properties": {
        "answer": {
            "type": "string",
            "minLength": 1,
            "maxLength": _MAX_ANSWER_CHARS,
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

    from agent.application.composite_view import build_composite_view_projection

    projection = build_composite_view_projection(result)
    result_summary = projection.get("result_summary")
    result_summary = (
        result_summary if isinstance(result_summary, Mapping)
        else build_result_summary(result)
    )
    sections = [
        dict(item)
        for item in result_summary.get("blocks", [])
        if isinstance(item, Mapping)
    ]
    return {
        "schema_version": COMPOSITE_ANSWER_SCHEMA_VERSION,
        "state": projection.get("state"),
        "status": projection.get("status"),
        "completeness": projection.get("completeness"),
        "components": sections[:_MAX_COMPONENTS],
        "result_summary": dict(result_summary),
        "fallback_answer": projection.get("answer"),
    }


class LLMCompositeAnswerGenerator:
    """Generate a bounded Composite answer without exposing internal refs."""

    def __init__(self, client: Any):
        self._client = client
        self._structured_recovery_attempts = 0

    def generate(
        self,
        result: Mapping[str, Any],
        *,
        budget: Optional[RunBudget] = None,
        progress: Any = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> CompositeAnswerGenerationResult:
        context = build_composite_answer_context(result)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是面向普通用户的分析结果解读助手。只能根据可信 Composite facts 回答，"
                    "不得补造事实、数量、坐标或规划许可结论。返回严格 JSON，只有 answer 字段，"
                    "answer 必须包含 headline、summary、key_findings、limitations；可选 next_steps；不要输出工具名、"
                    "fingerprint、result_ref、artifact 引用、prompt 或模型内部过程。若 completeness.state 为 partial、"
                    "优先依据 result_summary 的结论、关键发现、限制和 evidence 组织答案；facts 只用于必要的技术细节。"
                    "如果 evidence_bundle 中存在 stale、partial、unavailable、unknown 或冲突来源，"
                    "只用通俗中文说明其对结论的影响；不得把 unknown 说成最新，也不得自行裁决冲突。"
                    "blocked 或 waiting_decision，必须明确说明已完成范围、未完成范围和是否可以继续，不得写成全部完成。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        options = _answer_budget_options(budget, progress=progress)
        _answer_begin_attempt(budget, progress)
        try:
            call = call_structured_json(
                self._client,
                messages,
                COMPOSITE_ANSWER_SCHEMA,
                schema_name="composite_answer",
                recovery_messages=messages,
                on_recovery=lambda: _answer_begin_attempt(
                    budget, progress, retry=True
                ),
                on_progress=_answer_provider_progress(
                    progress, on_progress, phase="answer"
                ),
                timeout_provider=(
                    lambda: budget.child_timeout(kind="provider")
                    if budget is not None
                    else None
                ),
                **options,
            )
        except PlanningError:
            _answer_check_budget(budget)
            raise
        self._structured_recovery_attempts = call.recovery_attempts
        _answer_check_budget(budget)
        payload = call.payload
        if "answer" not in payload:
            repaired = repair_structured_fields(
                payload,
                {"answer": ("content", "text", "response")},
            )
            if repaired is not None:
                payload = repaired
        if not isinstance(payload, Mapping) or set(payload) != {"answer"}:
            raise PlanningError(
                "composite answer output contains unexpected fields",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            )
        try:
            answer = _normalize_composite_answer(payload.get("answer"))
        except PlanningError as exc:
            raise PlanningError(
                "composite answer failed contract validation",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            ) from exc
        encoded = json.dumps(answer, ensure_ascii=False)
        if any(marker in encoded for marker in ("memory://", "artifact://", "result_ref", "prompt")):
            raise PlanningError(
                "composite answer contains an internal reference",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            )
        return CompositeAnswerGenerationResult(
            answer=answer,
            evidence=project_answer_generation_evidence(
                {
                    **self._client_metrics(),
                    "compact_recovery_attempts": self._structured_recovery_attempts,
                    "quality": assess_answer(answer.get("summary"), context),
                },
                status="success",
                available=True,
            ),
        )

    def generate_stream(
        self,
        result: Mapping[str, Any],
        *,
        on_delta,
        budget: Optional[RunBudget] = None,
        progress: Any = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
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
                    "隐藏思维过程或未经事实支持的结论。优先依据结论、关键发现、限制和证据来源组织总结；"
                    "如果来源质量为 stale、partial、unavailable 或 unknown，简短说明影响；冲突来源并列说明，"
                    "不要自行判断哪一方正确。若结果不完整，明确说明已完成内容、缺失范围和后续动作。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        stream = getattr(self._client, "stream_text", None)
        if not callable(stream):
            generated = self.generate(
                result,
                budget=budget,
                progress=progress,
                on_progress=on_progress,
            )
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
        options = _answer_budget_options(budget, progress=progress)
        _answer_begin_attempt(budget, progress)
        try:
            for chunk in _invoke_text_stream(
                stream,
                messages,
                max_chars=800,
                timeout_seconds=options.get("timeout_seconds"),
                deadline=options.get("deadline"),
                on_progress=_answer_provider_progress(
                    progress, on_progress, phase="answer"
                ),
            ):
                _answer_check_budget(budget)
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
            return self._fallback_stream(
                result,
                on_delta,
                exc,
                budget=budget,
                progress=progress,
                on_progress=on_progress,
            )
        except PlanningError as exc:
            if _is_stream_fallback_eligible(exc):
                return self._fallback_stream(
                    result,
                    on_delta,
                    exc,
                    budget=budget,
                    progress=progress,
                    on_progress=on_progress,
                )
            raise
        summary = _normalize_stream_text("".join(chunks), max_length=800)
        if not summary:
            raise PlanningError("answer stream returned an empty summary")
        if _contains_internal_reference(summary):
            raise PlanningError("answer stream contains an internal reference")
        _answer_check_budget(budget)
        base = fallback_composite_answer(result, "streamed_summary").answer
        answer = dict(base)
        answer["summary"] = summary
        answer["headline"] = summary.splitlines()[0][:160] or answer.get("headline", "分析结果")
        return CompositeAnswerGenerationResult(
            answer=_normalize_composite_answer(answer),
            evidence=project_answer_generation_evidence(
                {
                    **self._client_metrics(),
                    "streaming": True,
                    "quality": assess_answer(answer.get("summary"), context),
                },
                status="success",
                available=True,
            ),
        )

    def _client_metrics(self) -> Mapping[str, Any]:
        metrics = getattr(self._client, "metrics", None)
        value = metrics() if callable(metrics) else {}
        return value if isinstance(value, Mapping) else {}

    def _fallback_stream(
        self,
        result: Mapping[str, Any],
        on_delta,
        cause: Exception,
        *,
        budget: Optional[RunBudget] = None,
        progress: Any = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> CompositeAnswerGenerationResult:
        generated = self.generate(
            result,
            budget=budget,
            progress=progress,
            on_progress=on_progress,
        )
        if callable(on_delta):
            on_delta(generated.answer.get("summary", ""))
        evidence = dict(generated.evidence)
        evidence["streaming"] = False
        evidence["fallback_reason"] = _stream_fallback_reason(cause)
        return CompositeAnswerGenerationResult(answer=generated.answer, evidence=evidence)


def fallback_composite_answer(
    result: Mapping[str, Any], reason_code: str = "generation_unavailable"
) -> CompositeAnswerGenerationResult:
    """Use the deterministic Composite projection when model generation fails."""

    from agent.application.composite_view import build_composite_view_projection

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

    result_payload = _result_payload_for_summary(result, plan=plan, steps=steps)
    execution_status = _safe_text(
        getattr(
            getattr(result, "status", None),
            "value",
            getattr(result, "status", ""),
        ),
        32,
    )
    # ``run_lifecycle`` marks a run EXECUTING while it emits answer deltas.
    # Tool execution has already ended at this point, so exposing that raw
    # lifecycle status to the answer model can produce the false user-facing
    # claim that the analysis is still running.  Keep the durable result
    # contract untouched and project an explicit finalization state instead.
    answer_finalizing = execution_status == "EXECUTING"
    if answer_finalizing:
        result_payload["status"] = "COMPLETED"

    packet: dict[str, Any] = {
        "schema_version": ANSWER_GENERATION_SCHEMA_VERSION,
        "request": _safe_text(getattr(result, "request", ""), _MAX_REQUEST_CHARS),
        "goal": _safe_text(getattr(plan, "goal", "") if plan else "", 400),
        "result_type": _safe_text(output.get("type"), 96),
        "status": "FINALIZING" if answer_finalizing else execution_status,
        "answer_phase": "finalizing" if answer_finalizing else "complete",
        "execution_complete": answer_finalizing or execution_status == "COMPLETED",
        "completeness": build_result_completeness(result_payload),
        "assumptions": [
            _safe_text(item, 200)
            for item in (getattr(plan, "assumptions", []) or [])[:8]
            if isinstance(item, (str, int, float))
        ],
        "steps": steps,
        "result_summary": build_result_summary(result_payload),
    }
    transient_documents = getattr(result, "_transient_model_context", None)
    if isinstance(transient_documents, list):
        packet["web_documents"] = _project_web_documents(transient_documents)
    # Keep the serialized packet bounded even when a custom Domain returns a
    # particularly wide scalar result.
    _fit_answer_context(packet, steps)
    return packet


def _project_web_documents(value: Any) -> list[dict[str, str]]:
    """Keep page text useful while reserving a bounded answer context."""

    result: list[dict[str, str]] = []
    remaining = 6000
    for item in value[-8:] if isinstance(value, list) else []:
        if remaining <= 0 or not isinstance(item, Mapping):
            break
        text = _safe_text(item.get("text"), min(6000, remaining))
        if not text:
            continue
        result.append(
            {
                "url": _safe_text(item.get("url"), _MAX_REQUEST_CHARS),
                "domain": _safe_text(item.get("domain"), 255),
                "title": _safe_text(item.get("title"), 240),
                "text": text,
            }
        )
        remaining -= len(text)
    return result


def _fit_answer_context(packet: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    """Reduce optional detail structurally and guarantee the packet limit."""

    def size() -> int:
        return len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")))

    def compact_steps() -> None:
        packet["steps"] = [
            {
                key: item[key]
                for key in ("id", "tool", "status", "error")
                if key in item
            }
            for item in packet.get("steps", [])
            if isinstance(item, Mapping)
        ]

    def fit_web_documents() -> None:
        documents = packet.get("web_documents")
        if not isinstance(documents, list):
            return
        projected = [
            {
                key: item[key]
                for key in ("url", "domain", "title")
                if key in item
            }
            for item in documents
            if isinstance(item, Mapping)
        ]
        texts = [
            _safe_text(item.get("text"), 6000)
            if isinstance(item, Mapping)
            else ""
            for item in documents
        ]
        # Keep the earliest source cards that fit before trimming their body.
        # This gives the model at least one useful page whenever metadata can
        # fit, instead of discarding every body as soon as the packet is wide.
        selected_count = 0
        for count in range(len(projected), 0, -1):
            packet["web_documents"] = projected[:count]
            if size() <= _MAX_CONTEXT_CHARS:
                selected_count = count
                break
        if selected_count == 0:
            packet.pop("web_documents", None)
            return

        selected = projected[:selected_count]
        selected_texts = texts[:selected_count]
        total_text = sum(len(text) for text in selected_texts)
        if total_text <= 0:
            packet["web_documents"] = selected
            return

        def with_text_budget(budget: int) -> list[dict[str, str]]:
            remaining = max(0, int(budget))
            result: list[dict[str, str]] = []
            for index, metadata in enumerate(selected):
                slots = selected_count - index
                amount = min(len(selected_texts[index]), (remaining + slots - 1) // slots)
                item = dict(metadata)
                if amount:
                    item["text"] = selected_texts[index][:amount]
                result.append(item)
                remaining -= amount
            return result

        low, high = 0, total_text
        best = selected
        while low <= high:
            middle = (low + high) // 2
            candidate = with_text_budget(middle)
            packet["web_documents"] = candidate
            if size() <= _MAX_CONTEXT_CHARS:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        packet["web_documents"] = best

    if size() <= _MAX_CONTEXT_CHARS:
        return
    summary = packet.get("result_summary")
    if isinstance(summary, dict):
        for block in summary.get("blocks", []):
            if isinstance(block, dict):
                block["facts"] = {}
                evidence = block.get("evidence")
                if isinstance(evidence, dict):
                    bundle = evidence.get("evidence_bundle")
                    if isinstance(bundle, dict) and isinstance(bundle.get("entries"), list):
                        # Page bodies live in the transient model context; the
                        # answer model needs bundle quality, not duplicate
                        # source cards in every step summary.
                        bundle["entries"] = []
                    records = evidence.get("source_records")
                    if isinstance(records, list):
                        evidence["source_records"] = [
                            {
                                key: item[key]
                                for key in ("source_id", "title", "url", "domain", "quality")
                                if isinstance(item, Mapping) and key in item
                            }
                            for item in records
                            if isinstance(item, Mapping)
                        ]
        summary["blocks"] = list(summary.get("blocks", []))[:8]
    packet["steps"] = steps[:8]
    if size() <= _MAX_CONTEXT_CHARS:
        return

    # Execution facts are useful, but the transient page body is the only
    # source text available to an answer model. Compact facts before removing
    # that body so a bounded, non-empty excerpt survives when possible.
    compact_steps()
    fit_web_documents()
    if size() <= _MAX_CONTEXT_CHARS:
        return

    packet["assumptions"] = list(packet.get("assumptions") or [])[:3]
    packet["goal"] = _safe_text(packet.get("goal"), 240)
    packet["request"] = _safe_text(packet.get("request"), 400)
    fit_web_documents()
    if size() <= _MAX_CONTEXT_CHARS:
        return

    # A custom Domain can still publish unusually wide summary metadata. At
    # this point retain only the stable fields needed to explain the request;
    # this final projection makes the bound an invariant rather than a best
    # effort for ordinary payloads.
    compact = {
        "schema_version": ANSWER_GENERATION_SCHEMA_VERSION,
        "request": _safe_text(packet.get("request"), 400),
        "goal": _safe_text(packet.get("goal"), 240),
        "result_type": _safe_text(packet.get("result_type"), 96),
        "status": _safe_text(packet.get("status"), 32),
        "answer_phase": _safe_text(packet.get("answer_phase"), 32),
        "execution_complete": bool(packet.get("execution_complete")),
    }
    packet.clear()
    packet.update(compact)


def _result_payload_for_summary(
    result: Any, *, plan: Any, steps: list[dict[str, Any]]
) -> dict[str, Any]:
    """Adapt legacy result-like test objects to the shared summary seam."""

    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, Mapping):
            return dict(value)
    output = getattr(plan, "output", {}) if plan is not None else {}
    output = dict(output) if isinstance(output, Mapping) else {}
    return {
        "request": _safe_text(getattr(result, "request", ""), _MAX_REQUEST_CHARS),
        "status": _safe_text(
            getattr(getattr(result, "status", None), "value", getattr(result, "status", "")),
            32,
        ),
        "plan": {
            "goal": _safe_text(getattr(plan, "goal", "") if plan else "", 400),
            "output": output,
        },
        "steps": [
            {
                "id": item.get("id"),
                "tool": item.get("tool"),
                "status": item.get("status"),
                "result": item.get("facts") or {},
                "error": item.get("error"),
            }
            for item in steps
        ],
    }


class LLMAnswerGenerator:
    """Generate a concise answer from a validated, bounded fact packet."""

    def __init__(self, client: Any):
        self._client = client
        self._structured_recovery_attempts = 0

    def generate(
        self,
        result: Any,
        *,
        budget: Optional[RunBudget] = None,
        progress: Any = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> AnswerGenerationResult:
        context = build_answer_context(result)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是面向普通用户的分析结果解读助手。只根据可信事实回答，不得补造事实、坐标、"
                    "数量或规划结论。结论优先，把说明要点写在 answer 字符串中；内部状态、工具名、"
                    "result_ref、memory:// 和 JSON 字段都要翻译成自然中文。若数据不完整，明确说明影响。"
                    "对于不依赖外部数据的概念解释、比较、总结、写作和简单算术，可以根据用户请求直接回答；"
                    "不要因为事实包为空就把这类问题误报为没有结果。涉及实时、地域或专门外部事实时，"
                    "只有在已有证据支持时才下结论，并明确说明缺少的数据。"
                    "优先依据 result_summary 的结论、关键发现、限制和 evidence 组织答案；facts 只用于必要的技术细节。"
                    "若 completeness.state 为 partial、blocked 或 waiting_decision，必须区分已完成内容与未完成范围，"
                    "不得声称全部分析已完成。若 answer_phase 为 finalizing 或 execution_complete 为 true，说明工具执行已经结束，"
                    "只能总结已得到的结果，不得说分析仍在执行。"
                    "只返回一个 JSON 对象，且只能有 answer 字段；answer 必须是 6000 字符以内的非空字符串。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        options = _answer_budget_options(budget, progress=progress)
        _answer_begin_attempt(budget, progress)
        try:
            call = call_structured_json(
                self._client,
                messages,
                ANSWER_GENERATION_SCHEMA,
                schema_name="answer_generation",
                recovery_messages=messages,
                on_recovery=lambda: _answer_begin_attempt(
                    budget, progress, retry=True
                ),
                on_progress=_answer_provider_progress(
                    progress, on_progress, phase="answer"
                ),
                timeout_provider=(
                    lambda: budget.child_timeout(kind="provider")
                    if budget is not None
                    else None
                ),
                **options,
            )
        except PlanningError:
            _answer_check_budget(budget)
            raise
        self._structured_recovery_attempts = call.recovery_attempts
        _answer_check_budget(budget)
        payload = call.payload
        if "answer" not in payload:
            repaired = repair_structured_fields(
                payload,
                {"answer": ("content", "text", "response")},
            )
            if repaired is not None:
                payload = repaired
        if not isinstance(payload, Mapping):
            raise PlanningError(
                "answer generator output must be an object",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            )
        if set(payload) != {"answer"}:
            raise PlanningError(
                "answer generator output contains unexpected fields",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            )
        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise PlanningError(
                "answer generator output must include a non-empty answer",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            )
        answer = answer.strip()
        if len(answer) > _MAX_ANSWER_CHARS:
            raise PlanningError(
                "answer generator output exceeds the answer limit",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            )
        if any(marker in answer for marker in ("memory://", "artifact://", "result_ref")):
            raise PlanningError(
                "answer generator output contains an internal reference",
                category="answer",
                code="invalid_model_response",
                retryable=False,
            )
        return AnswerGenerationResult(
            answer=answer,
            evidence=project_answer_generation_evidence(
                {
                    **self._client_metrics(),
                    "compact_recovery_attempts": self._structured_recovery_attempts,
                    "quality": assess_answer(answer, context),
                },
                status="success",
                available=True,
            ),
        )

    def generate_stream(
        self,
        result: Any,
        *,
        on_delta,
        budget: Optional[RunBudget] = None,
        progress: Any = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> AnswerGenerationResult:
        """Generate a bounded natural-language answer through provider deltas."""

        stream = getattr(self._client, "stream_text", None)
        if not callable(stream):
            generated = self.generate(
                result,
                budget=budget,
                progress=progress,
                on_progress=on_progress,
            )
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
                    "对于不依赖外部数据的概念解释、比较、总结、写作和简单算术，可以直接完成回答；"
                    "不要因为事实包为空就声称没有结果。涉及实时、地域或专门外部事实时，明确说明证据范围和限制。"
                    "优先根据 result_summary 的结论、关键发现、限制和证据来源回答，技术 facts 只作必要补充；"
                    "遵守 evidence_bundle 的质量状态：unknown 不是最新，stale/partial/unavailable 和来源冲突必须说明影响。"
                    "数据不完整时明确说明影响。若 answer_phase 为 finalizing 或 execution_complete 为 true，说明工具执行已经结束，"
                    "不要告诉用户分析仍在执行。答案不超过 6000 字。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        chunks: list[str] = []
        size = 0
        options = _answer_budget_options(budget, progress=progress)
        _answer_begin_attempt(budget, progress)
        try:
            for chunk in _invoke_text_stream(
                stream,
                messages,
                max_chars=_MAX_ANSWER_CHARS,
                timeout_seconds=options.get("timeout_seconds"),
                deadline=options.get("deadline"),
                on_progress=_answer_provider_progress(
                    progress, on_progress, phase="answer"
                ),
            ):
                _answer_check_budget(budget)
                text = _normalize_stream_text(
                    chunk, max_length=min(_MAX_ANSWER_CHARS - size, _MAX_ANSWER_CHARS)
                )
                if not text:
                    continue
                candidate = "".join(chunks) + text
                if _contains_internal_reference(candidate):
                    raise PlanningError("answer stream contains an internal reference")
                chunks.append(text)
                size += len(text)
                if callable(on_delta):
                    on_delta(text)
                if size >= _MAX_ANSWER_CHARS:
                    break
        except (AttributeError, NotImplementedError) as exc:
            return self._fallback_stream(
                result,
                on_delta,
                exc,
                budget=budget,
                progress=progress,
                on_progress=on_progress,
            )
        except PlanningError as exc:
            if _is_stream_fallback_eligible(exc):
                return self._fallback_stream(
                    result,
                    on_delta,
                    exc,
                    budget=budget,
                    progress=progress,
                    on_progress=on_progress,
                )
            raise
        answer = _normalize_stream_text("".join(chunks), max_length=_MAX_ANSWER_CHARS)
        if not answer:
            raise PlanningError("answer stream returned an empty answer")
        if _contains_internal_reference(answer):
            raise PlanningError("answer stream contains an internal reference")
        _answer_check_budget(budget)
        return AnswerGenerationResult(
            answer=answer,
            evidence=project_answer_generation_evidence(
                {
                    **self._client_metrics(),
                    "streaming": True,
                    "quality": assess_answer(answer, context),
                },
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

    def _fallback_stream(
        self,
        result: Any,
        on_delta,
        cause: Exception,
        *,
        budget: Optional[RunBudget] = None,
        progress: Any = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> AnswerGenerationResult:
        generated = self.generate(
            result,
            budget=budget,
            progress=progress,
            on_progress=on_progress,
        )
        if callable(on_delta):
            on_delta(generated.answer)
        evidence = dict(generated.evidence)
        evidence["streaming"] = False
        evidence["fallback_reason"] = _stream_fallback_reason(cause)
        return AnswerGenerationResult(answer=generated.answer, evidence=evidence)



def _answer_budget_options(
    budget: Optional[RunBudget],
    *,
    progress: Any = None,
) -> dict[str, Any]:
    """Enter the answer phase and snapshot one provider-call deadline."""

    if budget is None:
        return {}
    if progress is not None and callable(getattr(progress, "start_phase", None)):
        progress.start_phase(
            "answer",
            status="EXECUTING",
            message="正在生成答案",
            emit_event=False,
        )
    if budget.phase != "answer":
        budget.start_phase("answer")
    budget.check()
    return {
        "timeout_seconds": budget.child_timeout(kind="provider"),
        "deadline": budget.child_deadline(kind="provider"),
    }


def _answer_begin_attempt(
    budget: Optional[RunBudget],
    progress: Any = None,
    *,
    retry: bool = False,
) -> None:
    if budget is None:
        return
    begin_attempt = getattr(progress, "begin_attempt", None)
    if callable(begin_attempt):
        begin_attempt(retry=retry)
    else:
        budget.begin_attempt(retry=retry)


def _answer_check_budget(budget: Optional[RunBudget]) -> None:
    if budget is not None:
        budget.check()


def _answer_provider_progress(
    progress: Any,
    callback: Optional[Callable[[Mapping[str, Any]], None]],
    *,
    phase: str,
) -> Optional[Callable[[Mapping[str, Any]], None]]:
    if progress is None and not callable(callback):
        return None

    allowed = {
        "kind",
        "attempt",
        "retry_count",
        "received_chars",
        "elapsed_ms",
        "timeout_seconds",
    }

    def emit(value: Mapping[str, Any]) -> None:
        if not isinstance(value, Mapping):
            return
        safe = {
            key: value[key]
            for key in allowed
            if key in value and isinstance(value[key], (str, int, float, bool))
        }
        safe["phase"] = phase
        if callable(callback):
            try:
                callback(dict(safe))
            except Exception:
                pass
        update = getattr(progress, "progress", None)
        if callable(update):
            kind = str(safe.get("kind") or "provider_progress")
            message = {
                "provider_call_started": "正在生成答案",
                "provider_retry": "答案生成正在重试",
                "provider_stream_delta": "正在接收答案",
                "provider_call_completed": "答案已生成",
                "provider_call_failed": "答案生成失败",
            }.get(kind, "答案生成中")
            try:
                update(message, data=safe)
            except Exception:
                pass

    return emit


def _invoke_text_stream(
    stream: Callable[..., Any],
    messages: Any,
    *,
    max_chars: int,
    timeout_seconds: Optional[float],
    deadline: Optional[float],
    on_progress: Optional[Callable[[Mapping[str, Any]], None]],
) -> Any:
    """Call old and new stream adapters without leaking unsupported kwargs."""

    try:
        parameters = inspect.signature(stream).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        item.kind == inspect.Parameter.VAR_KEYWORD
        for item in parameters.values()
    )
    kwargs: dict[str, Any] = {}
    if accepts_kwargs or "max_chars" in parameters:
        kwargs["max_chars"] = max_chars
    for key, value in (
        ("timeout_seconds", timeout_seconds),
        ("deadline", deadline),
        ("on_progress", on_progress),
    ):
        if value is not None and (accepts_kwargs or key in parameters):
            kwargs[key] = value
    if on_progress is not None and not accepts_kwargs and "on_progress" not in parameters:
        if "progress_callback" in parameters:
            kwargs["progress_callback"] = on_progress
    return stream(messages, **kwargs)


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
