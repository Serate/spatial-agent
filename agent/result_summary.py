"""Domain-neutral, bounded summary projection for typed results.

This module is the common seam between Result, Composite View and answer
generation.  Domain Packs publish typed data profiles and facts; the Runtime
only normalizes their safe shape.  It deliberately does not know GIS field
names or renderers.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from agent.data_kinds import SUPPORTED_DATA_KINDS, build_data_profile, normalize_data_profile
from agent.contract_versions import RESULT_SUMMARY_SCHEMA_VERSION
from agent.result_completeness import (
    RESULT_COMPLETENESS_STATES,
    build_result_completeness,
    normalize_result_completeness,
)


RESULT_SUMMARY_KINDS = frozenset(SUPPORTED_DATA_KINDS)
RESULT_SUMMARY_STATES = frozenset(
    set(RESULT_COMPLETENESS_STATES) | {"complete", "failed", "unavailable"}
)
_MAX_BLOCKS = 8
_MAX_FACTS = 24
_MAX_LIST = 12
_MAX_TEXT = 320
_MAX_CONCLUSION = 800
_MAX_SOURCES = 16
_MAX_BYTES = 128_000
_PRIVATE_KEYS = {
    "api_key",
    "authorization",
    "credentials",
    "password",
    "secret",
    "token",
    "prompt",
    "messages",
    "model_response",
    "raw_response",
    "private_payload",
    "tool_args",
    "args",
    "geometry",
    "coordinates",
    "features",
    "geojson",
    "result_ref",
    "artifact_ref",
    "path",
    "file_path",
    "dataset_path",
    "references",
    "views",
    "evidence_registry",
    "plan",
    "steps",
    "failure",
    "degradation",
    "error",
    "warning",
    "tool",
    "result",
    "inputs",
    "input_evidence",
    "execution",
    "binding_fingerprint",
    "plan_fingerprint",
    "step_ids",
    "depends_on",
    "required",
    "view_refs",
    "workflow",
    "capability_id",
    "component_ids",
    "fingerprint",
    "request",
    "domain_id",
}
_PRIVATE_MARKERS = ("memory://", "artifact://", "prompt", "authorization")
_META_KEYS = {
    "schema_version",
    "type",
    "result_type",
    "data_profile",
    "status",
    "state",
    "answer",
    "summary",
    "conclusion",
    "headline",
    "title",
    "component_id",
    "domain_id",
    "block_id",
    "id",
    "kind",
    "kinds",
}


class ResultSummaryError(ValueError):
    """A persisted result summary cannot cross the public boundary."""


def build_result_summary(value: Any) -> dict[str, Any]:
    """Build one bounded summary from a Result or Composite-shaped mapping.

    The input may be a raw run payload, a canonical Result envelope, or a
    Composite View projection.  The output is intentionally independent of
    transport and renderer details.
    """

    source = _unwrap_result(value)
    completeness = _read_completeness(source)
    sections = _sections(source)
    blocks = [_build_block(item, source, index) for index, item in enumerate(sections)]
    blocks = [item for item in blocks if item is not None][: _MAX_BLOCKS]
    limitations = _collect_limitations(source, completeness, blocks)
    evidence = _build_evidence(source, blocks)
    findings = [
        block["conclusion"]
        for block in blocks
        if block.get("conclusion")
    ][: _MAX_BLOCKS]
    conclusion = _conclusion(source, blocks, completeness["state"])
    result = {
        "schema_version": RESULT_SUMMARY_SCHEMA_VERSION,
        "state": completeness["state"],
        "completeness": completeness,
        "conclusion": conclusion,
        "key_findings": findings,
        "limitations": limitations[:_MAX_BLOCKS],
        "evidence": evidence,
        "blocks": blocks,
    }
    _fit_budget(result)
    return result


def normalize_result_summary(value: Any, *, allow_legacy: bool = True) -> dict[str, Any]:
    """Normalize a persisted summary without widening its public shape."""

    if value is None and allow_legacy:
        return build_result_summary({})
    if not isinstance(value, Mapping):
        raise ResultSummaryError("result_summary must be an object")
    version = value.get("schema_version")
    if version in (None, "") and allow_legacy:
        version = RESULT_SUMMARY_SCHEMA_VERSION
    if str(version) != RESULT_SUMMARY_SCHEMA_VERSION:
        raise ResultSummaryError("unknown result summary schema version")
    state = _state(value.get("state"))
    completeness = normalize_result_completeness(value.get("completeness"))
    raw_blocks = value.get("blocks")
    if not isinstance(raw_blocks, list) or len(raw_blocks) > _MAX_BLOCKS:
        raise ResultSummaryError("result_summary.blocks must be a bounded list")
    blocks = [_normalize_block(item, index) for index, item in enumerate(raw_blocks)]
    limitations = _strings(value.get("limitations"), _MAX_BLOCKS, _MAX_TEXT)
    findings = _strings(value.get("key_findings"), _MAX_BLOCKS, _MAX_CONCLUSION)
    evidence = _normalize_evidence(value.get("evidence"))
    conclusion = _text(value.get("conclusion"), _MAX_CONCLUSION)
    return {
        "schema_version": RESULT_SUMMARY_SCHEMA_VERSION,
        "state": state,
        "completeness": completeness,
        "conclusion": conclusion,
        "key_findings": findings,
        "limitations": limitations,
        "evidence": evidence,
        "blocks": blocks,
    }


def _unwrap_result(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    nested = value.get("result")
    if isinstance(nested, Mapping):
        return nested
    return value


def _read_completeness(source: Mapping[str, Any]) -> dict[str, Any]:
    existing = source.get("completeness")
    if isinstance(existing, Mapping):
        return normalize_result_completeness(existing)
    return build_result_completeness(source, status=source.get("status"))


def _sections(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    composite = source.get("composite") or source.get("_composite")
    if isinstance(composite, Mapping):
        components = composite.get("components")
        if isinstance(components, list):
            return [item for item in components[:_MAX_BLOCKS] if isinstance(item, Mapping)]

    typed = source.get("typed_sections")
    if isinstance(typed, list):
        return [item for item in typed[:_MAX_BLOCKS] if isinstance(item, Mapping)]

    sections = source.get("sections")
    if isinstance(sections, list):
        components = [
            item for item in sections
            if isinstance(item, Mapping) and item.get("kind") == "component"
        ]
        if components:
            return components[:_MAX_BLOCKS]

    steps = source.get("steps")
    if isinstance(steps, list):
        typed_steps = [item for item in steps[:16] if isinstance(item, Mapping)]
        if typed_steps:
            return typed_steps[:_MAX_BLOCKS]
    return [source] if source else []


def _build_block(
    section: Mapping[str, Any], source: Mapping[str, Any], index: int
) -> dict[str, Any] | None:
    nested = section.get("result")
    nested = nested if isinstance(nested, Mapping) else section
    profile = _profile(
        section.get("data_profile")
        or nested.get("data_profile")
        or source.get("data_profile")
    )
    kinds = profile["kinds"]
    block_id = _text(
        section.get("block_id")
        or section.get("component_id")
        or section.get("id")
        or f"result-{index + 1}",
        96,
    )
    if not block_id:
        return None
    status = _text(section.get("status") or nested.get("status") or source.get("status"), 32)
    state = _block_state(section.get("state") or nested.get("state") or status)
    if state == "unavailable" and _source_has_content(section, nested):
        state = _state(source.get("status"))
    conclusion = _conclusion_from(section, nested)
    limitations = _section_limitations(section, nested)
    evidence = _build_block_evidence(section, nested, source)
    facts_source = section.get("facts")
    if not isinstance(facts_source, Mapping):
        if isinstance(section.get("result"), Mapping):
            facts_source = section["result"]
        else:
            facts_source = nested.get("data") if isinstance(nested.get("data"), Mapping) else nested
    facts = _safe_facts(facts_source)
    title = _text(
        section.get("title")
        or nested.get("title")
        or section.get("component_id")
        or section.get("id")
        or profile["primary"],
        160,
    )
    result_type = _text(
        section.get("result_type")
        or nested.get("type")
        or nested.get("result_type")
        or source.get("result_type")
        or "unknown",
        96,
    )
    return {
        "block_id": block_id,
        "title": title or "结果",
        "kind": profile["primary"],
        "kinds": kinds,
        "data_profile": profile,
        "result_type": result_type,
        "state": state,
        "status": status or "UNKNOWN",
        "conclusion": conclusion,
        "facts": facts,
        "limitations": limitations[:_MAX_BLOCKS],
        "evidence": evidence,
    }


def _normalize_block(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResultSummaryError(f"result_summary.blocks[{index}] must be an object")
    profile = _profile(value.get("data_profile") or {"kinds": value.get("kinds")})
    block_id = _text(value.get("block_id"), 96)
    if not block_id:
        raise ResultSummaryError("result summary block_id is required")
    evidence = _normalize_evidence(value.get("evidence"))
    return {
        "block_id": block_id,
        "title": _text(value.get("title"), 160) or "结果",
        "kind": profile["primary"],
        "kinds": profile["kinds"],
        "data_profile": profile,
        "result_type": _text(value.get("result_type"), 96) or "unknown",
        "state": _state(value.get("state")),
        "status": _text(value.get("status"), 32) or "UNKNOWN",
        "conclusion": _text(value.get("conclusion"), _MAX_CONCLUSION),
        "facts": _safe_facts(value.get("facts")),
        "limitations": _strings(value.get("limitations"), _MAX_BLOCKS, _MAX_TEXT),
        "evidence": evidence,
    }


def _profile(value: Any) -> dict[str, Any]:
    try:
        return normalize_data_profile(value, allow_legacy=True)
    except Exception:
        return build_data_profile(("unknown",))


def _block_state(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"COMPLETED", "COMPLETE", "SUCCESS", "READY"}:
        return "complete"
    if raw in {"PARTIAL", "DEGRADED"}:
        return "partial"
    if raw in {"PENDING", "QUEUED", "PLANNING", "EXECUTING", "CREATED"}:
        return "pending"
    if raw in {"WAITING_FOR_DECISION", "AWAITING_APPROVAL"}:
        return "waiting_decision"
    if raw in {"FAILED", "ERROR", "REJECTED", "CANCELLED", "BLOCKED", "NEEDS_CLARIFICATION"}:
        return "blocked"
    return "unavailable"


def _state(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "completed": "complete",
        "success": "complete",
        "ready": "complete",
        "failed": "blocked",
        "error": "blocked",
        "rejected": "blocked",
        "cancelled": "blocked",
        "needs_clarification": "blocked",
        "awaiting_approval": "waiting_decision",
        "executing": "pending",
        "planning": "pending",
        "created": "pending",
        "queued": "pending",
    }
    result = aliases.get(raw, raw)
    return result if result in RESULT_SUMMARY_STATES else "unavailable"


def _conclusion(source: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]], state: str) -> str:
    direct = _conclusion_from(source, source)
    if direct:
        return direct
    if blocks:
        return _text(blocks[0].get("conclusion"), _MAX_CONCLUSION)
    return {
        "pending": "结果仍在生成中。",
        "waiting_decision": "继续分析前需要用户确认。",
        "blocked": "当前没有可用的完整结果。",
        "partial": "当前只形成了部分结果。",
    }.get(state, "当前没有可用结果摘要。")


def _conclusion_from(first: Mapping[str, Any], second: Mapping[str, Any]) -> str:
    for value in (
        first.get("conclusion"),
        first.get("answer"),
        first.get("summary"),
        first.get("message"),
        second.get("conclusion"),
        second.get("answer"),
        second.get("summary"),
    ):
        if isinstance(value, Mapping):
            value = value.get("summary") or value.get("headline")
        text = _text(value, _MAX_CONCLUSION)
        if text and not _contains_private(text):
            return text
    return ""


def _collect_limitations(
    source: Mapping[str, Any], completeness: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]]
) -> list[str]:
    values: list[str] = []
    if completeness.get("uncertainty"):
        values.append(str(completeness["uncertainty"]))
    values.extend(_strings(source.get("limitations"), _MAX_BLOCKS, _MAX_TEXT))
    for block in blocks:
        values.extend(_strings(block.get("limitations"), _MAX_BLOCKS, _MAX_TEXT))
        evidence = block.get("evidence")
        if isinstance(evidence, Mapping):
            limitation = _document_evidence_limitation(evidence)
            if limitation:
                values.append(limitation)
    if blocks and not any(block.get("evidence", {}).get("available") for block in blocks) and not any(
        block.get("evidence", {}).get("status")
        for block in blocks
        if isinstance(block.get("evidence"), Mapping)
    ):
        values.append("当前结果未提供可核验的证据来源。")
    return _unique_text(values, _MAX_BLOCKS)


def _section_limitations(first: Mapping[str, Any], second: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    values.extend(_strings(first.get("limitations"), _MAX_BLOCKS, _MAX_TEXT))
    values.extend(_strings(second.get("limitations"), _MAX_BLOCKS, _MAX_TEXT))
    for value in (first.get("failure"), second.get("failure")):
        if isinstance(value, Mapping):
            message = _text(value.get("message"), _MAX_TEXT)
            if message and not _contains_private(message):
                values.append(message)
    for value in (first.get("degradation"), second.get("degradation")):
        if not isinstance(value, Mapping):
            continue
        items = value.get("items")
        if isinstance(items, list):
            for item in items[:_MAX_BLOCKS]:
                if isinstance(item, Mapping):
                    message = _text(item.get("message"), _MAX_TEXT)
                    if message and not _contains_private(message):
                        values.append(message)
    return _unique_text(values, _MAX_BLOCKS)


def _build_evidence(source: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sources: list[str] = []
    source_records: list[dict[str, str]] = []
    states: list[str] = []
    statuses: list[str] = []
    reason_codes: list[str] = []
    available = False
    count = 0
    raw = source.get("evidence")
    if isinstance(raw, Mapping):
        available = bool(raw.get("available"))
        count = _count(raw.get("entry_count"), raw.get("entries"))
        states.append(_text(raw.get("state") or ("available" if available else "unavailable"), 32))
        sources.extend(_safe_sources(raw.get("sources")))
        source_records.extend(_safe_source_records(raw.get("source_records")))
        statuses.extend(_safe_statuses(raw.get("status")))
        reason_codes.extend(_safe_reason_codes(raw.get("reason_code")))
    registry = source.get("evidence_registry")
    if isinstance(registry, Mapping):
        available = available or bool(registry.get("available"))
        count = max(count, _count(registry.get("entry_count"), registry.get("entries")))
        entries = registry.get("entries")
        if isinstance(entries, list):
            sources.extend(
                _text(item.get("id"), 96)
                for item in entries[:_MAX_SOURCES]
                if isinstance(item, Mapping) and _text(item.get("id"), 96)
            )
    for block in blocks:
        evidence = block.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        available = available or bool(evidence.get("available"))
        count += _count(evidence.get("source_count"), None)
        states.append(_text(evidence.get("state"), 32))
        sources.extend(_safe_sources(evidence.get("sources")))
        source_records.extend(_safe_source_records(evidence.get("source_records")))
        statuses.extend(_safe_statuses(evidence.get("status")))
        reason_codes.extend(_safe_reason_codes(evidence.get("reason_code")))
    if not sources and source.get("domain_id"):
        sources.append(_text(source.get("domain_id"), 64))
    states = [item for item in states if item]
    evidence_state = "available" if available else "unavailable"
    if not available and statuses:
        if "degraded" in statuses:
            evidence_state = "degraded"
        elif all(item == "ok" for item in statuses):
            evidence_state = "no_results"
    result = {
        "available": available,
        "state": evidence_state,
        "source_count": max(count, len(set(sources))),
        "sources": _unique_text(sources, _MAX_SOURCES),
        "states": _unique_text(states, _MAX_SOURCES),
    }
    if source_records:
        result["source_records"] = _unique_source_records(source_records)
    if statuses:
        result["statuses"] = _unique_text(statuses, _MAX_SOURCES)
    if reason_codes:
        result["reason_codes"] = _unique_text(reason_codes, _MAX_SOURCES)
    return result


def _build_block_evidence(
    first: Mapping[str, Any], second: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    raw = first.get("evidence")
    if not isinstance(raw, Mapping):
        raw = second.get("evidence")
    if not isinstance(raw, Mapping):
        raw = source.get("evidence")
    if not isinstance(raw, Mapping):
        raw = source.get("evidence_registry")
    if not isinstance(raw, Mapping):
        raw = first if _is_document_evidence(first) else second if _is_document_evidence(second) else {}
    document = _project_document_evidence(raw)
    if document is not None:
        available = document["available"]
        state = document["state"]
        status = document["status"]
        reason_code = document["reason_code"]
        source_records = document["source_records"]
        source_count = max(document["source_count"], len(source_records))
    else:
        available = bool(raw.get("available"))
        state = _text(raw.get("state") or ("available" if available else "unavailable"), 32)
        status = _text(raw.get("status"), 32)
        reason_code = _safe_reason_code(raw.get("reason_code")) if raw.get("reason_code") else ""
        source_records = _safe_source_records(raw.get("source_records"))
        source_count = _count(raw.get("source_count") or raw.get("entry_count"), raw.get("entries"))
    sources = _safe_sources(raw.get("sources"))
    if source_records:
        sources.extend(_source_record_labels(source_records))
    if not sources:
        source_name = first.get("domain_id") or source.get("domain_id")
        if source_name:
            sources = [_text(source_name, 64)]
    result = {
        "available": available,
        "state": state,
        "source_count": source_count,
        "sources": _unique_text(sources, _MAX_SOURCES),
    }
    if status:
        result["status"] = status
    if reason_code:
        result["reason_code"] = reason_code
    if source_records:
        result["source_records"] = _unique_source_records(source_records)
    if document is not None:
        query = _text(raw.get("query"), _MAX_TEXT)
        if query and not _contains_private(query):
            result["query"] = query
        allowed_domains = _safe_domains(raw.get("allowed_domains"))
        if allowed_domains:
            result["allowed_domains"] = allowed_domains
    return result


def _safe_facts(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    facts: dict[str, Any] = {}
    for key, item in list(value.items())[:_MAX_FACTS * 2]:
        name = _text(key, 64).lower()
        if not name or name in _PRIVATE_KEYS or name in _META_KEYS:
            continue
        projected = _safe_value(item, key=name, depth=0)
        if projected is not None:
            facts[name] = projected
        if len(facts) >= _MAX_FACTS:
            break
    return facts


def _safe_value(value: Any, *, key: str, depth: int) -> Any:
    if key in _PRIVATE_KEYS or any(token in key for token in ("password", "secret", "token")):
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return max(-10**15, min(value, 10**15))
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if isinstance(value, str):
        text = value.replace("\x00", "").strip()[:_MAX_TEXT]
        return None if not text or _contains_private(text) else text
    if depth >= 3:
        return None
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for child_key, child_value in list(value.items())[:_MAX_FACTS]:
            normalized = _text(child_key, 64).lower()
            if not normalized or normalized in _PRIVATE_KEYS:
                continue
            projected = _safe_value(child_value, key=normalized, depth=depth + 1)
            if projected is not None:
                result[normalized] = projected
        return result or None
    if isinstance(value, (list, tuple)):
        result = []
        for child in list(value)[:_MAX_LIST]:
            projected = _safe_value(child, key=key, depth=depth + 1)
            if projected is not None:
                result.append(projected)
        return result or None
    return None


def _source_has_content(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    return any(key in first or key in second for key in ("answer", "summary", "data", "facts"))


def _normalize_evidence(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    available = bool(source.get("available"))
    entries = source.get("entries")
    result = {
        "available": available,
        "state": _text(source.get("state") or ("available" if available else "unavailable"), 32),
        "source_count": _count(source.get("source_count") or source.get("entry_count"), entries),
        "sources": _unique_text(_safe_sources(source.get("sources")), _MAX_SOURCES),
    }
    source_records = _unique_source_records(_safe_source_records(source.get("source_records")))
    if source_records:
        result["source_records"] = source_records
    status = _text(source.get("status"), 32).lower()
    if status:
        result["status"] = status
    if source.get("reason_code"):
        result["reason_code"] = _safe_reason_code(source.get("reason_code"))
    query = _text(source.get("query"), _MAX_TEXT)
    if query and not _contains_private(query):
        result["query"] = query
    allowed_domains = _safe_domains(source.get("allowed_domains"))
    if allowed_domains:
        result["allowed_domains"] = allowed_domains
    document = _project_document_evidence(source)
    if document is not None:
        result.update(
            {
                "available": document["available"],
                "state": document["state"],
                "status": document["status"],
                "reason_code": document["reason_code"],
                "source_count": max(document["source_count"], len(document["source_records"])),
                "source_records": _unique_source_records(document["source_records"]),
            }
        )
        query = _text(source.get("query"), _MAX_TEXT)
        if query and not _contains_private(query):
            result["query"] = query
        allowed_domains = _safe_domains(source.get("allowed_domains"))
        if allowed_domains:
            result["allowed_domains"] = allowed_domains
    if "states" in source:
        result["states"] = _unique_text(_safe_sources(source.get("states")), _MAX_SOURCES)
    if "statuses" in source:
        result["statuses"] = _unique_text(_safe_sources(source.get("statuses")), _MAX_SOURCES)
    if "reason_codes" in source:
        result["reason_codes"] = _unique_text(_safe_sources(source.get("reason_codes")), _MAX_SOURCES)
    return result


def _fit_budget(value: dict[str, Any]) -> None:
    if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= _MAX_BYTES:
        return
    for block in value.get("blocks", []):
        if isinstance(block, dict):
            block["facts"] = {}
    if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > _MAX_BYTES:
        value["blocks"] = list(value.get("blocks", []))[:4]


def _project_document_evidence(value: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalize the public-web result into the shared evidence shape.

    ``web_search`` returns source records directly, while other tools wrap
    evidence under ``evidence``.  Keeping this adapter here means every
    transport and renderer sees the same bounded document-evidence status.
    """

    result_type = _text(value.get("result_type") or value.get("type"), 96).lower()
    schema_version = _text(value.get("schema_version"), 96)
    if result_type not in {"document_evidence", "web_document"} and "document-evidence" not in schema_version:
        return None
    raw_status = _text(value.get("status"), 32).lower()
    source_records = _safe_source_records(value.get("source_records"))
    source_records.extend(_safe_source_records(value.get("sources")))
    source_records = _unique_source_records(source_records)
    source_count = _count(value.get("source_count"), value.get("sources"))
    source_count = max(source_count, len(source_records))
    if raw_status in {"ok", "success", "completed", "available"}:
        status = "ok"
        state = "available" if source_count else "no_results"
        available = bool(source_count)
    elif raw_status in {"degraded", "partial"}:
        status = "degraded"
        state = "degraded"
        available = bool(source_count)
    else:
        status = "unavailable"
        state = "unavailable"
        available = False
    reason_code = _safe_reason_code(value.get("reason_code"))
    return {
        "available": available,
        "state": state,
        "status": status,
        "reason_code": reason_code,
        "source_count": min(source_count, 128),
        "source_records": source_records,
    }


def _is_document_evidence(value: Mapping[str, Any]) -> bool:
    result_type = _text(value.get("result_type") or value.get("type"), 96).lower()
    schema_version = _text(value.get("schema_version"), 96)
    return result_type in {"document_evidence", "web_document"} or "document-evidence" in schema_version


def _document_evidence_limitation(evidence: Mapping[str, Any]) -> str:
    status = _text(evidence.get("status"), 32).lower()
    state = _text(evidence.get("state"), 32).lower()
    if status == "unavailable" or state == "unavailable":
        return "公开网页来源当前不可用，结论未使用网页资料补充。"
    if status == "degraded" or state == "degraded":
        return "公开网页来源仅部分可用，相关结论应结合其他证据核对。"
    if state == "no_results":
        return "在当前允许的公开来源范围内没有找到相关资料。"
    return ""


def _count(value: Any, fallback: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, min(value, 128))
    return min(len(fallback), 128) if isinstance(fallback, list) else 0


def _safe_reason_code(value: Any) -> str:
    text = _text(value, 96)
    if not text:
        return "evidence_unavailable"
    return text if all(char.isalnum() or char in "_.-" for char in text) else "evidence_unavailable"


def _safe_statuses(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return []
    return [
        item
        for item in (_text(raw, 32).lower() for raw in list(values)[:_MAX_SOURCES])
        if item and item in {"ok", "degraded", "unavailable", "available", "no_results"}
    ]


def _safe_reason_codes(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return []
    return [
        item
        for item in (_safe_reason_code(raw) for raw in list(values)[:_MAX_SOURCES])
        if item
    ]


def _safe_domains(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return []
    result: list[str] = []
    for raw in list(values)[:_MAX_SOURCES]:
        domain = _text(raw, 255).lower().rstrip(".")
        if not domain or "/" in domain or ":" in domain or " " in domain or "." not in domain:
            continue
        if domain not in result:
            result.append(domain)
    return result


def _safe_source_records(value: Any) -> list[dict[str, str]]:
    values = value if isinstance(value, (list, tuple)) else []
    result: list[dict[str, str]] = []
    for raw in list(values)[:_MAX_SOURCES * 2]:
        if not isinstance(raw, Mapping):
            continue
        url = _safe_https_url(raw.get("url"))
        if not url:
            continue
        title = _text(raw.get("title"), 160)
        snippet = _text(raw.get("snippet"), _MAX_TEXT)
        domain = _text(raw.get("domain"), 255).lower().rstrip(".")
        if not domain:
            try:
                domain = (urlsplit(url).hostname or "").lower().rstrip(".")
            except ValueError:
                domain = ""
        if not domain or _contains_private(title) or _contains_private(snippet):
            continue
        item = {
            "title": title or "未命名来源",
            "url": url,
            "domain": domain[:255],
        }
        if snippet:
            item["snippet"] = snippet
        result.append(item)
    return result


def _safe_https_url(value: Any) -> str:
    raw = _text(value, 2048)
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
            return ""
        if host == "localhost" or "." not in host:
            return ""
        return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))[:2048]
    except (TypeError, ValueError):
        return ""


def _unique_source_records(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping):
            continue
        url = _safe_https_url(value.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        item = {
            "title": _text(value.get("title"), 160) or "未命名来源",
            "url": url,
            "domain": _text(value.get("domain"), 255).lower().rstrip(".") or "未知来源",
        }
        snippet = _text(value.get("snippet"), _MAX_TEXT)
        if snippet and not _contains_private(snippet):
            item["snippet"] = snippet
        result.append(item)
        if len(result) >= _MAX_SOURCES:
            break
    return result


def _source_record_labels(values: Sequence[Mapping[str, Any]]) -> list[str]:
    return [
        _text(item.get("title") or item.get("domain"), 96)
        for item in values
        if isinstance(item, Mapping) and _text(item.get("title") or item.get("domain"), 96)
    ]


def _safe_sources(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return []
    return [
        item
        for item in (_text(raw, 96) for raw in list(values)[:_MAX_SOURCES])
        if item and not _contains_private(item)
    ]


def _strings(value: Any, limit: int, text_limit: int) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return []
    return [
        item
        for item in (_text(raw, text_limit) for raw in list(values)[:limit])
        if item and not _contains_private(item)
    ]


def _unique_text(values: Sequence[Any], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        item = _text(value, _MAX_TEXT)
        if item and item not in result and not _contains_private(item):
            result.append(item)
        if len(result) >= limit:
            break
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _contains_private(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PRIVATE_MARKERS)


__all__ = [
    "RESULT_SUMMARY_KINDS",
    "RESULT_SUMMARY_SCHEMA_VERSION",
    "RESULT_SUMMARY_STATES",
    "ResultSummaryError",
    "build_result_summary",
    "normalize_result_summary",
]
