"""Structured observability with OpenTelemetry-style span tracing (M80.3).

Emits JSON-lines events for every run and every step so the execution path is
machine-readable for standard log/observability pipelines. The span model maps
OpenTelemetry concepts (trace_id, span_id, parent_span_id, name, status,
duration) but is implemented with the standard library only.

Events are bounded and credential-free: attributes only carry allowlisted
fields (session id, backend, error category/code/phase/retryability, replan
count, memory fact count, step attempts/latency/result type). Raw error text,
provider responses, URLs, keys, and file paths are never emitted.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional, TextIO

OBSERVABILITY_SCHEMA_VERSION = "spatial-agent.observability.v1"

_OBSERVABILITY_ENV = "SPATIAL_AGENT_OBSERVABILITY"
_LOG_PATH_ENV = "SPATIAL_AGENT_OBSERVABILITY_LOG"
_STDOUT_ENV = "SPATIAL_AGENT_OBSERVABILITY_STDOUT"

_RUN_ALLOWED_ATTRIBUTES = {
    "session_id",
    "backend",
    "planner",
    "result_type",
    "error_category",
    "error_code",
    "failure_phase",
    "failure_retryable",
    "replan_count",
    "memory_fact_count",
}
_STEP_ALLOWED_ATTRIBUTES = {
    "attempts",
    "error_category",
    "error_code",
    "result_type",
}


def observability_enabled() -> bool:
    raw = os.environ.get(_OBSERVABILITY_ENV)
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _stdout_requested() -> bool:
    """Observability only writes to stdout when explicitly requested.

    CLI tools (smoke_check, run_demo) parse stdout as pure JSON, so the
    emitter must never pollute it by default.
    """
    raw = os.environ.get(_STDOUT_ENV)
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _log_stream() -> Optional[TextIO]:
    path = os.environ.get(_LOG_PATH_ENV)
    if path:
        return open(path, "a", encoding="utf-8")
    return None


class ObservabilityEmitter:
    """Emits structured JSON-lines events for runs and steps.

    Output goes to a configured log file, or to stdout only when
    SPATIAL_AGENT_OBSERVABILITY_STDOUT=1. By default events are counted but
    not written anywhere, so CLI tools that parse stdout stay clean.
    """

    def __init__(self, enabled: Optional[bool] = None) -> None:
        self._enabled = observability_enabled() if enabled is None else enabled
        self._owned_stream: Optional[TextIO] = None
        self._stream: Optional[TextIO] = None
        self._event_count = 0
        if self._enabled:
            self._owned_stream = _log_stream()
            if self._owned_stream is not None:
                self._stream = self._owned_stream
            elif _stdout_requested():
                self._stream = sys.stdout

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def event_count(self) -> int:
        return self._event_count

    def emit_run(
        self,
        *,
        run_id: str,
        session_id: Optional[str],
        name: str,
        status: str,
        duration_ms: Optional[float],
        attributes: Optional[Dict[str, Any]] = None,
        span_id: Optional[str] = None,
    ) -> None:
        self._emit(
            "run",
            span_id=span_id or _new_span_id(),
            parent_span_id=None,
            name=name,
            status=status,
            duration_ms=duration_ms,
            attributes=attributes,
            run_id=run_id,
            session_id=session_id,
        )

    def emit_step(
        self,
        *,
        run_id: str,
        parent_span_id: str,
        name: str,
        status: str,
        duration_ms: Optional[float],
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._emit(
            "step",
            span_id=_new_span_id(),
            parent_span_id=parent_span_id,
            name=name,
            status=status,
            duration_ms=duration_ms,
            attributes=attributes,
            run_id=run_id,
            session_id=None,
        )

    def close(self) -> None:
        if self._owned_stream is not None:
            try:
                self._owned_stream.close()
            except OSError:
                pass
            self._owned_stream = None
            self._stream = None

    def _emit(
        self,
        kind: str,
        *,
        span_id: str,
        parent_span_id: Optional[str],
        name: str,
        status: str,
        duration_ms: Optional[float],
        attributes: Optional[Dict[str, Any]],
        run_id: str,
        session_id: Optional[str],
    ) -> None:
        if not self._enabled:
            return
        allowed = _ALLOWED_RUN if kind == "run" else _ALLOWED_STEP
        safe_attributes = {
            key: value
            for key, value in (attributes or {}).items()
            if key in allowed and _attribute_ok(value)
        }
        event = {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event": kind,
            "trace_id": run_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "name": str(name),
            "status": str(status),
            "duration_ms": round(float(duration_ms), 3) if duration_ms is not None else None,
            "timestamp": time.time(),
        }
        if session_id is not None:
            event["session_id"] = str(session_id)
        if safe_attributes:
            event["attributes"] = safe_attributes
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
        if self._stream is not None:
            self._stream.write(line + "\n")
            self._stream.flush()
        self._event_count += 1


class CollectingEmitter(ObservabilityEmitter):
    """Test emitter that keeps events in memory instead of writing to stdout."""

    def __init__(self, enabled: Optional[bool] = None) -> None:
        super().__init__(enabled=observability_enabled() if enabled is None else enabled)
        self.events: list[Dict[str, Any]] = []

    def _emit(self, *args, **kwargs) -> None:
        # Rebuild the JSON line and parse it back so tests validate the wire format.
        if not self._enabled:
            return
        from io import StringIO

        buffer = StringIO()
        previous = self._stream
        self._stream = buffer
        try:
            super()._emit(*args, **kwargs)
        finally:
            self._stream = previous
        for line in buffer.getvalue().splitlines():
            if line:
                self.events.append(json.loads(line))


def _new_span_id() -> str:
    return uuid.uuid4().hex[:16]


def _attribute_ok(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str) and len(value) <= 120:
        return True
    return False


_ALLOWED_RUN = _RUN_ALLOWED_ATTRIBUTES
_ALLOWED_STEP = _STEP_ALLOWED_ATTRIBUTES
