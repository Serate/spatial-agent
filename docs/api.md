# Spatial Agent HTTP API

The HTTP API exposes the same Agent Runtime used by the CLI demo. Clients submit natural-language requests, receive structured run results, and reuse session_id for follow-up turns.

## Start The Server

~~~powershell
python serve_api.py --host 127.0.0.1 --port 8088
~~~

Open `http://127.0.0.1:8088/` for the interactive Spatial Agent Console. The page uses the same `/runs` and artifact endpoints documented below and has no third-party runtime dependency.

## Production deployment

Production uses `production_api:app` behind Uvicorn, with GDAL/Rasterio/PROJ fixed inside the container. Copy `.env.production.example` to `.env.production`, set `SPATIAL_AGENT_HOST_DATASET_ROOT` to the host GIS data directory, provide model settings without committing the file, and start with:

```text
docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d
```

`SPATIAL_AGENT_HOST_DATASET_ROOT` is used by Compose for the read-only `/data` bind mount. The `--env-file` option is required because a Compose `env_file` passes variables into the container but does not participate in host-side volume interpolation.

The container uses a domestic Docker proxy for the base image and Tsinghua University's Conda mirror for GIS packages. It sets `GDAL_DATA`, `PROJ_LIB`, `SPATIAL_AGENT_DATASET_CONFIG`, and `SPATIAL_AGENT_REQUIRE_GIS` itself. It does not depend on `conda activate` or the operator's shell. Conversation state and run snapshots are persisted in `outputs/spatial-agent.db` through `SPATIAL_AGENT_STATE_DB`, so the production container can use multiple Uvicorn workers. Use `/health/live` for process liveness and `/health/ready` for GIS readiness; a missing required GIS dependency, GDAL/PROJ data directory, or data mount returns HTTP 503 from readiness.

For local GIS backend demos, start the server from the GIS conda environment so GeoPandas and Rasterio are available:

~~~powershell
& 'D:\code\conda\Scripts\conda.exe' run -n spatial-agent-gis python serve_api.py --host 127.0.0.1 --port 8088
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
| timeout_seconds | no | none | Optional cooperative run budget; Runtime stops at a step boundary after the budget is exceeded. |

For raster value analysis, use a request such as `分析DEM高程统计`. The planner selects `get_raster_statistics`, which returns bounded statistics for sampled files and does not expose raster arrays through the API.

Raster statistics also include a bounded `statistics.distribution` summary. Its `bins` are generated from at most 10,000 sampled valid pixels, so the Console can show a lightweight value-distribution chart without transferring raster arrays.

For a multi-source terrain overview, use `分析洪山区的高程、坡度和土地利用分布`. The rule planner executes elevation zonal statistics, derives slope in degrees from DEM pixels, and returns land-use raster class counts and shares. Land-use values remain source raster codes; the Agent does not invent semantic labels. Construction suitability requires explicit thresholds and weights and is therefore not inferred from this overview.

For the demo construction screening workflow, use `分析洪山区建设适宜性，坡度不超过20度`. The planner combines administrative lookup, DEM elevation, derived slope, land-use classes, and a bounded buildability screening. The result reports candidate pixel ratio and can export a limited candidate-area GeoJSON; it is an auditable demo screen, not a legal planning or permit conclusion.

For administrative-area raster analysis, use a request such as `分析洪山区DEM高程概况`. The planner selects `get_zonal_raster_statistics`, which resolves the named area, converts its CRS for each raster file, and computes masked statistics only where the geometry intersects the raster.

## POST /runs/{run_id}/retry

Retries a failed run from its first failed step. The runtime reuses completed step results and does not call the Planner again. The request body accepts the same `planner`, `backend`, `export_artifact`, and `export_geojson` fields as needed.

## POST /runs/{run_id}/cancel

Requests cooperative cancellation of an active run. The current tool is allowed to return; Runtime then stops before the next step and returns `CANCELLED`. It does not forcibly terminate third-party code.

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

复合任务还会返回安全的 `provenance` 字段，包含 `execution_policy` 和每个步骤的 `depends_on`、`input_bindings`、`result_ref` 与受限统计摘要。它不包含原始工具参数、完整几何或凭据。

## Planner 评测

使用规则规划器执行离线评测：

~~~powershell
python scripts/evaluate_planner.py --planner rule --backend memory --output outputs/evaluation.json
~~~

报告包含状态/工具匹配率、依赖链有效率、平均步骤耗时、Planner 延迟和 Token 总量。默认只输出报告；加 `--strict` 才会在有失败用例时返回非零。只有显式指定 `--planner openai` 时才会调用真实模型。

## GET Artifact Files

Exported files can be read through the API without exposing arbitrary filesystem paths:

~~~text
GET /artifacts/runs/<run-id>.json
GET /artifacts/geojson/<run-id>.geojson
~~~

Only files below the configured artifact directories and with the expected suffix are served. Path traversal and unknown artifact types return 404.

## GET /health

Returns service readiness and safe local capability information for the web Console. It does not return secrets, provider responses, or raw dataset paths.

Example response:

~~~json
{
  "status": "ok",
  "python": "C:\\Users\\...\\python.exe",
  "capabilities": {
    "memory_backend": true,
    "local_gis_backend": true,
    "live_llm": true,
    "live_llm_configured": true,
    "live_llm_network": true
  },
  "dependencies": {
    "geopandas": true,
    "rasterio": true
  },
  "data": {
    "dataset_root_exists": true
  }
}
~~~

Capability meanings:

| Field | Meaning |
|---|---|
| memory_backend | Deterministic in-memory demo backend is available. |
| local_gis_backend | GeoPandas, Rasterio, and the configured dataset root are available in this server process. |
| live_llm_configured | A live planner configuration is present through environment variables or config/openai.local.json. |
| live_llm_network | The server process can open a short TCP connection to the configured provider host without sending a model request. |
| live_llm | Both live_llm_configured and live_llm_network are true, so the Console may attempt a live planner request. |

The Console uses this endpoint to warn before running a local GIS request from the wrong Python environment, a live model request without model configuration, or a service process whose outbound sockets are blocked.

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

`max_output_tokens`、`timeout_seconds` 可限制成本和单次等待时间。当前示例配置使用 `max_output_tokens=10000`；这是输出上限，不会强制模型消耗 10000 tokens。运行结果中的 `planner_metrics` 只包含 provider、wire_api、model、耗时、错误类型和 provider 返回的 token usage，不包含 prompt、响应原文或密钥。

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
- When using the web Console with a live planner, start `serve_api.py` from a process that is allowed outbound network access; a restricted server process can serve the page while returning WinError 10013 for model requests.
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

`export_geojson=true` produces a small `FeatureCollection` whose features summarize tool steps. The local admin backend can provide bounded real geometry on this explicit export path; memory and raster results use `null` geometry because they expose result references and metrics rather than raw geometries.
