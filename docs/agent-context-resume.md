# Spatial Agent 对话恢复文档

本文档用于在新对话中恢复 Spatial Agent 项目的开发上下文。新对话开始后，应先阅读本文档，再检查 Git 状态和相关文件，然后继续当前任务。

## 当前全局执行规则

- 全局 goal 持续执行“整体规划 -> 可并行实现 -> 集成测试 -> 整体重规划”循环。
- 当前最大并发度为 3，任一阶段最多启动 3 个并行子任务。
- 并行任务必须在共享 schema、runtime 状态、result envelope 和能力目录上统一集成。

## 项目定位

Spatial Agent 是一个面向求职展示的 AI Agent Runtime 项目，空间数据只是业务载体。核心展示点是：

- Planner 与 Runtime 分离。
- LLM Planner 与 RuleBasedPlanner 可替换。
- TaskPlan 结构化输出和 schema 校验。
- Tool Registry 统一验证和 dispatch。
- SpatialBackend 可替换。
- 真实 GeoJSON、Rasterio 数据接入。
- 多轮澄清。
- 用户可读答案和执行 trace。
- HTTP API。
- Artifact 导出。
- 离线测试、smoke check 和 CI。

## 已完成里程碑

- M0：设计基线、工具 schema、评测用例。
- M1：最小 Agent Runtime、ToolRegistry、RuleBasedPlanner、内存空间后端。
- M2：LLMPlanner、OpenAIPlannerClient、TaskPlan JSON schema、Fake LLM 测试。
- M3：SpatialBackend、InMemorySpatialBackend、SpatialToolAdapter。
- M4：评测运行器、步骤耗时、JSON 报告。
- M5：GeoPandas/Rasterio 数据集探测。
- M6：真实行政区 GeoJSON backend 和 HybridSpatialBackend。
- M7：自然语言行政区查询。
- M8：AnswerComposer。
- M9：多轮澄清和 session 隔离。
- M10：AgentService、HTTP API。
- M11：smoke check 和 GitHub Actions CI。
- M12：API contract 文档和边界测试。
- M13：trace formatter。
- M14：artifact export。
- M15：DEM/土地利用栅格 metadata backend。

M15 已推送 commit：

~~~text
0ae304a feat: add raster metadata backend
~~~

## 当前进行中的 M16

M16 目标是完成真实 LLM Planner 的本地 demo 路径，但不让 CI 依赖真实模型：

- 本地配置读取。
- 自定义 provider URL。
- API key header auth。
- model 和 reasoning effort 配置。
- 可选 live smoke test。
- RuleBasedPlanner 继续作为默认、离线、确定性路径。
- DeepSeek Chat Completions 模式已接入并通过真实 live smoke。
- 当前中转 Responses provider 可达但模型 POST 超时，不能作为已验证路径。

当前相关文件：

- agent/llm_planner.py
- agent/openai_config.py
- run_demo.py
- config/openai.example.json
- config/openai.local.json
- tests/test_m16_openai_config.py
- docs/api.md
- README.md

config/openai.local.json 是本地私有配置，已被 Git 忽略，不能提交或输出真实 key。

## Codex Provider 配置

已读取本机 Codex 配置，发现 provider 语义是：

~~~toml
model_provider = "custom"
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"

[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "https://crs.ruinique.com"
~~~

因此项目本地配置当前应使用：

- wire API：Responses。
- base URL：https://crs.ruinique.com。
- 认证方式：Authorization Bearer header。
- 模型：gpt-5.6-luna。
- reasoning effort：medium。

代码仍保留 api_url 和 query auth 作为可选兼容能力，但 Codex 对应的默认语义是 base_url + header auth。

## 已诊断的真实模型问题

第一次 live 请求返回：

~~~text
HTTP 403
error code: 1010
~~~

诊断发现：

- Python urllib 默认 User-Agent 会被 provider 网关拒绝。
- 加上普通 User-Agent 和 Accept: application/json 后，provider 对 /responses 和 /v1/responses 都可以返回 HTTP 200。
- agent/llm_planner.py 已加入 Accept、Content-Type、User-Agent 和 Authorization headers。

因此 403 的主要根因已经解决，不要优先继续猜测 /v1 或 query key。

## 当前真实模型剩余问题

加 header 后，模型已经能返回结构化 JSON，但曾返回了不符合项目 TaskPlan 的简写：

~~~json
{
  "outcome": "success",
  "tool": "get_raster_metadata",
  "args": {
    "dataset": "dem",
    "max_files": 3
  }
}
~~~

项目需要完整 TaskPlan：

~~~json
{
  "goal": "inspect raster dataset metadata",
  "steps": [
    {
      "id": "raster-metadata",
      "tool": "get_raster_metadata",
      "args": {
        "dataset": "dem",
        "max_files": 3
      },
      "depends_on": []
    }
  ],
  "output": {
    "type": "raster_metadata_result",
    "summary": true
  }
}
~~~

随后 live planner 还出现过领域词汇问题：用户说“查询 DEM 栅格元数据”，模型要求提供 DEM dataset ID。已在 LLMPlanner prompt 中补充：

- DEM/高程/地形 -> dataset dem。
- 土地利用/地类 -> dataset land_use。
- 行政区 -> dataset admin_areas。
- 道路 -> dataset roads。
- 坡度 -> dataset slope。

## 当前恢复位置：M61 基础实现已推送，等待部署环境复验

已获取并核验武汉道路、水体、行政区、DEM 和土地利用数据。M50 已完成真实栅格候选与 OSM 道路/水体约束闭环；M51 已新增 `get_dataset_health_report`，并接入工具 schema、规则 Planner、LLM guidance、中文 AnswerComposer 和 Console 的数据健康面板；M52 又增加了 DEM/土地利用跨栅格覆盖关系检查。

真实武汉健康检查结果：行政区、道路、水体为 `ready`；DEM 和土地利用文件可读取，但跨 `EPSG:32649`/`EPSG:32650`，因此标记为 `degraded`。M54-M56 已将健康预检接入综合建设分析、单独区域栅格统计和复合行政区栅格分析，并增加能力声明和不可用数据门控。M61 已增加核心/可选数据分层、异步幂等与重启恢复、真实模型重试观测和 Console 层状态显示；离线 236、GIS 226、全局评测和浏览器烟测通过。

M50 期间修复了两个问题：Rasterio `from_bounds` 在当前 Windows GIS 环境触发 native exit；全量道路/水体 `unary_union` 导致内存暴涨。根因、修复和预防已记录在 `docs/agent-development-issues.md`。

## M60 已完成的当前改动

- 新增 `agent/runtime_capabilities.py`，按需生成包含数据质量、覆盖范围、CRS、文件数、检查文件数和更新时间的运行时能力快照。
- `agent/capability_catalog.py` 新增 `runtime_capability_catalog()`；`agent/data_quality.py` 的健康报告增加 `updated_at`。
- `serve_api.py` 和 `production_api.py` 接入 `GET /capabilities/runtime`。
- `scripts/production_acceptance.ps1` 增加运行时能力快照检查并输出 `runtime_health`。
- 运行时快照测试已加入 `tests/test_m59_capability_catalog.py`。

## M60 验证状态

- 运行时能力和入口契约测试通过；默认环境缺少 FastAPI 的测试按环境条件跳过。
- 生产容器已重新 build，快照、健康、异步提交/轮询和 production acceptance 通过；完整健康为 `unavailable` 仅因容器示例数据卷缺少 roads/water。
- SQLite 跨进程结果引用、清空会话、取消标记和失败重试测试 4/4 通过；离线 208、GIS 205、smoke、全局评测和浏览器烟测通过。

## M61 下一步任务

进入 M61：全局产品能力、数据质量、真实模型、部署可靠性和用户体验深化。M60 已完成运行时能力快照和异步跨进程可靠性基础。

1. 分层处理核心与可选数据健康，完善武汉道路/水体生产数据卷和 CRS/覆盖降级说明。
2. 深化异步幂等、异常重启恢复、状态观测和真实模型超时/重试指标。
3. 扩展开放式空间问答的意图、澄清和多工具编排，并让 Console 按结果类型动态展示。

大阶段最多拆分 3 路并行；仅将边界清晰、可独立测试且不同时修改同一公共契约的任务并行执行。所有任务必须在共享 schema、runtime 状态、result envelope 和能力目录上统一集成。

## M61 当前实现状态

- 数据质量已区分核心与可选层，运行时能力快照暴露核心/可选健康和能力级门控。
- 异步 SQLite 已接入请求指纹、显式幂等键、重复提交复用、清空会话清理和新服务重启接管。
- OpenAI 兼容客户端已接入可配置超时、暂态重试、退避和安全 token/延迟指标；不重试鉴权失败或 WinError 10013。
- M61 专项测试 20 项通过；离线/GIS、全局评测和浏览器集成验证已通过。
- M61 已推送 `ac38f3a` 与 `85b1ce4`；Docker 新镜像重建未完成，当前 Docker 服务被 Windows named pipe/service 权限阻塞，不能把旧容器响应当作新镜像证据。

## M62 当前进展

- 新增 `agent/spatial_intent.py`，为开放式空间问题提供候选能力和澄清提示，不绕过 Planner、schema 或 ToolRegistry。
- 未命中固定规则的空间请求不再统一落到旧 M1 错误；已匹配的空间能力会提示补充区域、数据集或阈值。
- M62 新增测试已通过；下一步是结构化澄清 API/Console 展示、全局评测和 Docker 环境复验。
- M62.1 已将结构化澄清详情接入 `AgentRunResult`、SQLite、`result` envelope 和 Console；保留旧 `error` 文本兼容客户端。下一步是 HTTP/评测契约、能力目录标签和 Docker 复验。
- M62.2 已让澄清候选复用 `capability_catalog` 中文标签，并增加标准 HTTP 结构化澄清测试；离线全量 243 项通过。下一阶段重点是多工具开放式编排、证据评测和生产 Docker/GIS 复验。
- M63 已开始受控空间总览编排：`spatial_overview` 生成 8 步跨来源计划并返回 `spatial_overview_result`；专项回归通过，待全局评测、浏览器、GIS 和 Docker 验收。
- M63 已完成联合验收：GIS 41 项通过；Docker 重建后 `healthy`、生产 acceptance 通过；容器同步空间总览返回 8 步 `spatial_overview_result`。同时修复生产同步路由误传异步 `idempotency_key`，离线全量 245 项通过、32 项跳过。下一阶段重点是真实几何证据、真实模型结构化总览和 Console 动态结果展示。
- M64 已验证真实武汉总览 GeoJSON 的最终几何证据：导出受限时正确为 `truncated_geometry`，来源包含 `geojson/geopackage`，道路/水体 feature 带 dataset 标签；LLM guidance 和 Console 总览结果注册已更新。下一步是浏览器、真实模型和 Docker 多进程验收。
- M64 已完成 DeepSeek live 总览规划验证：返回 `spatial_overview_result` 和 8 个注册工具步骤；真实 GIS 几何与模型规划证据仍分开统计。

## M65 当前进展

- 已新增脱敏录制模型响应回归，验证空间总览 8 步计划、依赖 DAG、结果绑定和 ToolRegistry 实际执行，默认不访问网络。
- 已增加多 worker 异步提交、独立轮询、幂等和 claim 后崩溃恢复测试；修复首次提交被误标为幂等复用，以及 Windows 已退出 worker 被误判为存活的问题。
- Console 已增加 `spatial_overview_result` 紧凑摘要面板；已有多区域对比服务能力纳入本阶段验收。
- M65 已完成全量离线/GIS、Smoke、Docker 重建和 production acceptance，已推送 `1fbc4cc`；浏览器当时仅因未启动 Chrome CDP 未执行。

## M66 当前进展

- M66-E 已加入开放式空间澄清和跨区域对比全局评测契约，并推送 `ed56e26`。
- M66-A 已增加真实 GIS 空间总览 live 端到端测试；必须同时开启 `SPATIAL_AGENT_LIVE_OPENAI=1`、`SPATIAL_AGENT_LIVE_GIS=1` 并使用 `spatial-agent-gis` 环境。测试验证 `spatial_overview_result`、8 类工具覆盖、全部步骤完成和中文答案，最多容忍 provider 暂态失败重试 3 次。
- M66-C 已修复异步轮询/服务重启丢失最终 `geometry_evidence` 的问题，新增同步/异步/重启证据矩阵。
- M66-D 已增加隔离 Chrome CDP 启动脚本、总览面板/地图分层 smoke 以及 `CDP_URL`/`CONSOLE_URL` 配置；待实际启动 CDP 后执行。
- M66 已完成最终全量、Docker 和浏览器联合验收；下一阶段为 M67，按产品能力、数据质量、真实模型、部署可靠性和用户体验五个维度推进。

## M67 当前实现与验证状态

- 数据集目录、健康报告和 runtime capability snapshot 已支持受控数据 provenance；来源、版本、署名和许可字段经过 allowlist/长度限制，旧配置保持兼容。
- 脱敏模型回放已接入全局评测，覆盖工具覆盖、依赖 DAG、结果类型、中文答案、token/延迟和 provider 错误分类，默认不访问网络。
- SQLite 与内存异步链路已提供生命周期、排队/运行耗时、失败分类、取消和重启接管观测；HTTP 提供 `/runs/{run_id}/observability` 与 `/runs/{run_id}/async`，`/metrics` 提供 `async_jobs` 聚合。
- Console 结果证据区按响应动态显示几何、运行时能力、数据来源、provenance 和降级状态；总览地图验证行政区、道路、水体三色分层。
- M67 专项 22 项、离线全量 293 项（35 项跳过）、GIS 全量 293 项（9 项跳过）、smoke、全局评测、Docker production acceptance 和串行 Chrome CDP 验收均通过。
- 当前阶段已完成，下一阶段按产品能力、数据质量、真实模型、部署可靠性和用户体验整体规划 M68；并行上限保持 3。

## M68 全局规划

1. 配置化空间工作流、结构化约束和证据选择。
2. 可复现道路/水体数据卷、provenance 校验和跨栅格覆盖/对齐报告。
3. 开放式空间问答、澄清和失败修复的脱敏回放与可选 live 基线。
4. SQLite 升级、多 worker 观测一致性、取消/超时边界和滚动重启恢复。
5. 统一动态答案、轨迹、证据和地图工作区，减少空面板并解释降级状态。

M16 的真实模型路径仍保持可选，不阻塞离线和 GIS 回归：

~~~powershell
$env:SPATIAL_AGENT_LIVE_OPENAI='1'
python -m unittest tests.test_m16_openai_config.M16LiveOpenAIPlannerTests -v
~~~

DeepSeek live smoke 已通过。若继续诊断中转 provider，重点检查：

1. 模型 POST 是否在 provider 上游完成。
2. Codex 与 Python client 的 endpoint、协议和 streaming 是否一致。
3. 是否返回 HTTP 状态、模型 JSON 或仅发生读取超时。

M16 收尾顺序：

1. 轮换已在对话中暴露的 API key。
2. 保持 ToolRegistry 作为最终执行边界。
3. 运行全量离线测试、smoke check 和 DeepSeek live smoke。
4. 提交 M16，建议 commit message 为：

~~~text
feat: add openai planner local config
~~~

## 标准验证命令

非 GIS 全量测试：

~~~powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m unittest discover -s tests -v
~~~

Smoke check：

~~~powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\smoke_check.py
~~~

GIS 回归：

~~~powershell
& 'D:\code\conda\Scripts\conda.exe' run -n spatial-agent-gis python -m unittest tests.test_m6_geojson_admin_backend tests.test_m7_admin_planner tests.test_m8_answer_composer tests.test_m9_clarification_loop tests.test_m15_raster_metadata -v
~~~

Git 检查：

~~~powershell
git -c safe.directory=D:/Project/job/ai-agent status --short --branch
git -c safe.directory=D:/Project/job/ai-agent diff --check
git -c safe.directory=D:/Project/job/ai-agent check-ignore -v config/openai.local.json
~~~

## 重要约束

- 不提交 config/openai.local.json。
- 不提交 API key、token 或私有 provider 返回内容。
- 不提交 D:/dataset/agent 下的原始 GIS 数据。
- CI 和默认 smoke check 不调用真实模型。
- 新增 Agent 工具时，同时更新 schema、adapter、planner guidance、answer composer、测试和文档。
- 真实模型失败时，先判断是网络、provider、模型输出、plan 校验还是 backend 执行问题。
- 新遇到的 Agent 开发问题，记录到 docs/agent-development-issues.md。
- 开发采用“整体规划 -> 可并行实现 -> 集成测试 -> 整体重规划”循环；可并行子任务最多 3 个。
- 每个阶段完成后更新 docs/milestones.md、恢复文档，并创建一个 GitHub 版本；私有配置和原始数据不得提交。
- 全局 goal：持续执行“整体规划 -> 最多 3 路可并行实现 -> 统一集成测试 -> 全局重规划”，阶段验收通过后提交并推送版本；规划必须覆盖产品能力、数据质量、真实模型、部署可靠性和用户体验。

## M68 收尾状态

- 已实现受控工作流模板和严格计划校验：工具 allowlist、结果类型、必需条件、步骤上限、依赖 DAG 均在 `agent/workflow_templates.py` 统一验证；能力目录和 `/workflows` API 已接入。
- 已实现 metadata-only 栅格对齐证据：`agent/raster_alignment.py` 检查 CRS、分辨率、原点、范围、尺寸、旋转和覆盖关系；健康报告/runtime 快照暴露 `grid_alignment`，不读取 DEM/土地利用像元。
- 已实现 SQLite 生命周期字段迁移、异步 worker 数量配置和内存会话创建/列表/历史恢复/清空/删除。
- 验证通过：M68 专项 47 项，另加 smoke 回归 1 项；离线全量 340 项（35 项跳过）；GIS 全量 340 项（9 项跳过）；全局评测严格模式 8/8 执行场景通过、3 项可选场景跳过。
- Docker Desktop 当前仍无法连接 Linux engine：`dockerDesktopLinuxEngine` named pipe 不存在，`com.docker.service` 服务项不可用。该宿主环境问题已写入开发问题日志，新镜像/容器 readiness/production acceptance 尚无 M68 证据。

## M69 全局规划

1. 产品能力：版本化工作流模板、可编辑结构化约束、计划修订和动态 Console 结果工作区。
2. 数据质量：武汉全量数据 manifest、下载/哈希校验、provenance 版本锁定与像元级对齐前置门控。
3. 真实模型：开放式多轮澄清、非法计划修复、失败重试的脱敏回放和可选 live 基线。
4. 部署可靠性：SQLite 迁移与多 worker 的超时、取消、幂等、滚动重启组合验收；Docker 恢复后补生产镜像验收。
5. 用户体验：答案、轨迹、证据和地图互相引用，并明确展示数据版本、对齐状态和降级原因。

M69 最多启动 3 路并行子任务；并行任务不得各自修改公共 schema 或 result envelope，必须由主线统一集成。每阶段完成后更新本文件、`docs/task-resume.md`、`docs/milestones.md` 和中文开发问题日志，并提交推送一个 GitHub 版本。

## M69 当前实现进展

- 工作流模板契约已支持版本、结构化约束和证据选择；开发/生产 HTTP 均支持 validate/revise，计划修订仍经过统一模板、TaskPlan 和 DAG 校验。
- 数据 manifest 支持确定性文件记录、SHA-256 显式验证和受控 provenance；配置 manifest 时健康检查默认只做路径/大小/provenance 轻量校验。
- 脱敏模型回放已加入全局评测，覆盖多轮澄清和失败计划修复，当前两条回放均通过。
- Console 已从 `/workflows` 动态渲染约束/证据编辑器；`workflow` 已贯通同步/异步 `/runs`、Planner、Runtime、内存状态和 SQLite 恢复，生成计划会再次按模板校验。
- 联合 DEM/土地利用像元工具已要求显式 `grid_alignment=aligned`；仅文件覆盖关系为 ready 或网格不一致时，Runtime 在 dispatch 前阻止工具并给出中文原因。
- 新增兼容性修复：无工作流请求不再向旧 Runtime 替身传递 `workflow=None`，异步几何证据矩阵和 `scripts/smoke_check.py` 已恢复通过。
- M69.2 已完成武汉 manifest 正式绑定入口、完整哈希校验和 SQLite 多 worker 可靠性矩阵；M69 仍待 Docker 新镜像、生产 readiness/acceptance 和可选 live provider 验收。

## M69.2 当前进展

- `DatasetCatalog` 支持必需 manifest 配置；`scripts/bind_dataset_manifest.py` 生成仓库外的正式本地绑定配置。
- manifest 健康检查显式标记 `verification_mode=metadata`；完整 `sha256` 校验由 `scripts/dataset_manifest.py --verify` 执行，并可用 `--evidence-output` 保存安全摘要。
- `/capabilities/runtime` 暴露 manifest 状态、校验模式、已核对文件数和 `data_readiness`；生产 readiness 可用 `SPATIAL_AGENT_REQUIRE_DATASET_MANIFEST=1` 开启门控。
- 本机真实武汉数据 manifest 已核验 16 个文件且 `hashes_verified=true`；manifest、绑定配置和 evidence 位于 `D:\tmp\wuhan-gis`，不得提交。
- SQLite 矩阵已覆盖 3 worker 幂等提交、超时终态重放、取消/超时重启接管和滚动重启指纹复用；并修复直答计划绕过取消/超时控制检查的问题。
- 离线全量 363 项（35 项跳过）、GIS 全量 363 项（9 项跳过）、smoke、全局严格评测和真实本地 DEM/道路/水体调用均通过。
- 当前工作区只允许保留用户未跟踪 `.idea/`；M69.2 进入文档审查、提交推送阶段。Docker Linux engine 缺失和 FastAPI 生产依赖缺失仍是外部验收边界。
