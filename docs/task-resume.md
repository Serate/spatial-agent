# Spatial Agent Task Resume

This document is a handoff note for continuing development of the Spatial Agent project in a fresh conversation or work session.

## Project

- Local path: D:\Project\job\ai-agent
- GitHub: https://github.com/Serate/spatial-agent
- Branch: main
- Git safe-directory form: git -c safe.directory=D:/Project/job/ai-agent ...

## Positioning

Spatial Agent is a job-search portfolio project focused on AI Agent engineering with geospatial data as the domain carrier.

The project should demonstrate:

- Agent Runtime orchestration
- Planner and LLM Planner separation
- Tool schema validation
- Tool Registry dispatch
- SpatialBackend adapter design
- Real local geospatial data integration
- Multi-turn clarification
- User-facing answer composition
- HTTP API boundary
- Readable execution trace
- Artifact export
- Smoke checks and CI

The project should not be framed as a simple GIS script. The core point is a testable, observable, replaceable Agent Runtime.

## Current Status

- Latest completed milestone: Production GIS container and live DeepSeek validation
- Latest pushed commit: 3b07d4c feat: classify planner errors in evaluation reports
- Current milestone: Demo convergence and final regression
- Production container has passed GIS readiness and real DeepSeek zonal smoke tests; local provider files remain ignored.

## Completed Milestones

### M0: Design Baseline

- Project design documents
- Tool schema
- Evaluation cases

### M1: Minimal Agent Runtime

- AgentRuntime
- ToolRegistry
- RuleBasedPlanner
- In-memory spatial adapter
- Basic runtime tests

### M2: LLM Planner Seam

- LLMPlanner
- OpenAIPlannerClient
- TaskPlan JSON schema
- Fake LLM client tests

The fake LLM client is used only for deterministic tests. It returns fixed structured JSON so parser behavior, schema validation, tool-name validation, clarification flow, and rejection flow can be tested without network access, API keys, or token cost.

### M3: Spatial Backend Interface

- SpatialBackend protocol
- InMemorySpatialBackend
- SpatialToolAdapter

### M4: Evaluation And Trace Metrics

- Evaluation runner
- StepRun timing fields
- JSON evaluation reports

### M5: Dataset Probe

- GeoPandas/Rasterio metadata probe
- environment.yml
- Local dataset inspection scripts

### M6: Real Admin GeoJSON Backend

- GeoJSONAdminBackend
- HybridSpatialBackend
- run_demo.py --backend local

### M7: Natural-Language Admin Queries

- RuleBasedPlanner supports requests such as: 查询洪山区行政区边界
- Planner generates admin_areas schema and range query steps.

### M8: Answer Composition

- AnswerComposer converts tool traces into user-facing natural-language answers.

### M9: Multi-Turn Clarification

- Runtime stores pending clarification by session_id.
- Example flow: 查询行政区边界 -> missing admin area name -> 洪山区 -> completed query.

### M10: HTTP API

- AgentService
- serve_api.py
- GET /health
- POST /runs

### M11: Smoke Check And CI

- scripts/smoke_check.py
- GitHub Actions workflow
- Smoke check runs unit tests and service-level checks

### M12: API Contract

- docs/api.md
- API request/response examples
- Error response examples
- HTTP boundary tests

### M13: Trace Formatter

- agent/trace_formatter.py
- trace_summary added to AgentService responses
- Trace covers completed, clarification, rejected, and failed states

### M14: Artifact Export

- agent/artifact_store.py
- export_artifact=true
- artifact_ref returned from AgentService and HTTP API
- outputs/ ignored by Git

### M15: Real Raster / Land-Use Metadata Query

- agent/raster_backend.py
- get_raster_metadata tool
- DEM and land-use raster metadata inspection
- RuleBasedPlanner handles DEM and land-use metadata requests
- local backend reads real Rasterio metadata; memory backend returns deterministic placeholders
- README and docs/data-adapter-plan.md updated
- Pushed commit: 0ae304a feat: add raster metadata backend

### M16: Real LLM API Demo Path In Progress

Implemented locally but not yet committed at the time of this handoff:

- agent/openai_config.py loads OpenAI planner settings from config/openai.local.json or environment variables.
- config/openai.example.json provides a safe committed template.
- .gitignore ignores .env and config/*.local.json.
- OpenAIPlannerClient supports OPENAI_BASE_URL, OPENAI_MODEL, and OPENAI_REASONING_EFFORT.
- OpenAIPlannerClient supports Responses and Chat Completions wire APIs through wire_api/OPENAI_WIRE_API.
- DeepSeek Chat Completions has been validated with deepseek-v4-flash and https://api.deepseek.com.
- OpenAIPlannerClient now also supports exact OPENAI_API_URL plus query-string auth via OPENAI_AUTH_LOCATION=query and OPENAI_API_KEY_QUERY_PARAM.
- Default model is gpt-5.6-luna and default reasoning effort is medium.
- tests/test_m16_openai_config.py covers local config loading, env overrides, URL normalization, and skipped live smoke behavior.
- README.md and docs/api.md document the OpenAI planner setup.

Local private config:

- config/openai.local.json was written with the provided provider URL, key, model, and reasoning effort.
- The file is ignored by Git and must not be committed.

Validation so far:

- Target offline tests passed:
  - python -m unittest tests.test_m16_openai_config tests.test_m2_llm_planner -v
- git diff --check passed, with only Windows LF/CRLF warnings.
- Live OpenAI planner smoke reached the provider only after running with escalated network permission.

Known M16 issues observed:

- Without network permission, live OpenAI calls fail with WinError 10013 socket access denied.
- With network permission, the configured provider returned HTTP 403 Forbidden for the live Responses API smoke.
- HTTP 403 means the network path and code path reached the provider; next checks are provider authorization, API key validity, model access, account balance, or whether the provider supports /v1/responses for this model.
- Do not run live API tests in CI. Keep SPATIAL_AGENT_LIVE_OPENAI unset unless doing manual provider validation.
- Codex config was inspected and shows model_provider custom, wire_api responses, requires_openai_auth true, base_url https://crs.ruinique.com. This implies header auth and Responses protocol, not key-in-query auth.
- config/openai.local.json was changed back to base_url https://crs.ruinique.com and auth_location header. Query auth remains available in code only as an optional provider compatibility mode.
- Root cause found for provider HTTP 403 / error code 1010: crs.ruinique.com rejects Python urllib's default User-Agent. Adding a normal User-Agent plus Accept: application/json returns HTTP 200 for both /responses and /v1/responses probes.
- The configured crs.ruinique.com provider still times out on model POST requests from this client, while DeepSeek Chat Completions succeeds.

## Model API Position

The project may connect to a real LLM API.

Current design:

- Default path uses RuleBasedPlanner for deterministic tests, CI, and reliable local demos.
- Optional path uses LLMPlanner with OpenAIPlannerClient.
- Tests use a fake LLM client to avoid network dependency and token usage.

Recommended position:

- Do not make CI depend on a real model API.
- Keep RuleBasedPlanner as the default for deterministic behavior.
- Keep real LLM API integration available through --planner openai or API payload field planner=openai.
- Add documentation and smoke demos for real model integration when an API key is available.

This is not avoiding real model integration. It is separating deterministic engineering tests from live model behavior.

## Local Data

- Dataset root: D:\dataset\agent
- Admin GeoJSON: D:\dataset\agent\湖北省_县.geojson
- Admin GeoJSON details: 103 county-level features, EPSG:4490, fields name and gb, MultiPolygon geometry
- DEM: 9 ASTER .img tiles, EPSG:32649, 30m
- Land use: 4 .tif files, EPSG:32649, 30m
- Land-use sidecar SHP: 4 .shp files, EPSG:4326

Do not commit raw datasets from D:\dataset\agent.

## Python Environments

- Default Python: C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe
- Conda executable: D:\code\conda\Scripts\conda.exe
- GIS conda env: spatial-agent-gis
- GIS Python: C:\Users\torch\.conda\envs\spatial-agent-gis\python.exe

## Standard Validation

Run smoke check:

~~~powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\smoke_check.py
~~~

Run all non-GIS tests:

~~~powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m unittest discover -s tests -v
~~~

Run GIS-focused tests:

~~~powershell
& 'D:\code\conda\Scripts\conda.exe' run -n spatial-agent-gis python -m unittest tests.test_m6_geojson_admin_backend tests.test_m7_admin_planner tests.test_m8_answer_composer tests.test_m9_clarification_loop -v
~~~

Check Git state:

~~~powershell
git -c safe.directory=D:/Project/job/ai-agent status --short --branch
git -c safe.directory=D:/Project/job/ai-agent diff --check
~~~

## Next Recommended Milestone

### Finish M16: Commit And Hand Off Real LLM API Demo Path

Goal: finish and commit the optional real-model demo path without making CI depend on a live model API.

Suggested next steps:

- Rotate any key exposed in chat and update only the ignored local config.
- Keep config/openai.local.json untracked and verify it with git check-ignore.
- Do not make CI depend on either live provider.
- Run full offline tests and smoke check.
- Commit with a clear message such as feat: document openai planner config.

## Current Production Validation

- Docker Desktop Linux engine runs through WSL2 with domestic image mirrors.
- The production Dockerfile installs GIS dependencies in cacheable Conda layers and uses Tsinghua Conda/PyPI mirrors.
- Production Compose requires `docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d` so the host data path participates in volume interpolation.
- The production image uses Linux `share/gdal` and `share/proj` runtime data paths and readiness checks both marker files.
- Real DeepSeek smoke tests for DEM metadata and 洪山区 zonal DEM analysis pass inside the container.
- `.env.production`, `config/openai.local.json`, raw GIS data, and API keys remain local-only.

## Later Milestones

### M26: Console Raster Statistics Overview

- 完成区域/栅格统计结果的中文可视化概览。
- 前端展示最小值、最大值、均值、标准差、有效像元和 NoData 比例。
- 使用原生 HTML/CSS/JavaScript，不增加构建依赖；保留无结果和业务错误空态。

### M27: Raster Value Distribution Summary

- 后端在分块统计过程中保留受限样本，生成 10 桶值分布摘要。
- Console 用原生 CSS 条形图展示分布，并明确样本统计口径。

### M28: Console Conversation Controls

- 增加新建会话和清空对话操作。
- 新会话使用新的 session_id，保持服务端澄清状态隔离。

### M29: Live Zonal Analysis Smoke

- 增加真实模型“分析洪山区 DEM 高程概况”的可选端到端测试。
- 验证模型工具选择、GIS 后端执行、真实统计结果和中文答案。
- 默认跳过，只有显式设置 `SPATIAL_AGENT_LIVE_OPENAI=1` 才访问 provider。

### M30: Per-step Result Summary

- 在 Console 任务步骤中展示每个工具的关键结构化结果。
- 失败步骤显示业务错误，避免执行轨迹只有生命周期状态而缺少实际结果。

### M31: Raster Footprint Preview

- 栅格统计结果携带合并 bounds/CRS。
- Console 在无矢量几何时显示栅格覆盖范围矩形。

### M32: Multi-step Result References

- 统一结果引用格式为 `{"$from":"步骤ID","path":"结果字段"}`。
- 计划解析阶段校验引用来源、依赖声明和执行顺序。
- 已有行政区 schema → 过滤 → 区域 DEM 统计的真实 GIS 示例链路。
- Console 展示步骤依赖、执行状态和解析后的结果摘要。

### M33: Failure-aware Multi-step Execution

- 多步骤工具失败后 fail-fast。
- 保留已完成结果，并将未执行步骤标记为 BLOCKED。

### M34: Retry Failed Run

- Runtime 支持从第一个失败步骤恢复。
- API 和 Console 提供失败运行重试入口。

### M35: Run Provenance

- API/artifact 记录安全的步骤血缘摘要。
- Console 展示依赖、输入绑定、执行策略和结果引用。

### M36: Planner Evaluation Metrics

- 评测报告统计状态/工具匹配、步骤耗时、Planner 延迟、Token 总量和依赖链有效率。

### M38: Real Land-use Zonal Analysis

- 增加真实土地利用栅格行政区分析示例。
- 不伪造当前尚未接入的真实坡度栅格能力。

### M37: Cooperative Runtime Control

- Runtime 支持线程安全的协作式取消和步骤边界超时。
- API 提供 cancel 入口；状态包括 `CANCELLED` 和 `TIMED_OUT`。

### M39: Showcase Convergence

- 新增中文演示验收清单，覆盖离线、GIS、真实模型、失败恢复和回归命令。

### M40.1: Real Terrain And Land-use Analysis

- `get_zonal_slope_statistics` 从真实 DEM 像元动态计算坡度统计，不伪造坡度数据。
- `get_zonal_land_use_distribution` 返回行政区内土地利用栅格类别编码、像元数和占比。
- 规则规划器支持高程、坡度和土地利用联合请求，生成多工具、有依赖的执行计划。
- Console 增加综合分析卡片和土地利用类别占比图，并明确类别编码未做语义映射。
- GIS 验收：洪山区真实 DEM 坡度和土地利用类别统计通过。

### M16: Real LLM API Demo Path

- Add .env.example
- Document OPENAI_API_KEY
- Add --planner openai demo instructions
- Add tests that skip when no API key is available
- Keep CI deterministic and offline

### M17: Trace Or Artifact Viewer

- Add a simple CLI or static HTML viewer for run artifacts
- Focus on interview demo readability

### M18: Lightweight Map Or Export Enhancement

- Export small GeoJSON summaries or map-ready artifacts
- Keep raw datasets out of Git

## Development Rule Of Thumb

For each milestone:

1. Implement the smallest useful slice.
2. Add tests.
3. Run targeted tests.
4. Run smoke check.
5. Run git diff --check.
6. Commit with a clear message.
7. Push to origin/main.

Prefer small, explainable increments over large rewrites.

## Current Extended Demo Capabilities

- 同一 session_id 支持基于上一轮请求的受控追问，例如“继续分析这个结果”。
- `POST /comparisons` 支持同一行政区的多个坡度阈值建设适宜性对比。
- Console 支持阈值对比表、历史任务列表和运行指标摘要。
- Leaflet 支持纯矢量模式与可选 OpenStreetMap 底图，外部网络不可用时不影响矢量结果。
- `GET /runs` 和 `GET /metrics` 在生产 SQLite 模式下直接读取持久化运行快照，不要求每次运行导出 artifact；内存模式仍使用 artifact store。
- 生产接口已验证洪山区三个坡度阈值均可完成真实 GIS 分析。
- Planner 支持结构化 `direct_answer` 决策；通用问题不强行调用 GIS 工具，空间问题仍必须通过 TaskPlan 和 ToolRegistry。
- Console 在运行结果顶部显示决策模式：通用回答不会调用空间工具，澄清/拒绝不会执行工具，空间计划显示实际工具步骤数量。
- 未知或暂不支持的空间问题保持 `NEEDS_CLARIFICATION`，不能由通用回答替代空间结果，也不能绕过 ToolRegistry。
- M42 新增 SQLite 状态存储，Service/Runtime 重建后仍可恢复澄清上下文和运行快照。
- M43 将取消标记、运行索引和指标也持久化到 SQLite，支持跨 worker 的取消检查和失败运行查询。
- M43 提供 `GET /runs/{run_id}`，支持服务重启后读取完整运行快照。

## Development Issues Log

- 新对话恢复优先阅读 docs/agent-context-resume.md。
- Maintain docs/agent-development-issues.md as the project-level log of practical AI Agent engineering issues.
- This log is not milestone-specific. It covers planner behavior, tool schemas, runtime validation, real model APIs, local data, answer composition, trace/artifact safety, and documentation drift.
- When a new development issue appears, update docs/agent-development-issues.md with symptom, root cause, diagnosis, fix, and prevention before relying on chat history.
