"""Domain-neutral fact receipts and alignment metadata for Composite results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


FACT_RECEIPT_SCHEMA_VERSION = "spatial-agent.composite-fact-receipt.v1"
ALIGNMENT_SCHEMA_VERSION = "spatial-agent.cross-domain-alignment.v1"
MAX_RECEIPTS = 32
MAX_FIELDS = 24


def build_component_fact_receipts(
    component: Mapping[str, Any],
    summary: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Describe child facts and their source references without copying values."""

    source_refs = _source_refs(summary)
    raw_blocks = summary.get("blocks") if isinstance(summary, Mapping) else []
    if not isinstance(raw_blocks, list):
        raw_blocks = []
    receipts: list[dict[str, Any]] = []
    for index, block in enumerate(raw_blocks[:8]):
        if not isinstance(block, Mapping):
            continue
        block_id = _text(block.get("block_id") or f"block-{index + 1}", 96)
        fields = _field_ids(block.get("facts"))
        if not block_id or not fields:
            continue
        receipt: dict[str, Any] = {
            "schema_version": FACT_RECEIPT_SCHEMA_VERSION,
            "fact_id": f"{_text(component.get('component_id'), 96)}:{block_id}"[:160],
            "component_id": _text(component.get("component_id"), 96),
            "domain_id": _text(component.get("domain_id"), 64),
            "data_kind": _text(block.get("kind"), 32) or "unknown",
            "status": _text(block.get("state"), 32) or "unknown",
            "field_ids": fields,
            "source_refs": source_refs[:8],
        }
        if not source_refs:
            receipt["limitation"] = "fact_source_refs_missing"
        receipts.append(receipt)
    return receipts[:MAX_RECEIPTS]


def normalize_fact_receipts(value: Any) -> list[dict[str, Any]]:
    """Normalize fact receipts from a persisted Composite projection."""

    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value[:MAX_RECEIPTS]:
        if not isinstance(raw, Mapping):
            continue
        fact_id = _text(raw.get("fact_id"), 160)
        component_id = _text(raw.get("component_id"), 96)
        if not fact_id or not component_id:
            continue
        item: dict[str, Any] = {
            "schema_version": FACT_RECEIPT_SCHEMA_VERSION,
            "fact_id": fact_id,
            "component_id": component_id,
            "domain_id": _text(raw.get("domain_id"), 64),
            "data_kind": _text(raw.get("data_kind"), 32) or "unknown",
            "status": _text(raw.get("status"), 32) or "unknown",
            "field_ids": _text_list(raw.get("field_ids"), MAX_FIELDS),
            "source_refs": _text_list(raw.get("source_refs"), 8),
        }
        limitation = _text(raw.get("limitation"), 96)
        if limitation:
            item["limitation"] = limitation
        result.append(item)
    return result


def build_cross_domain_alignment(
    components: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Report declared cross-domain scope compatibility without guessing."""

    items = [item for item in (components or []) if isinstance(item, Mapping)]
    scopes = [item.get("scope") for item in items]
    scopes = [scope for scope in scopes if isinstance(scope, Mapping)]
    if len(items) <= 1:
        return {
            "schema_version": ALIGNMENT_SCHEMA_VERSION,
            "status": "not_applicable",
            "compared_component_count": len(items),
            "dimensions": [],
            "reason_codes": [],
        }
    if not scopes:
        return _alignment("unknown", len(items), [], ["cross_domain_alignment_undeclared"])
    keys = ("spatial_ref", "geography", "time_start", "time_end", "unit")
    dimensions: list[str] = []
    conflicts: list[str] = []
    incomplete: list[str] = []
    for key in keys:
        values = [
            _text(scope.get(key), 160)
            for scope in scopes
            if scope.get(key) not in (None, "")
        ]
        if not values:
            continue
        dimension = {
            "spatial_ref": "spatial",
            "geography": "spatial",
            "time_start": "temporal",
            "time_end": "temporal",
            "unit": "unit",
        }[key]
        if dimension not in dimensions:
            dimensions.append(dimension)
        if len(values) != len(scopes):
            incomplete.append(dimension)
        elif len(set(values)) > 1:
            conflicts.append(dimension)
    if conflicts:
        return _alignment(
            "conflict", len(items), dimensions,
            ["cross_domain_alignment_conflict", *conflicts],
        )
    if len(scopes) != len(items) or incomplete:
        return _alignment(
            "unknown", len(items), dimensions,
            ["cross_domain_alignment_incomplete", *incomplete],
        )
    return _alignment("aligned", len(items), dimensions, [])


def normalize_alignment(value: Any) -> dict[str, Any]:
    """Normalize alignment metadata while preserving only declared fields."""

    source = value if isinstance(value, Mapping) else {}
    status = _text(source.get("status"), 24)
    if status not in {"aligned", "conflict", "unknown", "not_applicable"}:
        status = "unknown"
    return {
        "schema_version": ALIGNMENT_SCHEMA_VERSION,
        "status": status,
        "compared_component_count": _bounded_count(source.get("compared_component_count")),
        "dimensions": _text_list(source.get("dimensions"), 8),
        "reason_codes": _text_list(source.get("reason_codes"), 8),
    }


def _alignment(
    status: str,
    count: int,
    dimensions: list[str],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": ALIGNMENT_SCHEMA_VERSION,
        "status": status,
        "compared_component_count": max(0, min(count, 8)),
        "dimensions": _text_list(dimensions, 8),
        "reason_codes": _text_list(reasons, 8),
    }


def _source_refs(summary: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(summary, Mapping):
        return []
    evidence = summary.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    bundle = evidence.get("evidence_bundle")
    bundle = bundle if isinstance(bundle, Mapping) else {}
    entries = bundle.get("entries")
    if not isinstance(entries, list):
        return []
    return _text_list(
        [item.get("source_id") for item in entries if isinstance(item, Mapping)],
        8,
    )


def _field_ids(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    return _text_list(sorted(str(key) for key in value.keys()), MAX_FIELDS)


def _text_list(value: Any, limit: int) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for raw in values:
        item = _text(raw, 160)
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result


def _bounded_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, min(value, 8))


def _text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


__all__ = [
    "ALIGNMENT_SCHEMA_VERSION",
    "FACT_RECEIPT_SCHEMA_VERSION",
    "build_component_fact_receipts",
    "build_cross_domain_alignment",
    "normalize_alignment",
    "normalize_fact_receipts",
]
