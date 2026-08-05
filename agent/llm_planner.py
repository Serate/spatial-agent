import json
import os
import urllib.error
import urllib.parse
import urllib.request
from time import perf_counter
from typing import Any, Dict, Mapping, Optional, Protocol

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
        return parse_task_plan(_normalize_shortcut_plan(payload), self._allowed_tools)

    def metrics(self) -> Dict[str, Any]:
        provider_metrics = getattr(self._client, "metrics", None)
        if callable(provider_metrics):
            return provider_metrics()
        return {}

    def _system_prompt(self) -> str:
        tools = ", ".join(self._allowed_tools)
        return (
            "You are the planner for a spatial data Agent Runtime. "
            "Return only a JSON object that matches the provided schema. "
            "Use only registered tools: "
            + tools
            + ". "
            "Allowed datasets: roads, slope, admin_areas, dem, land_use. "
            "For DEM or land use value statistics, use tool get_raster_statistics with "
            "args {\"dataset\":\"dem\",\"max_files\":3}. "
            "For DEM, elevation, or terrain raster metadata requests, use tool "
            "get_raster_metadata with args {\"dataset\":\"dem\",\"max_files\":3}. "
            "For land use raster metadata requests, use tool get_raster_metadata "
            "with args {\"dataset\":\"land_use\",\"max_files\":3}. "
            "For admin boundary requests with a named district/county, use "
            "get_dataset_schema on admin_areas and range_query on admin_areas where "
            "field name equals the requested area name. The exact range_query args "
            "must be {\"dataset\":\"admin_areas\",\"conditions\":[{\"field\":\"name\","
            "\"operator\":\"eq\",\"value\":\"洪山区\"}],\"limit\":100}. "
            "For road and slope proximity requests, use get_dataset_schema, range_query, "
            "and spatial_join as needed. "
            "For successful requests, never return an outcome/tool/args shortcut. "
            "Always return a complete plan with goal, steps, and output. "
            "The exact success shape is {\"goal\":\"...\",\"steps\":["
            "{\"id\":\"...\",\"tool\":\"registered_tool\",\"args\":{},"
            "\"depends_on\":[]}],\"output\":{\"type\":\"...\"}}. "
            "steps must be an array of objects, never strings or arrays. "
            "output must be an object, never a string, array, or null. "
            "Do not invent tools. Do not generate SQL, shell commands, or code. "
            "If the request is missing required spatial constraints, return "
            "{\"outcome\":\"needs_clarification\",\"message\":\"...\"}. "
            "If the request asks for destructive, unauthorized, or oversized actions, return "
            "{\"outcome\":\"rejected\",\"message\":\"...\"}."
        )


class OpenAIPlannerClient:
    """Minimal OpenAI Responses API client using the standard library."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_url: Optional[str] = None,
        base_url: Optional[str] = None,
        wire_api: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        auth_location: Optional[str] = None,
        api_key_query_param: Optional[str] = None,
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise PlanningError("OPENAI_API_KEY is required for OpenAIPlannerClient")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
        self._wire_api = wire_api or os.environ.get("OPENAI_WIRE_API", "responses")
        if self._wire_api not in ("responses", "chat_completions"):
            raise PlanningError("OPENAI_WIRE_API must be responses or chat_completions")
        self._url = _planner_url(
            api_url=api_url or os.environ.get("OPENAI_API_URL"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com",
            wire_api=self._wire_api,
        )
        self._reasoning_effort = reasoning_effort or os.environ.get(
            "OPENAI_REASONING_EFFORT", "medium"
        )
        self._max_output_tokens = max_output_tokens or _env_int("OPENAI_MAX_OUTPUT_TOKENS")
        self._timeout_seconds = timeout_seconds or _env_float("OPENAI_TIMEOUT_SECONDS") or 60.0
        self._auth_location = auth_location or os.environ.get("OPENAI_AUTH_LOCATION", "header")
        self._api_key_query_param = api_key_query_param or os.environ.get(
            "OPENAI_API_KEY_QUERY_PARAM", "key"
        )
        self._last_metrics = {
            "provider": "openai-compatible",
            "wire_api": self._wire_api,
            "model": self._model,
        }

    def complete_json(self, messages, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._wire_api == "chat_completions":
            body = {
                "model": self._model,
                "messages": messages,
                "response_format": {"type": "json_object"},
            }
            if self._max_output_tokens is not None:
                body["max_tokens"] = self._max_output_tokens
        else:
            body = {
                "model": self._model,
                "input": messages,
                "reasoning": {"effort": self._reasoning_effort},
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "task_plan",
                        "schema": schema,
                        "strict": True,
                    }
                },
            }
            if self._max_output_tokens is not None:
                body["max_output_tokens"] = self._max_output_tokens
        url = self._request_url()
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        started = perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self._last_metrics = dict(self._last_metrics)
            self._last_metrics["latency_ms"] = round((perf_counter() - started) * 1000, 3)
            self._last_metrics["usage"] = _usage_summary(payload.get("usage"))
        except urllib.error.HTTPError as exc:
            self._record_error(started, "http_error")
            detail = exc.read().decode("utf-8", errors="replace")
            raise PlanningError("OpenAI request failed: " + detail) from exc
        except urllib.error.URLError as exc:
            self._record_error(started, "url_error")
            raise PlanningError("OpenAI request failed: " + str(exc)) from exc
        except TimeoutError as exc:
            self._record_error(started, "timeout")
            raise PlanningError("OpenAI request timed out") from exc

        text = self._extract_text(payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise PlanningError("OpenAI response was not valid JSON") from exc

    def metrics(self) -> Dict[str, Any]:
        return dict(self._last_metrics)

    def _record_error(self, started: float, error_type: str) -> None:
        self._last_metrics = dict(self._last_metrics)
        self._last_metrics["latency_ms"] = round((perf_counter() - started) * 1000, 3)
        self._last_metrics["error_type"] = error_type

    def _extract_text(self, payload: Mapping[str, Any]) -> str:
        if self._wire_api == "chat_completions":
            choices = payload.get("choices", [])
            if choices and isinstance(choices[0], Mapping):
                message = choices[0].get("message", {})
                if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                    return message["content"]
            raise PlanningError("Chat Completions response did not contain message content")
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

    def _request_url(self) -> str:
        if self._auth_location == "query":
            return _append_query_param(self._url, self._api_key_query_param, self._api_key)
        return self._url

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "spatial-agent/0.1",
        }
        if self._auth_location == "header":
            headers["Authorization"] = "Bearer " + self._api_key
        elif self._auth_location != "query":
            raise PlanningError("OPENAI_AUTH_LOCATION must be one of: header, query")
        return headers


def _planner_url(api_url: Optional[str], base_url: str, wire_api: str = "responses") -> str:
    if api_url:
        return api_url.rstrip("/")
    if wire_api == "chat_completions":
        return _chat_completions_url(base_url)
    return _responses_url(base_url)


def _responses_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/responses"):
        return clean
    if clean.endswith("/v1"):
        return clean + "/responses"
    return clean + "/v1/responses"


def _chat_completions_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    if clean.endswith("/v1"):
        return clean + "/chat/completions"
    return clean + "/chat/completions"


def _append_query_param(url: str, key: str, value: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not any(item_key == key for item_key, _ in query):
        query.append((key, value))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query),
            parsed.fragment,
        )
    )


def _env_int(name: str) -> Optional[int]:
    value = os.environ.get(name)
    return int(value) if value else None


def _env_float(name: str) -> Optional[float]:
    value = os.environ.get(name)
    return float(value) if value else None


def _usage_summary(usage: Any) -> Dict[str, int]:
    if not isinstance(usage, Mapping):
        return {}
    keys = (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
    )
    return {key: usage[key] for key in keys if isinstance(usage.get(key), int)}


def _normalize_shortcut_plan(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Expand the known single-tool response shape before TaskPlan validation."""
    if "goal" in payload or "steps" in payload:
        normalized = dict(payload)
        if isinstance(payload.get("steps"), list):
            normalized["steps"] = [
                _normalize_step_arguments(step) for step in payload["steps"]
            ]
        if isinstance(payload.get("output"), str):
            normalized["output"] = {"type": payload["output"]}
            return normalized
        return normalized
    if payload.get("outcome") not in (None, "success"):
        return payload
    tool = payload.get("tool")
    args = payload.get("args")
    if not isinstance(tool, str) or not isinstance(args, dict):
        return payload
    args = _normalize_step_arguments({"tool": tool, "args": args})["args"]
    return {
        "goal": "execute " + tool,
        "steps": [{"id": "step-1", "tool": tool, "args": args, "depends_on": []}],
        "output": {},
    }


def _normalize_step_arguments(step: Mapping[str, Any]) -> Mapping[str, Any]:
    """Normalize the known Chat Completions range_query shortcut."""
    if step.get("tool") != "range_query" or not isinstance(step.get("args"), dict):
        return step
    args = dict(step["args"])
    if "conditions" not in args and "field" in args and "value" in args:
        field = args.pop("field")
        value = args.pop("value")
        operator = args.pop("operator", "eq")
        args["conditions"] = [{"field": field, "operator": operator, "value": value}]
    if "conditions" in args and "limit" not in args:
        args["limit"] = 100
    normalized = dict(step)
    normalized["args"] = args
    return normalized
