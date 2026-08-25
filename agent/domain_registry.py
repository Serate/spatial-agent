"""Controlled Domain Pack registry for deployment and entry-point selection.

The registry is intentionally explicit: a domain id selects one allowlisted
lazy factory, and never becomes a Python import path or an arbitrary class
name.  The selected pack is then passed through the existing Runtime and
ToolRegistry seams.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping


DOMAIN_REGISTRY_SCHEMA_VERSION = "spatial-agent.domain-registry.v1"
_DOMAIN_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class DomainSelectionError(ValueError):
    """A safe, machine-readable error for invalid deployment domain choice."""

    def __init__(self, message: str, *, code: str = "unknown_domain"):
        self.code = str(code)[:64]
        super().__init__(message)


@dataclass(frozen=True)
class DomainEntry:
    domain_id: str
    label: str
    description: str
    factory: Callable[[], Any]


class DomainRegistry:
    """Deep selection module hiding lazy imports behind a small interface."""

    def __init__(self, entries: Mapping[str, DomainEntry]):
        self._entries = dict(entries)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": DOMAIN_REGISTRY_SCHEMA_VERSION,
            "domain_ids": list(self.ids()),
            "domains": [
                {
                    "id": entry.domain_id,
                    "label": entry.label,
                    "description": entry.description,
                }
                for entry in sorted(self._entries.values(), key=lambda item: item.domain_id)
            ],
        }

    def resolve_id(self, domain_id: str | None = None, *, default: str = "gis") -> str:
        candidate = domain_id
        if candidate is None or not str(candidate).strip():
            candidate = os.environ.get("SPATIAL_AGENT_DOMAIN") or default
        candidate = str(candidate).strip().lower()
        if not _DOMAIN_ID_RE.fullmatch(candidate) or candidate not in self._entries:
            raise DomainSelectionError(
                "unknown domain: " + candidate,
                code="unknown_domain",
            )
        return candidate

    def resolve(self, domain_id: str | None = None, *, default: str = "gis") -> Any:
        selected_id = self.resolve_id(domain_id, default=default)
        entry = self._entries[selected_id]
        pack = entry.factory()
        if str(getattr(pack, "domain_id", "")) != selected_id:
            raise DomainSelectionError(
                "registered domain pack id mismatch: " + selected_id,
                code="domain_pack_mismatch",
            )
        return pack


def _load_gis():
    from domains.gis import GIS_DOMAIN_PACK

    return GIS_DOMAIN_PACK


def _load_text():
    from domains.text.domain import TEXT_DOMAIN_PACK

    return TEXT_DOMAIN_PACK


def _load_indicators():
    from domains.indicators import INDICATORS_DOMAIN_PACK

    return INDICATORS_DOMAIN_PACK


def _load_economic():
    from domains.economic import ECONOMIC_DOMAIN_PACK

    return ECONOMIC_DOMAIN_PACK


_REGISTRY = DomainRegistry(
    {
        "gis": DomainEntry(
            domain_id="gis",
            label="空间 GIS",
            description="行政区、栅格、道路、水体和空间分析能力。",
            factory=_load_gis,
        ),
        "text": DomainEntry(
            domain_id="text",
            label="文本分析",
            description="通用文本摘要能力，用于验证非 GIS Runtime 替换。",
            factory=_load_text,
        ),
        "indicators": DomainEntry(
            domain_id="indicators",
            label="区域指标",
            description="可追溯的指标目录、趋势与区域比较能力。",
            factory=_load_indicators,
        ),
        "economic": DomainEntry(
            domain_id="economic",
            label="区域经济分析",
            description="基于真实来源的经济指标查询、趋势、比较和来源证据能力。",
            factory=_load_economic,
        ),
    }
)


def domain_registry() -> DomainRegistry:
    """Return the immutable-in-practice built-in registry."""
    return _REGISTRY


def resolve_domain_id(domain_id: str | None = None) -> str:
    return _REGISTRY.resolve_id(domain_id)


def resolve_domain_pack(domain_id: str | None = None) -> Any:
    return _REGISTRY.resolve(domain_id)
