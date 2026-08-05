# Spatial Agent HTTP API

The HTTP API exposes the same Agent Runtime used by the CLI demo. Clients submit natural-language requests, receive structured run results, and reuse session_id for follow-up turns.

## Start The Server

~~~powershell
python serve_api.py --host 127.0.0.1 --port 8088
~~~

## GET /health

Returns a basic process health response.

~~~json
{
  "status": "ok"
}
~~~

## POST /runs

Runs one Agent turn.

Request body:

~~~json
{
  "request": "查询洪山区行政区边界",
  "session_id": "demo",
  "planner": "rule",
  "backend": "local"
}
~~~

Fields:

| Field | Required | Default | Description |
|---|---:|---|---|
| request | yes | none | Natural-language task for the Agent. |
| session_id | no | default | Conversation scope for clarification state. |
| planner | no | rule | rule for deterministic demos, openai for LLM planning. |
| backend | no | memory | memory for deterministic tests, local for configured local spatial data. |
| export_artifact | no | false | When true, writes a small run summary artifact and returns artifact_ref. |
| export_geojson | no | false | When true, writes a bounded GeoJSON summary and returns geojson_ref. |

Successful response shape:

~~~json
{
  "run_id": "uuid",
  "status": "COMPLETED",
  "request": "查询洪山区行政区边界",
  "resolved_request": "查询洪山区行政区边界",
  "answer": "已找到 1 个匹配行政区：洪山区。",
  "artifact_ref": "outputs/runs/<run_id>.json",
  "trace_summary": [
    "Received request: 查询洪山区行政区边界",
    "Planned goal: query admin area boundary by name",
    "Tool range_query(admin_areas) completed, returned 1 result(s)."
  ],
  "error": null
}
~~~

## Multi-Turn Clarification

First turn:

~~~powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/runs -ContentType "application/json" -Body '{"request":"查询行政区边界","session_id":"demo"}'
~~~

Follow-up turn using the same session_id:

~~~powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/runs -ContentType "application/json" -Body '{"request":"洪山区","session_id":"demo"}'
~~~

## Error Responses

Invalid or empty request:

~~~json
{
  "error": "request must be a non-empty string"
}
~~~

Unsupported planner:

~~~json
{
  "error": "planner must be one of: rule, openai"
}
~~~

Unsupported backend:

~~~json
{
  "error": "backend must be one of: memory, local"
}
~~~

## OpenAI Planner Configuration

The API server can use the same real LLM planner as the CLI by passing "planner": "openai".
Runtime configuration is read from environment variables first, then from config/openai.local.json.
The local JSON file is ignored by Git so API keys are not committed.

Example local config:

~~~json
{
  "OPENAI_API_KEY": "sk-your-key",
  "model": "gpt-5.6-luna",
  "wire_api": "responses",
  "model_reasoning_effort": "medium",
  "base_url": "https://api.openai.com",
  "api_url": null,
  "auth_location": "header",
  "api_key_query_param": "key"
}
~~~

DeepSeek 使用 Chat Completions 兼容模式，不要只替换 base_url：

~~~json
{
  "OPENAI_API_KEY": "your-deepseek-key",
  "model": "deepseek-v4-flash",
  "wire_api": "chat_completions",
  "base_url": "https://api.deepseek.com",
  "auth_location": "header"
}
~~~

也可以使用环境变量 `OPENAI_WIRE_API=chat_completions`。该模式使用 `/chat/completions`、`messages` 和 JSON object 输出；最终仍由 TaskPlan parser 和 ToolRegistry 校验。

For a provider that expects the key in the URL and does not use the OpenAI /v1/responses path, set api_url to the exact request URL and auth_location to query:

~~~json
{
  "OPENAI_API_KEY": "sk-your-key",
  "model": "gpt-5.6-luna",
  "model_reasoning_effort": "medium",
  "api_url": "https://provider.example/direct-endpoint",
  "auth_location": "query",
  "api_key_query_param": "key"
}
~~~

Codex provider check:

- Local Codex config uses model_provider custom, wire_api responses, requires_openai_auth true, and base_url https://crs.ruinique.com.
- That maps to this project's OpenAI-compatible mode: base_url plus Authorization bearer header.
- The query-key mode is retained only for providers whose own docs explicitly require key-in-URL authentication.

Troubleshooting notes from the M16 setup:

- Do not commit real credentials. Put provider credentials in config/openai.local.json; this file is ignored by Git via config/*.local.json.
- base_url is for OpenAI-compatible providers and is normalized to /v1/responses. api_url is exact and is used as-is; use it when the provider does not want /v1 or /responses.
- If local execution fails with WinError 10013, the OS or sandbox blocked outbound socket access. Retry only in an environment where network access is explicitly allowed.
- If the live planner reaches the provider but returns HTTP 403 Forbidden / error code 1010, check the HTTP client headers first. This provider rejects Python urllib's default User-Agent; the project client sets a spatial-agent User-Agent and Accept: application/json by default.
- Live model tests are intentionally skipped by default. Set SPATIAL_AGENT_LIVE_OPENAI=1 only for manual validation, not CI.

## Design Notes

- The API does not expose arbitrary tool execution.
- Planner output still flows through ToolRegistry validation.
- The API returns result_ref values instead of large geometries.
- session_id scopes clarification state and prevents unrelated clients from sharing pending context.
- Artifact export writes a compact run summary only, not raw spatial datasets.

## Artifact Viewer

Render an exported artifact as a standalone HTML file:

~~~powershell
python view_artifact.py outputs\runs\<run-id>.json
~~~

The viewer shows the request, plan goal, tool status, attempts, latency, safe result summaries, answer, and trace. It does not expose raw tool arguments, geometries, credentials, or provider responses.

`export_geojson=true` produces a small `FeatureCollection` whose features summarize tool steps. Current backends return `null` geometry because they expose result references and metrics rather than raw geometries; geometry-producing backends can be added later without changing the API flag.
