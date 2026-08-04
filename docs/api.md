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

## Design Notes

- The API does not expose arbitrary tool execution.
- Planner output still flows through ToolRegistry validation.
- The API returns result_ref values instead of large geometries.
- session_id scopes clarification state and prevents unrelated clients from sharing pending context.
- Artifact export writes a compact run summary only, not raw spatial datasets.
