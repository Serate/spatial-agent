# Spatial Agent Task Resume

This document is a handoff note for continuing development of the Spatial Agent project in a fresh conversation or work session.

## 当前全局执行规则

- 当前 goal 的最大并发度为 3。
- 任一阶段最多启动 3 个并行子任务；公共契约由主线统一集成。

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

- Latest completed milestone: M61 data health, async reliability, and model observability baseline
- Latest pushed commits: `ac38f3a` async reliability, `85b1ce4` data health and model reliability
- Current milestone: M61 deployment revalidation and next global planning
- Production container has passed GIS readiness and real DeepSeek zonal smoke tests; local provider files remain ignored.

## Development Loop

- Overall loop: global planning -> parallelizable implementation -> integrated testing -> global replanning.
- A large milestone may be split into independent sub-tasks, with a maximum concurrency of three.
- Each completed milestone must update `docs/milestones.md`, refresh this handoff document, and create one GitHub commit/version.
- Parallel work must converge through the shared tool schema, runtime contract, focused tests, full regression, and GIS/browser verification.

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
- M44 建立整体产品验收基线，集中覆盖 DEM 元数据、行政区区域分析、建设适宜性、澄清追问和不支持空间领域。
- M44 扩展自然语言变体识别，并统一真实模型对土地利用、坡度和建设候选结果的中文摘要。
- M45 增加 Chrome CDP 浏览器烟测，覆盖会话恢复、结果隔离和真实 GIS 地图矢量渲染。
- M46 建立统一 `result` envelope，包含结果类型、标题、摘要、证据步骤、引用和空间几何可用性；核心评测新增结果类型与协议完整性断言。
- M47 增加受控 `spatial_context`，地图要素点击后可作为下一次 Planner 请求的结构化区域上下文；浏览器烟测验证洪山区选区和后续分析入口。
- M48 明确会话生命周期：清空会话删除持久化运行快照但保留会话编号，删除会话移除会话及其历史；前端同步清理工作区，并通过浏览器烟测等待异步清空完成。
- M49 增加异步运行入口：`POST /runs/async` 先返回 `run_id`，Console 轮询最终结果并支持真正的协作式取消；同步 `POST /runs` 保持兼容。
- M50 接入武汉 OSM 道路/水体 GeoPackage，并完成真实 DEM、土地利用候选与道路/水体约束的联合演示筛选；修复 Rasterio window native 崩溃和全量矢量 union 内存暴涨。
- M51 增加 `get_dataset_health_report`，对武汉行政区、DEM、土地利用、道路和水体执行有界的可读性、CRS、覆盖范围和基础几何质量检查，并接入规则 Planner、LLM guidance 与中文答案。
- M52 健康报告增加 DEM 与土地利用的跨栅格覆盖关系，显示可重叠文件对数量和 CRS 组合；检查只读取元数据，不加载完整像元。
- M53 为联合建设筛选增加显式数据健康 preflight，并在工具依赖和答案中保留预检证据。
- M54 将健康 preflight 接入综合高程、坡度、土地利用和建设候选分析。
- M55 将健康 preflight 扩展到单独区域栅格统计和复合行政区栅格流程；189 个离线测试、36 个 GIS 测试、smoke 与浏览器健康烟测通过。
- M56 为健康报告增加 `usable_for`/`capabilities`，Runtime 在下游 dispatch 前阻止明确不可用的数据，并完成 README 与阶段记录分离；191 个离线测试、38 个 GIS 测试、smoke 与浏览器健康烟测通过。
- M57.1 抽取 `BuildabilityComparisonScenario`，统一阈值对比和多区域对比的输入验证与 `scenario` 输出；194 个离线测试、19 个 GIS/真实数据重点测试通过。
- M57.2 新增 `evaluation/cases/global-acceptance.json` 和矩阵契约测试，覆盖通用问答、单区域、多数据集、阈值对比、多区域、不可用数据、真实 GIS 和真实模型；197 个离线测试、36 个 GIS 测试、smoke 与浏览器健康烟测通过。
- M58.1 将 environment、execution_mode、planner 写入评测报告，并新增 `scripts/evaluate_global.py`；全局矩阵离线执行 7/7 通过、3 个可选环境跳过。
- M58.2 新增 `scripts/production_acceptance.ps1` 和 SQLite 异步快照重建测试。
- M58.3 完成 Docker/Compose 配置、healthy/readiness、异步业务验收和容器重启后的 SQLite 快照验证；生产验收脚本修复了 session 隔离和 PowerShell UTF-8 编码问题。离线 200 个测试、GIS 190 个测试、smoke 和浏览器健康烟测通过。
- M59.1 新增统一能力目录、跨入口 `/capabilities` 契约、能力驱动的全局评测字段和 Console 摘要；生产容器重建后返回 8 项能力。离线 206 个测试、GIS 196 个测试、production acceptance 和浏览器健康烟测通过。

### M59.2：跨进程运行与结果证据验收

- 将能力目录中的环境要求接入评测 optional gating，区分 planner/tool 成功和真实 GIS 能力完成。
- 增加生产 SQLite 会话、运行、重试、取消和结果引用的跨进程契约矩阵。
- 细化真实 artifact 几何、边界几何、无几何演示和截断不可绘制等证据状态，并接入 Console 与全局报告。
- 大阶段按依赖拆分后最多并行 3 路，集成后运行全量、GIS、浏览器和部署验收，再基于全局结果规划下一阶段。

- M59.2 验证：内存导出为 `no_geometry`，真实 GIS 建设筛选为 `real_geometry`、101 个要素；离线 207 个测试、GIS 197 个测试、smoke、全局评测、生产 acceptance 和浏览器烟测通过。

### M60：真实数据能力与异步可靠性深化（已完成）

- 将能力目录扩展为带数据覆盖、CRS、质量等级和更新时间的运行时能力快照。
- 完成生产 SQLite 的重试、取消、会话清空和结果引用跨进程矩阵，覆盖异常重启和重复请求。
- 将真实几何证据状态接入评测报告、答案组合和地图渲染，明确截断与不可绘制原因。
- 按依赖最多拆分 3 路并行任务，集成后重新验收真实模型、GIS 数据和部署链路。

### M60 当前进展与验证边界

- 已新增运行时能力快照模块，包含数据质量、覆盖范围、CRS、文件数、检查文件数和更新时间。
- 已接入 `runtime_capability_catalog()`、数据健康报告 `updated_at`、`GET /capabilities/runtime` 和生产验收脚本的 `runtime_health` 输出。
- 运行时能力和入口契约测试通过；默认环境缺少 FastAPI 的测试按环境条件跳过。
- 生产容器已重建并通过快照、健康和异步业务验收；容器完整健康状态为 `unavailable`，仅因示例数据卷未提供道路/水体，核心栅格与行政区逐项证据为 `ready`。
- SQLite 跨进程结果引用、会话清空、取消和失败重试测试 4/4 通过；离线 208 项、GIS 205 项、smoke、全局评测和浏览器烟测通过。

### M60 并行执行规则（历史）

- M60 当时最大并行度为 5；当前全局规则已调整为最大并发度 3。只有依赖独立、修改边界清晰且可单独验收的子任务才并行。
- 推荐五路：运行时能力快照、SQLite 异步可靠性、几何证据、评测/答案契约、部署与 Console 验收。
- 所有并行任务必须遵守统一工具 schema、runtime 状态、result envelope、能力目录和测试夹具；公共契约变更由集成阶段统一合并。
- 每路先做聚焦测试，集成后统一执行离线、GIS、HTTP/浏览器、Docker 和可选真实模型验证；阶段版本只在联合验收通过后创建。

### M61 后续全局规划

1. 从产品能力、数据质量、真实模型、部署可靠性和用户体验五个维度整体推进 M61。
2. 将武汉道路/水体数据卷和可选数据健康分层纳入生产部署，避免缺失可选数据掩盖核心能力。
3. 深化异步幂等、重启恢复、真实模型超时重试和 Console 动态结果展示。

### M61 当前实现

- 数据健康分为核心层与可选层，能力目录新增 `data_layer`、`capability_status`、`available`，逐能力门控道路/水体约束分析。
- SQLite 异步入口支持默认请求指纹和显式 `idempotency_key`，并发重复提交、显式运行 ID 重放、清空去重键和重启接管均有契约测试。
- 真实模型客户端支持超时、暂态重试、指数退避和安全请求指标；默认 CI 仍不访问网络。
- M61 专项测试已通过 20 项；全量回归与生产验收待集成后执行。

### M62 当前实现

- 新增轻量空间意图分类器，识别空间请求和候选能力，但不把意图识别当作工具成功或真实几何证据。
- 未命中固定规则的空间问题现在返回可操作澄清；已支持的道路/坡度、多轮澄清和 ToolRegistry 契约保持不变。
- 下一步扩展能力目录与澄清动作的结构化 API/Console 展示，并补全 Docker 新镜像验收。

M62.1 已完成结构化澄清第一阶段：`ClarificationNeeded`、运行快照、SQLite、结果 envelope 和 Console 均支持 `clarification`；下一步做 HTTP/评测契约和能力目录驱动的前端动作。阶段验收仍需全量离线、HTTP/浏览器、GIS 以及 Docker（环境恢复后）验证。

M62.2 已完成能力目录和 HTTP 集成：澄清详情带能力中文标签，标准 HTTP 返回和全量离线测试已验证。下一步从全局推进多工具开放式编排、真实 GIS/模型证据矩阵和生产 Docker 复验。

## M63 当前实现：受控空间总览编排

- 新增 `spatial_overview` 能力；规则 Planner 支持“分析洪山区空间概况”等请求。
- 计划固定为健康检查、行政区解析、高程、坡度、土地利用、道路和水体摘要 8 步，所有工具仍经过 Registry 和数据门控。
- 专用结果类型和中文答案已接入；下一步补全局评测、HTTP/Console 结果类型验证，并在 GIS 数据环境执行真实证据验收。
- M63 集成验收已完成：全局评测 8/8 离线场景通过，GIS 回归 41 项通过，Docker 生产验收和容器空间总览请求通过。同步生产路由的异步参数回归已修复并增加契约测试。

下一阶段从全局推进：真实 GIS 空间总览的几何证据、真实模型对总览计划的结构化一致性、Console 按 `spatial_overview_result` 动态展示，以及生产数据卷/多进程观测矩阵。

## M64 当前进展

- 真实武汉配置下总览返回 `real_geometry`，GeoJSON 达到大小上限时返回 `truncated_geometry`，并包含最终 feature_count 与来源。
- 道路/水体导出 feature 保留 dataset 标签；Console 已增加 `spatial_overview_result` 结果注册和总览地图渲染入口。
- 下一步执行浏览器烟测、真实模型结构化总览测试、Docker 多进程矩阵，并完成阶段联合验收。
- DeepSeek live 总览规划已通过，返回完整 8 步注册工具计划；浏览器和重建后容器验收仍待完成。

## Development Issues Log

- 新对话恢复优先阅读 docs/agent-context-resume.md。
- Maintain docs/agent-development-issues.md as the project-level log of practical AI Agent engineering issues.
- This log is not milestone-specific. It covers planner behavior, tool schemas, runtime validation, real model APIs, local data, answer composition, trace/artifact safety, and documentation drift.
- When a new development issue appears, update docs/agent-development-issues.md with symptom, root cause, diagnosis, fix, and prevention before relying on chat history.

## M65 当前进展

- 生产异步链路已增加多 worker 并发提交、独立轮询和 claim 后崩溃恢复测试；修复首次提交幂等标记和 Windows 进程存活探测。
- 真实模型链路已用脱敏录制响应验证空间总览 8 步计划、依赖和 ToolRegistry 执行，测试不访问网络。
- Console 已增加 `spatial_overview_result` 紧凑摘要面板；跨区域对比沿用现有服务/HTTP/前端能力。
- 阶段验收尚未完成，下一步运行全量离线、GIS、HTTP/浏览器和 Docker 验收，之后提交并推送一个 M65 版本。

## M66 已完成

- 真实模型区域分析已确认必须在 `spatial-agent-gis` conda 环境运行；元数据、区域 DEM、复合区域分析和空间总览均有 live 端到端验证入口。
- 异步结果快照新增内部 `geometry_evidence`，同步、异步轮询和服务重启后的 GeoJSON 引用与几何状态由证据矩阵验证。
- Console 浏览器验收增加隔离 CDP 启动脚本、可配置 `CDP_URL`/`CONSOLE_URL` 和空间总览面板/行政区-道路-水体颜色分层 smoke。
- 开放式空间澄清和多区域对比已加入 M66 全局评测契约。
- 离线全量 271 项通过，GIS 全量 271 项通过；Docker production acceptance 确认核心数据 ready、可选 roads/water 缺口可见，异步完成与重复提交幂等通过。
- Chrome CDP 总览面板、行政区/道路/水体颜色分层、真实 GIS 建设适宜性地图（59 条路径、洪山区选区）、会话恢复和清空工作区 smoke 均通过。
- M66 已具备阶段版本收口证据；后续进入 M67 全局规划。

## M67 当前实现与验证

- 数据目录和 runtime 能力快照已暴露受控 provenance；旧数据配置和无 provenance 配置保持兼容。
- 脱敏模型回放评测已接入全局评测，覆盖 8 步空间总览工具覆盖、依赖 DAG、结果类型、中文答案、token/延迟和 provider 错误分类。
- 异步作业观测已接入服务与 SQLite，包括生命周期、队列/执行耗时、失败分类、取消和重启接管；新增两个单独观测入口。
- Console 结果证据面板按响应动态显示几何、运行时数据、provenance 和降级状态；总览地图支持行政区、道路和水体三色分层。
- M67 专项 22 项、离线全量 293 项（35 项跳过）、GIS 全量 293 项（9 项跳过）、smoke、全局评测、Docker 和串行 Chrome CDP 验收通过。

## M68 全局规划

1. 产品能力：配置化空间工作流、结构化约束和证据选择。
2. 数据质量：可复现道路/水体数据卷、provenance 校验和跨栅格覆盖/对齐报告。
3. 真实模型：开放式空间问答、澄清、失败修复的脱敏回放与可选 live 基线。
4. 部署可靠性：SQLite 升级、多 worker 观测一致性、取消/超时边界和滚动重启恢复。
5. 用户体验：统一动态答案、轨迹、证据和地图工作区，减少空面板并解释降级状态。

## 持续目标扩展

每个大阶段必须从产品能力、数据质量、真实模型、部署可靠性和用户体验五个维度做全局规划；可独立的工作拆成最多 3 路并行，公共 schema、runtime、result envelope 和能力目录由主线统一集成。阶段完成后必须有专项测试、全量回归、真实 GIS/浏览器/部署证据、中文问题记录、里程碑更新和 GitHub 版本，再依据全局结果规划下一阶段。

## M68 已完成

- 受控工作流模板目录位于 `agent/workflow_templates.py`，提供模板目录、模板校验、计划校验和依赖 DAG 校验；能力目录与 `GET /workflows` 已接入。
- `agent/raster_alignment.py` 提供 metadata-only DEM/土地利用对齐报告；健康报告和 runtime 快照保留 `relationships.dem_land_use.grid_alignment`，明确不读取像元。
- SQLite 旧 schema 生命周期字段迁移、异步 worker 配置（`SPATIAL_AGENT_ASYNC_WORKERS`，1-16，默认 4）和内存会话 CRUD/历史恢复已完成。
- M68 专项 47 项，另加 smoke 回归 1 项；离线全量 340 项（35 项跳过）、GIS 全量 340 项（9 项跳过）、`scripts/smoke_check.py` 和 `scripts/evaluate_global.py --strict` 均通过；全局评测 8/8 执行场景通过、3 个可选场景跳过。
- Docker Desktop 仍不可用：`dockerDesktopLinuxEngine` named pipe 不存在，`docker info` 无法连接；新镜像、容器 readiness 和 production acceptance 保留为外部环境待办，不能引用旧容器作为 M68 证据。

## M69 下一步

从项目整体推进三个可并行方向，最多并发 3：

1. 工作流编辑与计划契约：把模板校验扩展为版本化约束编辑、计划修订和 Console 交互，保持 Planner/Runtime/ToolRegistry 的统一边界。
2. 数据 manifest 与对齐门控：为武汉道路、水体、DEM、土地利用和行政区建立可复现 manifest、校验命令、版本/provenance 检查及像元级对齐前置诊断。
3. 模型回放与可靠性矩阵：覆盖开放式澄清补全、非法计划修复、失败重试、多 worker 取消/超时/滚动重启，并保留可选 live provider 基线。

主线集成后再做动态 Console 结果工作区统一、全量离线/GIS/HTTP/串行浏览器验收；Docker Desktop 恢复后补新镜像和 production acceptance，阶段通过后提交并推送一个版本。

## M69 当前实现进展

- 工作流模板已增加语义版本、约束规格、证据选项和默认选择；`validate_workflow_plan` 输出 `template_version`、归一化 `constraints` 与 `evidence`，`revise_workflow_plan` 提供受控修订。
- 开发服务和生产 FastAPI 已提供 `/workflows/{template_id}/validate`、`/workflows/{template_id}/revise`；接口只校验契约，不直接执行工具。
- 新增 `agent/dataset_manifest.py`、`scripts/dataset_manifest.py` 和 M69 manifest 测试；完整哈希校验是显式动作，健康报告只做轻量检查。
- 新增脱敏模型回放套件并接入全局评测：澄清补全、非法计划修复各 1 条，均通过；当前尚未完成 Console 编辑器、武汉 manifest 实际绑定、多 worker 组合矩阵、Docker 和 live provider 验收。

### M69 工作流与对齐子阶段已完成

- Console 从 `GET /workflows` 动态加载模板，折叠式设置区渲染结构化约束和证据选项；发送前调用 `/validate`，归一化 `workflow` 随同步/异步 `/runs` 提交。
- `AgentService`、Planner、Runtime、内存状态和 SQLite 快照统一传播模板版本、约束和证据；生成计划在 ToolRegistry 执行前再次经过模板 allowlist、结果类型和 DAG 校验。
- 像元联合工具 `get_zonal_buildability_analysis` 与 `get_zonal_constrained_buildability_analysis` 增加显式 `grid_alignment=aligned` 前置门控；只存在文件覆盖关系或网格不一致时不会 dispatch 真实联合像元工具。
- 修复新增 `workflow=None` 关键字破坏旧 Runtime 替身导致异步几何证据失败的问题；无工作流请求保持旧方法调用兼容。
- 子阶段验证：工作流/对齐专项 22 项通过，浏览器工作流交互通过，`scripts/smoke_check.py` 通过并包含离线全量 355 项（35 项跳过）。

### M69 尚未完成与下一步

1. 将武汉道路、水体、DEM、土地利用和行政区 manifest 绑定到正式本地配置并执行完整哈希核验。（代码入口、本机绑定配置和完整证据已完成。）
2. 补齐 SQLite 多 worker 的超时、取消、幂等和滚动重启组合矩阵，并保留不同状态后端的一致结果契约。（M69.2 专项已完成。）
3. Docker Desktop 恢复后构建新镜像、执行 readiness/production acceptance/容器重启恢复；再做可选 live provider 验收。

### M69.2 当前进展

- `DatasetCatalog` 已支持必需 manifest 的结构化配置；`scripts/bind_dataset_manifest.py` 可从已提交模板生成被忽略的本地绑定配置。
- `scripts/dataset_manifest.py --verify ... --evidence-output ...` 执行完整 SHA-256 校验并生成不含机器绝对路径的安全证据摘要；健康检查保持 metadata-only。
- runtime capability snapshot 增加 `manifest` 和 `data_readiness` 证据；生产 `/health/ready` 可通过 `SPATIAL_AGENT_REQUIRE_DATASET_MANIFEST=1` 启用门控。
- 本机真实武汉配置在 `D:\tmp\wuhan-gis\datasets.wuhan.local.json`，manifest 16 个文件，SHA-256 核验通过；这些文件均不在仓库中。
- M69.2 下一步先完成 SQLite 多 worker 可靠性组合测试，再串行执行全量离线/GIS/HTTP/部署验收。

### M69.2 验收结果

- manifest 专项 6 项通过；SQLite 多 worker 矩阵 5 项通过；既有取消、幂等、崩溃接管和观测回归 14 项通过（1 项生产 FastAPI 依赖缺失跳过）。
- 全量离线 363 项通过、35 项跳过；GIS 全量 363 项通过、9 项跳过；`scripts/smoke_check.py` 和 `scripts/evaluate_global.py --strict` 通过，执行场景 8/8、脱敏模型回放 2/2。
- 真实武汉配置下行政区/道路/水体可读且几何有效；DEM 与土地利用均完整读取但 CRS 混合，像元对齐状态为 `grid_mismatch`，联合像元工具继续在 dispatch 前阻止。
- Docker 新镜像、readiness、production acceptance 和容器重启恢复仍待宿主机 Docker Linux engine 恢复；当前 `docker info` 报 `dockerDesktopLinuxEngine` named pipe 不存在。
- M69.2 代码尚未提交推送；下一步是审查 diff、收口中文文档并创建阶段提交/版本。

### M70 当前任务

- 新增 `scripts/prepare_analysis_rasters.py`：保持原始栅格只读，按武汉 13 区融合边界生成固定 `EPSG:32649`/30 米目标网格，并输出 DEM、土地利用和 metadata-only 对齐报告。
- 本机真实派生层位于 `D:\tmp\wuhan-gis\analysis-ready`，派生配置为 `D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.bound.json`；这些文件不提交。
- 派生层 manifest 已完成 5 个数据项的完整 SHA-256 校验；真实建设候选请求已返回 576,040 个有效像元、23,172 个候选像元和可导出真实几何。
- M70 已完成：分析就绪流水线、目标网格/派生版本证据、runtime/Console/中文答案和失败路径均已接入；M70 专项 19 项、离线全量 369 项、GIS 全量 369 项、Smoke 和严格全局评测均通过。
- M70 真实验收：绑定配置下 `analysis_ready=ready`、`data_readiness=ready`、目标网格 `EPSG:32649`/30 米/4562×5277、对齐 `aligned`；洪山区建设候选执行得到 576,040 个有效像元和 23,172 个候选像元。
- M70 还保留外部边界：Docker Linux engine 未恢复，生产容器新镜像和 FastAPI 生产入口验收不能宣称通过；真实派生文件、配置、manifest 和 evidence 均位于 `D:\tmp\wuhan-gis`，不提交。

### M71 全局下一步

- 将分析就绪版本证据贯通空间总览、道路/水体约束筛选和多区域比较，确保多工作流的答案、轨迹、GeoJSON 和地图引用一致。
- 增加派生报告/manifest 变更检测、nodata 与重采样证据，以及真实能力快照驱动的开放式问题脱敏回放。
- Docker Linux engine 恢复后进行新镜像、readiness、重启恢复和生产 FastAPI 矩阵；Console 补绑定真实配置的浏览器 smoke。

### M71 验收结果

- `/comparisons` 和 `/region-comparisons` 的总体响应与每个结果行均保留 `analysis_ready`：派生版本 `analysis-ready-v1`、目标 CRS `EPSG:32649`、30 米分辨率和 `aligned` 状态。
- 道路/水体约束建设筛选真实 GIS 调用完成，答案显示 500 米道路阈值、161 个满足道路约束样本和 14 个水体排除样本，并引用同一分析就绪证据。
- M71 专项 3 项通过；离线全量 373 项通过、42 项跳过；GIS 全量 373 项通过、9 项跳过；Smoke、严格全局评测 8/8 和脱敏模型回放 2/2 通过。
- 真实绑定配置下阈值比较返回洪山区 15°/20° 候选 22,800/23,172 个；多区域 20° 比较返回洪山区 23,172 个、江夏区 59,045 个候选像元。
- GIS 首次全量运行的嵌套 smoke 曾出现一次 artifact 引用缺失，但目标测试 5/5、独立 smoke 和完整 GIS 复跑通过；详见中文开发问题日志。
- Docker Linux engine、生产镜像/readiness、FastAPI acceptance、浏览器真实配置 smoke 和 live provider 仍未完成，不能用旧容器或离线测试代替。

### M72 全局下一步

- 统一空间总览、比较、约束筛选和动态 Console 的证据引用与地图图层状态，增加真实配置浏览器 smoke。
- 增加源数据/派生层版本绑定、变更检测、nodata/边界/重采样报告，区分 metadata readiness 与完整哈希校验。
- 用真实能力快照驱动开放式问题澄清、计划修复和可选 live GIS 模型基线；Docker 恢复后完成生产镜像、readiness、重启恢复和 FastAPI acceptance。

### M72 验收结果

- 新增源数据绑定模块和 `scripts/verify_analysis_ready.py`；分析就绪报告为行政区、DEM、土地利用源文件记录确定性 SHA-256 指纹，源文件变更或缺失会在显式 verifier 中被标记。
- 健康报告只输出绑定版本、指纹和数据集摘要，保留 `verification_mode=metadata` 与 `hashes_verified=false` 的运行时边界；不将普通 readiness 误报为完整哈希校验。
- M72 专项 3 项、离线全量 375 项（42 项跳过）、GIS 全量 375 项（9 项跳过）、Smoke 和严格全局评测均通过；全局执行场景 8/8，脱敏模型回放 2/2。
- 真实武汉 `analysis-ready-report.json` 的源绑定 verifier 通过 14 个文件、0 个 mismatch，指纹 `sha256:b648973f4707b9cb63ecfeb9c680c692dd34cd491ec8e8fed2b4ffbea6584f5f`。
- Docker Linux engine、生产镜像/readiness、FastAPI acceptance、浏览器真实配置 smoke 和 live provider 仍未完成，不能用旧容器或离线结果替代。

### M73 全局下一步

- 将源绑定与派生版本接入能力快照、发布检查、总览/比较/约束结果和地图证据；补 nodata、边界、重采样与输出 manifest 联动校验。
- 基于真实能力快照执行模型澄清/计划修复回放和可选 live GIS 基线，并区分 provider、计划、工具门控和后端错误。
- Docker 恢复后完成当前版本生产镜像、数据卷、readiness、重启恢复、多 worker 和 FastAPI acceptance；同时补真实配置浏览器 smoke。

### M73 验收结果

- 运行时能力快照、数据证据、比较结果和 Console 统一传播 `analysis_ready.source_binding`，包含绑定版本、SHA-256 指纹、核验模式、源数据集和状态；不暴露逐文件哈希。
- M73 专项 3 项、兼容回归 17 项、离线全量 379 项（42 项跳过）、GIS 全量 379 项（9 项跳过）、Smoke 和严格全局评测均通过；全局执行场景 8/8，脱敏模型回放 2/2。
- 真实武汉快照验证 `data_readiness=ready`、`analysis-ready-v1`、`EPSG:32649`、`aligned` 和源绑定指纹 `sha256:b648973f4707b9cb63ecfeb9c680c692dd34cd491ec8e8fed2b4ffbea6584f5f`；manifest 仍明确为 metadata-only。
- Docker Linux engine、生产镜像/readiness、FastAPI acceptance、浏览器真实配置 smoke 和 live provider 仍未完成，不能用离线或旧容器结果替代。

### M74 全局下一步

- 增加 nodata、边界范围、重采样策略、派生输出 manifest 与源绑定的联动校验和发布报告。
- 把统一证据摘要接入总览/比较/约束地图工作区，补真实配置浏览器 smoke；执行真实能力快照驱动的模型澄清、计划修复和 live GIS 基线。
- Docker 恢复后完成当前版本数据卷、readiness、重启恢复、多 worker 与 FastAPI production acceptance。

### M74 验收结果

- 分析就绪报告新增并校验 `derivation`：DEM `bilinear`、土地利用 `nearest`，nodata `-9999/0`，边界源 CRS `EPSG:4490`、13 个行政区；非法土地利用策略会进入 `not_ready`。
- M74 专项 2 项、离线全量 381 项（42 项跳过）、GIS 全量 381 项（9 项跳过）、Smoke 和严格全局评测均通过；全局执行场景 8/8，脱敏模型回放 2/2。
- 真实武汉报告和 readiness 已返回派生策略、边界证据、`analysis-ready-v1`、`aligned`；源绑定 verifier 14 个文件、0 mismatch。
- Docker Linux engine、生产镜像/readiness、FastAPI acceptance、浏览器真实配置 smoke 和 live provider 仍未完成，不能用旧容器或离线结果替代。

### M75 全局下一步

- 增加派生输出 manifest 一致性报告，区分 metadata、源绑定 SHA-256 和输出文件 SHA-256 证据。
- 将完整性摘要接入地图/轨迹/答案和真实配置浏览器 smoke；执行真实能力快照驱动的模型澄清、计划修复和 live GIS 基线。
- Docker 恢复后验收当前版本数据卷、readiness、重启恢复、多 worker 和 FastAPI production 接口。
