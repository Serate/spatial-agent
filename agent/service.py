from typing import Dict, Tuple

from agent.trace_formatter import format_trace
from run_demo import build_runtime


class AgentService:
    """Application boundary for running Agent sessions from a CLI or HTTP API."""

    def __init__(self):
        self._runtimes = {}

    def run(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        runtime = self._runtime(planner, backend)
        result = runtime.run(request, session_id=session_id)
        payload = result.to_dict()
        payload["trace_summary"] = format_trace(result)
        return payload

    def _runtime(self, planner: str, backend: str):
        key = _runtime_key(planner, backend)
        if key not in self._runtimes:
            self._runtimes[key] = build_runtime(planner, backend)
        return self._runtimes[key]


def _runtime_key(planner: str, backend: str) -> Tuple[str, str]:
    if planner not in ("rule", "openai"):
        raise ValueError("planner must be one of: rule, openai")
    if backend not in ("memory", "local"):
        raise ValueError("backend must be one of: memory, local")
    return planner, backend
