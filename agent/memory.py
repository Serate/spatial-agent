"""Cross-session fact memory (M80.2).

Every completed run can leave one structured conclusion (a "fact") behind:
result type, admin areas involved, a bounded summary, and a few key metrics.
Planner calls for the same session can then be given a bounded "previous
conclusions" section so follow-ups do not have to re-derive what is already
known. Cross-session recall exists but is only used through explicit
contracts; the planner injection stays session-scoped to avoid leaking other
conversations.

Evidence is bounded and credential-free: summaries are truncated, facts only
carry allowlisted scalar metrics, and raw error text / URLs / keys / file
paths are never stored.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .models import AgentRunResult, RunStatus

_MEMORY_ENV = "SPATIAL_AGENT_MEMORY_ENABLED"
_SUMMARY_LIMIT = 200
_MAX_FACTS_PER_RUN = 6
_MAX_RECALL = 8

_ALLOWED_FACT_KEYS = {
    "admin_name",
    "admin_names",
    "result_type",
    "candidate_pixel_count",
    "candidate_ratio",
    "valid_pixel_count",
    "mean",
    "standard_deviation",
    "nodata_ratio",
    "category_count",
    "eligible_features",
    "water_excluded_features",
    "feature_count",
}


def memory_enabled() -> bool:
    raw = os.environ.get(_MEMORY_ENV)
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _truncate(text: Any, limit: int = _SUMMARY_LIMIT) -> str:
    value = str(text or "")
    return value[:limit] + ("…" if len(value) > limit else "")


def _extract_facts(result: AgentRunResult) -> Dict[str, Any]:
    """Pull allowlisted scalar facts from step results."""
    facts: Dict[str, Any] = {}
    for step in result.steps:
        payload = step.result if isinstance(step.result, dict) else {}
        statistics = payload.get("statistics")
        if isinstance(statistics, dict):
            for key in _ALLOWED_FACT_KEYS:
                if key in statistics and key not in facts:
                    facts[key] = statistics[key]
        constraint = payload.get("constraint_summary")
        if isinstance(constraint, dict):
            for key in ("eligible_features", "water_excluded_features"):
                if key in constraint and key not in facts:
                    facts[key] = constraint[key]
        admin = payload.get("admin_name")
        if admin and "admin_name" not in facts:
            facts["admin_name"] = str(admin)
    return {key: value for key, value in facts.items() if _fact_value_ok(value)}


def _fact_value_ok(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str) and len(value) <= 80:
        return True
    return False


class FactMemory:
    """Owns memory facts with in-memory and SQLite modes (like ConversationStore)."""

    def __init__(self, sqlite_conversation_store: Any = None) -> None:
        self._store = sqlite_conversation_store
        self._facts: List[Dict[str, Any]] = []
        self._enabled = memory_enabled()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def remember(self, result: AgentRunResult) -> Optional[Dict[str, Any]]:
        """Persist one bounded fact for a completed run; returns the fact."""
        if not self._enabled:
            return None
        if result.status != RunStatus.COMPLETED:
            return None
        extracted = _extract_facts(result)
        fact = {
            "run_id": result.run_id,
            "session_id": result.session_id or "default",
            "result_type": _result_type(result),
            "admin_names": _admin_names(result),
            "summary": _truncate(result.answer),
            "facts": dict(list(extracted.items())[:_MAX_FACTS_PER_RUN]),
            "created_at": time.time(),
        }
        if self._store is not None and hasattr(self._store, "insert_memory_fact"):
            self._store.insert_memory_fact(fact)
        else:
            self._facts.append(fact)
        return fact

    def recall(
        self,
        session_id: str,
        query: Optional[str] = None,
        limit: int = _MAX_RECALL,
    ) -> List[Dict[str, Any]]:
        """Return session-scoped facts, newest first, optionally filtered."""
        if not self._enabled:
            return []
        if self._store is not None and hasattr(self._store, "list_memory_facts"):
            facts = self._store.list_memory_facts(session_id=session_id, limit=limit)
        else:
            facts = [fact for fact in self._facts if fact.get("session_id") == session_id]
            facts = facts[-limit:][::-1]
        if query:
            terms = [term for term in str(query or "").lower().split() if term]
            if terms:
                facts = [
                    fact
                    for fact in facts
                    if any(
                        term in str(fact.get("result_type") or "").lower()
                        or term in str(fact.get("admin_names") or "").lower()
                        or term in str(fact.get("summary") or "").lower()
                        for term in terms
                    )
                ]
        return facts

    def recall_global(self, query: Optional[str] = None, limit: int = _MAX_RECALL) -> List[Dict[str, Any]]:
        """Cross-session recall for explicit contracts only (no planner injection)."""
        if not self._enabled:
            return []
        if self._store is not None and hasattr(self._store, "list_memory_facts"):
            facts = self._store.list_memory_facts(session_id=None, limit=limit)
        else:
            facts = self._facts[-limit:][::-1]
        if query:
            terms = [term for term in str(query or "").lower().split() if term]
            if terms:
                facts = [
                    fact
                    for fact in facts
                    if any(
                        term in str(fact.get("result_type") or "").lower()
                        or term in str(fact.get("admin_names") or "").lower()
                        or term in str(fact.get("summary") or "").lower()
                        for term in terms
                    )
                ]
        return facts

    def context_section(self, session_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Bounded section for planner context: session-scoped previous conclusions."""
        facts = self.recall(session_id=session_id, query=query, limit=_MAX_RECALL)
        if not facts:
            return {"available": False, "fact_count": 0, "facts": []}
        return {
            "available": True,
            "fact_count": len(facts),
            "facts": [
                {
                    "result_type": fact.get("result_type"),
                    "admin_names": list(fact.get("admin_names") or []),
                    "summary": _truncate(fact.get("summary"), 120),
                }
                for fact in facts
            ],
        }

    def evidence(self, session_id: str) -> Dict[str, Any]:
        """Bounded evidence attached to a run result: remembered + injected counts."""
        return {
            "enabled": self._enabled,
            "session_fact_count": len(self.recall(session_id=session_id)),
        }

    def clear_session(self, session_id: str) -> None:
        if self._store is not None and hasattr(self._store, "delete_memory_facts"):
            self._store.delete_memory_facts(session_id)
            return
        self._facts = [fact for fact in self._facts if fact.get("session_id") != session_id]


def _admin_names(result: AgentRunResult) -> List[str]:
    names: List[str] = []
    for step in result.steps:
        payload = step.result if isinstance(step.result, dict) else {}
        name = payload.get("admin_name")
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    return names[:4]


def _result_type(result: AgentRunResult) -> str:
    plan = result.plan
    if plan is not None:
        output_type = (plan.output or {}).get("type")
        if output_type:
            return str(output_type)
    return "unknown"
