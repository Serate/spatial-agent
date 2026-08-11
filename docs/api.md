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
  "backend": "local",
  "workflow": {
    "template_id": "raster_metadata",
    "constraints": {"dataset": "dem"},
    "evidence": ["summary", "metadata"]
  }
}
~~~

Fields:

| Field | Required | Default | Description |
|---|---:|---|---|
| request | yes | none | Natural-language task for the Agent. |
| session_id | no | default | Conversation scope for clarification state. |
| planner | no | rule | rule for deterministic demos, openai for LLM planning. |
| backend | no | memory | memory for deterministic tests, local for configured local spatial data. |
| workflow | no | none | Optional selection from `/workflows`; validated before planning and persisted in the run snapshot. |
| export_artifact | no | false | When true, writes a small run summary artifact and returns artifact_ref. |
| export_geojson | no | false | When true, writes a bounded GeoJSON summary and returns geojson_ref. |
| timeout_seconds | no | none | Optional cooperative run budget; Runtime stops at a step boundary after the budget is exceeded. |

For raster value analysis, use a request such as `分析DEM高程统计`. The planner selects `get_raster_statistics`, which returns bounded statistics for sampled files and does not expose raster arrays through the API.

Raster statistics also include a bounded `statistics.distribution` summary. Its `bins` are generated from at most 10,000 sampled valid pixels, so the Console can show a lightweight value-distribution chart without transferring raster arrays.

For a multi-source terrain overview, use `分析洪山区的高程、坡度和土地利用分布`. The rule planner executes elevation zonal statistics, derives slope in degrees from DEM pixels, and returns land-use raster class counts and shares. Land-use values remain source raster codes; the Agent does not invent semantic labels. Construction suitability requires explicit thresholds and weights and is therefore not inferred from this overview.

For the demo construction screening workflow, use `分析洪山区建设适宜性，坡度不超过20度`. The planner combines administrative lookup, DEM elevation, derived slope, land-use classes, and a bounded buildability screening. The result reports candidate pixel ratio and can export a limited candidate-area GeoJSON; it is an auditable demo screen, not a legal planning or permit conclusion.

For administrative-area raster analysis, use a request such as `分析洪山区DEM高程概况`. The planner selects `get_zonal_raster_statistics`, which resolves the named area, converts its CRS for each raster file, and computes masked statistics only where the geometry intersects the raster.

When `workflow` is supplied, its template, structured constraints, and evidence selection are normalized before planning. The generated plan is validated again against the same template before any tool executes. Joint DEM/land-use pixel tools are blocked when explicit `grid_alignment` evidence is not `aligned`; a file overlap report alone is insufficient.

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

Every run response also includes a bounded `result` envelope:

```json
{
  "type": "raster_metadata_result",
  "title": "栅格元数据",
  "summary": "用户可读摘要",
  "data": {"evidence_steps": []},
  "references": [],
  "geometry": {"available": false, "geojson_ref": null, "sources": [], "crs": []}
}
```

`result` is the stable presentation contract. Tool payloads and raw geometries
remain behind bounded references and artifact endpoints.

Run requests may include a bounded `spatial_context` object from the map:

```json
{"admin_name":"洪山区","source":"geojson","crs":"EPSG:4490","geometry_type":"MultiPolygon","geometry_available":true}
```

The runtime uses the named area as structured planning context; it does not
accept arbitrary geometry or execute client-provided code.

`POST /comparisons` accepts the same bounded `spatial_context` object. When it
contains `admin_name`, the server uses that selected map area for every slope
threshold instead of trusting a client-side label or page text:

```json
{
  "admin_name":"洪山区",
  "thresholds":[15,20,25],
  "backend":"local",
  "spatial_context":{"admin_name":"洪山区","source":"map","geometry_available":true}
}
```

## Multi-Turn Clarification

First turn:

~~~powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/runs -ContentType "application/json" -Body '{"request":"查询行政区边界","session_id":"demo"}'
~~~

Follow-up turn using the same session_id:

~~~powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/runs -ContentType "application/json" -Body '{"request":"洪山区","session_id":"demo"}'
~~~

## Conversation History

`GET /sessions` lists named conversations. `POST /sessions` creates the next
conversation name, such as `对话2`. Use
`GET /sessions/{session_id}/runs?limit=20` to restore the recent run summaries
for one conversation, then `GET /runs/{run_id}` for the complete structured
result of the latest run.

`POST /sessions/{session_id}/clear` clears the conversation's persisted run
snapshots and pending clarification while keeping the conversation entry. Use
`DELETE /sessions/{session_id}` to remove the conversation entry and its stored
runs entirely.

`POST /region-comparisons` compares the same slope rule across 2 to 6 named
administrative areas. It returns one bounded row per area and does not accept
client-provided geometry.

Both comparison endpoints return a normalized `scenario` object. The object
contains `operation`, deduplicated `admin_names`, and numeric `thresholds`, so
clients do not need to reconstruct the comparison semantics from page fields:

```json
{
  "scenario": {
    "operation": "buildability_comparison",
    "admin_names": ["洪山区", "江夏区"],
    "thresholds": [20.0]
  }
}
```

`POST /runs/async` returns a `run_id` immediately with status `QUEUED`. Poll
`GET /runs/{run_id}` for `PLANNING`, `EXECUTING`, and terminal statuses. Active
runs can be cooperatively cancelled with `POST /runs/{run_id}/cancel`.

异步提交、运行结果和 `GET /runs/{run_id}` 会附带受限的
`async_observability`。客户端也可以通过以下两个等价入口单独读取该对象：

- `GET /runs/{run_id}/observability`
- `GET /runs/{run_id}/async`

观测对象包含 `status`、`phase`、提交/开始/完成时间、排队耗时、运行耗时、
失败分类、取消请求、重启恢复次数和最后事件；不包含原始请求、任务 payload、
模型响应或凭据。`GET /metrics` 的 `async_jobs` 汇总状态数量、失败分类和耗时
统计，可用于部署监控但不能替代具体运行结果。

`GET /workflows` 返回当前受控工作流模板目录。每个模板包含版本、允许的工具、结果类型、
结构化约束规格、证据选项、最大步骤数和必填约束；客户端不能通过该接口直接执行任意工具，实际计划仍必须经过
TaskPlan schema 和 ToolRegistry。可通过 `POST /workflows/{template_id}/validate` 校验用户编辑的
约束/证据选择和可选计划，通过 `POST /workflows/{template_id}/revise` 合并受控约束修改并重新校验计划。
两个接口只返回归一化契约，不执行空间工具。生产异步 worker 数量可通过
`SPATIAL_AGENT_ASYNC_WORKERS` 配置为 1 到 16，默认值为 4，实际值可从
`metrics.async_jobs.worker_count` 读取。

数据目录可在配置 JSON 中增加相对 `manifest` 路径。健康检查会对 manifest 做不读大文件内容的
路径、大小和 provenance 校验；需要完整 SHA-256 校验时显式执行：

~~~powershell
python scripts\dataset_manifest.py --config config\datasets.wuhan.local.example.json --output outputs\wuhan.manifest.json
python scripts\bind_dataset_manifest.py --config config\datasets.wuhan.local.example.json --manifest outputs\wuhan.manifest.json --output outputs\datasets.wuhan.local.json
python scripts\dataset_manifest.py --config outputs\datasets.wuhan.local.json --verify outputs\wuhan.manifest.json --evidence-output outputs\wuhan.manifest.verification.json
~~~

绑定脚本会生成 `manifest_required=true` 的本地配置；该配置和 manifest 不应提交到仓库。生产 readiness 通过
`SPATIAL_AGENT_REQUIRE_DATASET_MANIFEST=1` 开启必需绑定门控。运行时 readiness 只验证 manifest 文件、相对路径、文件大小和 provenance，
`verification_mode=metadata` 表示没有在请求期间读取大文件；发布前的 `verification_mode=sha256` 且 `hashes_verified=true` 的显式证据文件才表示完整哈希核验通过。

如果源 DEM 与土地利用数据的 CRS、原点或尺寸不一致，可先生成分析就绪派生层：

~~~powershell
python scripts\prepare_analysis_rasters.py --config config\datasets.wuhan.local.example.json --output-dir D:\tmp\wuhan-gis\analysis-ready --config-output D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.json
~~~

脚本按武汉 13 个行政区融合边界生成固定目标网格，分别以双线性和最近邻重投影 DEM/分类栅格，并写出 `analysis-ready-report.json`。只有报告中的 `grid_alignment.status=aligned` 且派生 manifest 完整校验通过时，才应在本地配置中启用联合像元建设筛选。

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
- In production SQLite mode, `GET /runs` and `GET /metrics` read persisted run snapshots, including runs that were not exported as artifacts.
- `GET /runs/{run_id}` returns a persisted run snapshot after a service restart; `POST /runs/{run_id}/retry` can then resume a failed planned run.
- Cancellation is cooperative: the cancel request is persisted, and Runtime stops at the next safe step boundary. It does not forcibly terminate a running third-party GIS or provider call.
- Artifact export writes a compact run summary only, not raw spatial datasets.

## Release Evidence

`GET /release-evidence?max_files=10` runs the explicit publication checks and returns a bounded JSON report with three independent layers:

- `metadata`: runtime data readiness, analysis-ready target grid and lightweight health checks;
- `source_binding`: SHA-256 verification of the source files recorded before derivation;
- `output_manifest`: SHA-256 verification of the current derived DEM/land-use outputs and basename matches.

The endpoint may read large files and is intended for release or data-change validation, not frequent liveness probes. It never returns absolute paths or individual file hashes. A `metadata` readiness result is deliberately not presented as a completed SHA-256 publication check. The same report can be generated offline with:

```powershell
python scripts/release_evidence.py --config <dataset-config.json> --output <release-evidence.json>
```

## Artifact Viewer

Render an exported artifact as a standalone HTML file:

~~~powershell
python view_artifact.py outputs\runs\<run-id>.json
~~~

The viewer shows the request, plan goal, tool status, attempts, latency, safe result summaries, answer, and trace. It does not expose raw tool arguments, geometries, credentials, or provider responses.

`export_geojson=true` produces a small `FeatureCollection` whose features summarize tool steps. The local admin backend can provide bounded real geometry on this explicit export path; memory and raster results use `null` geometry because they expose result references and metrics rather than raw geometries.
