import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Mapping, Protocol

from .errors import ClarificationNeeded, PlanningError, RequestRejected
from .models import TaskPlan
from .plan_schema import parse_task_plan, task_plan_schema


class LLMClient(Protocol):
    def complete_json(self, messages, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class LLMPlanner:
    """Planner Adapter that constrains model output to TaskPlan JSON."""

    def __init__(self, client: LLMClient, allowed_tools):
        self._client = client
        self._allowed_tools = tuple(allowed_tools)

    def plan(self, request: str) -> TaskPlan:
        if not request.strip():
            raise ClarificationNeeded("empty spatial analysis request")
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": request,
            },
        ]
        payload = self._client.complete_json(messages, task_plan_schema())
        outcome = payload.get("outcome")
        if outcome == "needs_clarification":
            raise ClarificationNeeded(str(payload.get("message", "planner needs clarification")))
        if outcome == "rejected":
            raise RequestRejected(str(payload.get("message", "request rejected by planner")))
        return parse_task_plan(payload, self._allowed_tools)

    def _system_prompt(self) -> str:
        tools = ", ".join(self._allowed_tools)
        return (
            "You are the planner for a spatial data Agent Runtime. "
            "Return only a JSON object that matches the provided schema. "
            "Use only registered tools: "
            + tools
            + ". "
            "Do not invent tools. Do not generate SQL, shell commands, or code. "
            "If the request is missing required spatial constraints, return "
            "{\"outcome\":\"needs_clarification\",\"message\":\"...\"}. "
            "If the request asks for destructive, unauthorized, or oversized actions, return "
            "{\"outcome\":\"rejected\",\"message\":\"...\"}."
        )


class OpenAIPlannerClient:
    """Minimal OpenAI Responses API client using the standard library."""

    def __init__(self, api_key=None, model=None, base_url="https://api.openai.com/v1/responses"):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise PlanningError("OPENAI_API_KEY is required for OpenAIPlannerClient")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        self._base_url = base_url

    def complete_json(self, messages, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        body = {
            "model": self._model,
            "input": messages,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "task_plan",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        request = urllib.request.Request(
            self._base_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PlanningError("OpenAI request failed: " + detail) from exc
        except urllib.error.URLError as exc:
            raise PlanningError("OpenAI request failed: " + str(exc)) from exc

        text = self._extract_text(payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise PlanningError("OpenAI response was not valid JSON") from exc

    def _extract_text(self, payload: Mapping[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        chunks = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    chunks.append(content.get("text", ""))
        if chunks:
            return "".join(chunks)
        raise PlanningError("OpenAI response did not contain output text")
