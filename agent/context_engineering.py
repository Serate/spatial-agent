"""Bounded, auditable context construction for planner calls."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional


CONTEXT_SCHEMA_VERSION = "spatial-agent.context.v1"
_SENSITIVE_PARTS = ("api_key", "authorization", "password", "secret", "token")


@dataclass(frozen=True)
class ContextPacket:
    """The planner payload plus a safe summary suitable for run evidence."""

    payload: Dict[str, Any]
    rendered: str
    evidence: Dict[str, Any]


class ContextBuilder:
    """Build deterministic, bounded context without leaking private settings."""

    def __init__(self, max_chars: int = 8000, max_items: int = 24, max_string_chars: int = 1200):
        if max_chars < 512:
            raise ValueError("max_chars must be at least 512")
        if max_items < 1 or max_string_chars < 80:
            raise ValueError("context limits are too small")
        self.max_chars = max_chars
        self.max_items = max_items
        self.max_string_chars = max_string_chars

    def build(
        self,
        *,
        request: str,
        resolved_request: Optional[str] = None,
        session_id: Optional[str] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        available_tools: Optional[Iterable[str]] = None,
        planner_kind: Optional[str] = None,
    ) -> ContextPacket:
        original = self._text(request)
        resolved = self._text(resolved_request) or original
        sections: Dict[str, Any] = {
            "request": {
                "original": original,
                "resolved": resolved,
                "is_follow_up": resolved != original,
            },
            "session": {"bound": bool(session_id)},
            "workflow": self._safe_value(workflow or {}),
            "available_tools": self._safe_value(list(available_tools or [])),
        }
        if planner_kind:
            sections["planner"] = {"kind": self._text(planner_kind)}

        rendered, truncated = self._bounded_render(sections)
        section_chars = {
            name: len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            for name, value in sections.items()
        }
        evidence = {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "available": True,
            "budget_chars": self.max_chars,
            "input_chars": len(rendered),
            "truncated": truncated,
            "section_chars": section_chars,
            "section_names": list(sections),
            "request_sha256": hashlib.sha256(resolved.encode("utf-8")).hexdigest(),
            "session_bound": bool(session_id),
        }
        return ContextPacket(
            payload={"schema_version": CONTEXT_SCHEMA_VERSION, "sections": sections},
            rendered=rendered,
            evidence=evidence,
        )

    def _bounded_render(self, sections: Dict[str, Any]):
        rendered = self._render(sections)
        if len(rendered) <= self.max_chars:
            return rendered, False
        truncated = False
        for name in ("available_tools", "workflow", "planner"):
            if len(rendered) <= self.max_chars:
                break
            if name in sections:
                sections[name] = {"omitted": True, "reason": "context_budget"}
                rendered = self._render(sections)
                truncated = True
        if len(rendered) > self.max_chars:
            request_section = sections["request"]
            keep = max(40, self.max_chars // 3)
            for key in ("original", "resolved"):
                value = request_section.get(key, "")
                request_section[key] = value[:keep] + ("…" if len(value) > keep else "")
            rendered = self._render(sections)
            truncated = True
        if len(rendered) > self.max_chars:
            # Fit the request structurally; cutting a serialized JSON string
            # would make the planner payload unparsable.
            original = sections["request"].get("original", "")
            resolved = sections["request"].get("resolved", "")
            low, high, best = 0, max(len(original), len(resolved)), ""
            while low <= high:
                middle = (low + high) // 2
                candidate = dict(sections)
                candidate["request"] = {
                    "original": original[:middle],
                    "resolved": resolved[:middle],
                    "is_follow_up": sections["request"].get("is_follow_up", False),
                }
                candidate_rendered = self._render(candidate)
                if len(candidate_rendered) <= self.max_chars:
                    best = candidate_rendered
                    sections.clear()
                    sections.update(candidate)
                    low = middle + 1
                else:
                    high = middle - 1
            rendered = best or self._render({"request": {"omitted": True, "reason": "context_budget"}})
            truncated = True
        return rendered, truncated

    @staticmethod
    def _render(sections: Mapping[str, Any]) -> str:
        return json.dumps(
            {"schema_version": CONTEXT_SCHEMA_VERSION, "sections": sections},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _safe_value(self, value: Any, depth: int = 0) -> Any:
        if depth > 3:
            return "[omitted:depth]"
        if isinstance(value, Mapping):
            safe = {}
            for key, item in list(value.items())[: self.max_items]:
                key_text = str(key)
                if any(part in key_text.lower() for part in _SENSITIVE_PARTS):
                    continue
                safe[key_text[:80]] = self._safe_value(item, depth + 1)
            return safe
        if isinstance(value, (list, tuple, set)):
            return [self._safe_value(item, depth + 1) for item in list(value)[: self.max_items]]
        if isinstance(value, str):
            return value[: self.max_string_chars] + ("…" if len(value) > self.max_string_chars else "")
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)[: self.max_string_chars]

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()
