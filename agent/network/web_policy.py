"""Server-owned policy for bounded public web access.

This module is deliberately effect-free at its interface.  It validates and
canonicalizes a URL before an adapter opens it.  Public mode performs a DNS
resolution check so a harmless-looking hostname cannot resolve to a local or
metadata address.  The HTTP client still owns connection and redirect
handling; callers must run this check for every redirect target.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit


WEB_MODE_OFF = "off"
WEB_MODE_ALLOWLIST = "allowlist"
WEB_MODE_PUBLIC = "public"
WEB_MODES = frozenset({WEB_MODE_OFF, WEB_MODE_ALLOWLIST, WEB_MODE_PUBLIC})
DEFAULT_WEB_MODE = WEB_MODE_ALLOWLIST
MAX_WEB_URL = 2048
MAX_WEB_DOMAIN = 255


@dataclass(frozen=True)
class WebPolicyDecision:
    """Bounded result of one URL policy check."""

    allowed: bool
    url: str = ""
    host: str = ""
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "url": self.url[:MAX_WEB_URL],
            "host": self.host[:MAX_WEB_DOMAIN],
            "reason_code": self.reason_code[:96],
        }


class WebAccessPolicy:
    """Validate URLs against a server-owned web mode and address policy."""

    def __init__(
        self,
        mode: str = DEFAULT_WEB_MODE,
        allowed_domains: Iterable[Any] | None = None,
        *,
        resolver: Callable[..., Any] | None = None,
    ) -> None:
        normalized_mode = str(mode or DEFAULT_WEB_MODE).strip().lower()
        self._mode = normalized_mode if normalized_mode in WEB_MODES else DEFAULT_WEB_MODE
        self._allowed_domains = normalize_web_domains(allowed_domains)
        self._resolver = resolver or socket.getaddrinfo

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def allowed_domains(self) -> tuple[str, ...]:
        return self._allowed_domains

    def check_url(
        self,
        value: Any,
        *,
        require_allowlisted: bool | None = None,
    ) -> WebPolicyDecision:
        """Return a canonical URL decision without opening a connection."""

        if self._mode == WEB_MODE_OFF:
            return WebPolicyDecision(False, reason_code="web_mode_disabled")
        parsed, host, reason = _parse_https_url(value)
        if parsed is None:
            return WebPolicyDecision(False, reason_code=reason)
        if require_allowlisted is None:
            require_allowlisted = self._mode == WEB_MODE_ALLOWLIST
        if require_allowlisted and not any(
            domain_allowed(host, allowed) for allowed in self._allowed_domains
        ):
            return WebPolicyDecision(False, host=host, reason_code="web_host_not_allowlisted")
        if self._mode == WEB_MODE_PUBLIC and not _safe_public_host(
            host, self._resolver
        ):
            return WebPolicyDecision(False, host=host, reason_code="web_address_not_public")
        canonical = urlunsplit(
            (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, "")
        )[:MAX_WEB_URL]
        return WebPolicyDecision(True, url=canonical, host=host, reason_code="web_url_allowed")

    def check_provider(self, value: Any) -> WebPolicyDecision:
        """Validate a configured search provider under the active mode."""

        return self.check_url(
            value,
            require_allowlisted=self._mode == WEB_MODE_ALLOWLIST,
        )


def normalize_web_mode(value: Any) -> str:
    mode = str(value or DEFAULT_WEB_MODE).strip().lower()
    return mode if mode in WEB_MODES else DEFAULT_WEB_MODE


def normalize_web_domains(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    result: list[str] = []
    for item in value:
        text = str(item or "").strip().lower().rstrip(".")
        if (
            not text
            or len(text) > MAX_WEB_DOMAIN
            or "/" in text
            or ":" in text
            or " " in text
        ):
            continue
        try:
            text = text.encode("idna").decode("ascii")
        except UnicodeError:
            continue
        if _is_ip_literal(text) or text == "localhost" or "." not in text:
            continue
        if text not in result:
            result.append(text)
    return tuple(result[:32])


def domain_allowed(host: str, allowed: str) -> bool:
    return host == allowed or host.endswith("." + allowed)


def _parse_https_url(value: Any) -> tuple[Any, str, str]:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_WEB_URL:
        return None, "", "web_url_invalid"
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except (TypeError, ValueError):
        return None, "", "web_url_invalid"
    if parsed.scheme.lower() != "https":
        return None, host, "web_https_required"
    if not host or parsed.username or parsed.password:
        return None, host, "web_credentials_forbidden"
    if port not in (None, 443):
        return None, host, "web_port_forbidden"
    if _is_ip_literal(host) or host == "localhost" or "." not in host:
        return None, host, "web_host_forbidden"
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None, "", "web_host_invalid"
    return parsed, host, ""


def _safe_public_host(host: str, resolver: Callable[..., Any]) -> bool:
    try:
        values = resolver(host, 443, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror, TypeError, ValueError):
        return False
    addresses: set[str] = set()
    for item in values or ():
        address = item[4][0] if isinstance(item, tuple) and len(item) > 4 else item
        try:
            addresses.add(str(ipaddress.ip_address(str(address).split("%", 1)[0])))
        except ValueError:
            return False
    return bool(addresses) and all(_is_public_address(item) for item in addresses)


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_reserved
        and not address.is_unspecified
        and not address.is_multicast
    )


def _is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


__all__ = [
    "DEFAULT_WEB_MODE",
    "MAX_WEB_DOMAIN",
    "MAX_WEB_URL",
    "WEB_MODE_ALLOWLIST",
    "WEB_MODE_OFF",
    "WEB_MODE_PUBLIC",
    "WEB_MODES",
    "WebAccessPolicy",
    "WebPolicyDecision",
    "domain_allowed",
    "normalize_web_domains",
    "normalize_web_mode",
]
