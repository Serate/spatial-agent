"""Canonical bounded service inspection application.

Metrics and memory are read-only operational projections.  They share state,
Domain scoping and async observation rules, so keeping them here gives HTTP,
CLI and tests one consistent inspection seam while leaving the main service
facade focused on composition.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from agent.artifact_store import ArtifactStore


class InspectionApplication:
    """Project operational metrics and bounded memory facts."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        state: Any,
        domain_id: Callable[[], Optional[str]],
        worker_count: int,
        async_metrics: Callable[[], Dict[str, Any]],
    ) -> None:
        self._artifact_store = artifact_store
        self._state = state
        self._domain_id = domain_id
        self._worker_count = worker_count
        self._async_metrics = async_metrics

    def metrics(self) -> Dict[str, Any]:
        domain_id = self._domain_id()
        if self._state.persistent:
            metrics = self._state.store_metrics(domain_id=domain_id)
            metrics.setdefault("async_jobs", {})["worker_count"] = self._worker_count
        else:
            metrics = self._artifact_store.metrics(domain_id=domain_id)
            metrics["async_jobs"] = self._async_metrics()
        metrics["cost_governance"] = self._state.cost.summary()
        metrics["actions"] = self._artifact_store.action_metrics(domain_id=domain_id)
        metrics["observability"] = {
            "schema_version": "spatial-agent.observability.v1",
            "event_count": self._state.observability.event_count,
        }
        return metrics

    def list_memory(
        self,
        session_id: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 20,
        global_scope: bool = False,
    ) -> Dict[str, Any]:
        """Return bounded memory facts, with global scope explicit."""
        if global_scope:
            facts = self._state.memory.recall_global(query=query, limit=limit)
        else:
            if not isinstance(session_id, str) or not session_id.strip():
                raise ValueError("session_id must be a non-empty string")
            facts = self._state.memory.recall(
                session_id=session_id,
                query=query,
                limit=limit,
            )
        return {
            "memory_enabled": self._state.memory.enabled,
            "global_scope": bool(global_scope),
            "fact_count": len(facts),
            "facts": [
                {
                    "run_id": fact.get("run_id"),
                    "session_id": fact.get("session_id"),
                    "result_type": fact.get("result_type"),
                    "admin_names": list(fact.get("admin_names") or []),
                    "summary": fact.get("summary"),
                    "facts": dict(fact.get("facts") or {}),
                }
                for fact in facts
            ],
        }


__all__ = ["InspectionApplication"]
