"""Shared HTTP adapter helpers for explicit Domain-prefixed routes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from agent.domain_registry import DomainSelectionError
from agent.domain_selection import DomainSelection, resolve_domain_selection


@dataclass(frozen=True)
class DomainHttpScope:
    """A parsed Domain URL prefix and its transport-neutral inner path."""

    domain_id: str
    path: str


def parse_domain_path(path: str) -> DomainHttpScope | None:
    """Parse ``/domains/{domain_id}/...`` without selecting a Domain Pack."""

    parts = str(path or "").split("/")
    if len(parts) < 4 or parts[0] != "" or parts[1] != "domains" or not parts[2]:
        return None
    inner_path = "/" + "/".join(parts[3:])
    return DomainHttpScope(domain_id=unquote(parts[2]), path=inner_path)


def assert_domain_payload(
    selection: DomainSelection,
    payload: Mapping[str, Any] | None,
) -> None:
    """Reject a body that contradicts the authoritative URL selection."""

    if not isinstance(payload, Mapping):
        return
    declarations = []
    if "domain_id" in payload:
        declarations.append(payload.get("domain_id"))
    nested = payload.get("domain_selection")
    if nested is not None:
        if not isinstance(nested, Mapping):
            raise DomainSelectionError(
                "domain_selection must be an object",
                code="invalid_domain_selection",
            )
        declarations.append(resolve_domain_selection(nested).domain_id)
    if not declarations:
        return
    for declared in declarations:
        if not isinstance(declared, str) or declared.strip().lower() != selection.domain_id:
            raise DomainSelectionError(
                "request domain_id does not match URL domain_id",
                code="domain_mismatch",
            )
