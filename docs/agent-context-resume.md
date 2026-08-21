# Spatial Agent 对话恢复文档

本文档用于在新对话中恢复 Spatial Agent 项目的开发上下文。新对话开始后，应先阅读本文档，再检查 Git 状态和相关文件，然后继续当前任务。

## 当前全局执行规则

- 全局 goal 持续执行“整体规划 -> 顺序实现 -> 集成测试 -> 整体重规划”循环。
- 阶段规划的总体参考见 `docs/agent-project-direction.md`；先确认完整 Agent 闭环和面试展示能力，再决定局部实现任务。
- 当前最大并发度为 5；仅对边界清晰、可独立验收且不修改同一共享契约的任务并行。共享 schema、result envelope、Runtime 状态迁移和前端核心函数仍由主线统一集成。
- 所有任务按依赖顺序在共享 schema、runtime 状态、result envelope 和能力目录上逐项集成并验证。
- 每次规划下一阶段必须先做项目全局盘点，覆盖产品能力、架构边界、数据质量、真实模型、部署可靠性、前端体验和测试证据；不能被最近一次数据细节或局部 bug 带偏，数据任务只能作为整体目标下的实现手段。
- 规划门槛：先写出上述七个维度的现状、缺口、依赖和验收证据，再确定阶段目标与顺序任务；任何单个数据集、工具错误、模型调用或页面缺陷都必须说明它服务于哪个系统级目标，不能直接替代阶段规划。
- 重规划输出至少回答：本阶段如何提升完整 Agent 闭环、哪些架构/契约需要先稳定、哪些风险会阻塞真实部署，以及完成后用什么跨入口证据重新评估全局；只有完成这一步，才允许进入实现拆分。
- 阶段应组织为较完整的纵向切片，通常同时覆盖架构 seam、跨入口能力、测试证据、文档和部署影响，避免每个小改动单独成阶段；开发中只运行必要的快速/专项检查，阶段收尾再统一运行一次代表性专项与一次全量回归。

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
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m unittest discover -s tests -t . -v
~~~

Quick profile：

~~~powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\test_profile.py --profile quick
~~~

Service smoke：

~~~powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\test_profile.py --profile smoke
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
- 开发采用“整体规划 -> 顺序实现 -> 集成测试 -> 整体重规划”循环；当前不启动并行子任务。
- 规划下一阶段时必须顾全项目整体，先回答本阶段如何提升完整 Agent 系统，再决定是否处理具体数据集、单个工具或单个页面问题；不得以局部数据修复替代全局规划。
- 每个阶段完成后更新 docs/milestones.md、恢复文档，并创建一个 GitHub 版本；私有配置和原始数据不得提交。
- 全局 goal：持续执行“整体规划 -> 单线程顺序实现 -> 统一集成测试 -> 全局重规划”，阶段验收通过后提交并推送版本；规划必须覆盖产品能力、数据质量、真实模型、部署可靠性和用户体验。

## 当前重组后的总体 Goal

当前目标已从“持续增加空间分析功能”重组为“建设通用、可组合、可解释的空间智能体”。请求理解层必须独立抽取空间实体、任务意图、数据需求、约束和输出证据；能力目录与工具 schema 负责发现可用能力；Planner 负责生成统一 `TaskPlan`；Runtime 负责 DAG 校验、安全门控、数据健康、预算、取消、超时、重试和证据闭环。

新增区域或功能不得通过专用区域分支堆叠实现，应优先扩展通用实体解析、能力声明、工具契约和结果类型。规则规划器与真实模型共享计划和执行契约，具体区域只作为参数解析结果；洪山区综合空间分析只是复杂回归样例。

goal 工具的 objective 只能在创建时设置，不能直接编辑未完成 goal；当前 goal 的并发描述若与本规则冲突，以本文件和后续任务文档的当前有效规则为准。后续每阶段采用单线程顺序执行、阶段版本推送和“规划 -> 实现 -> 测试 -> 重规划”循环。

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

## M70 已完成

- 新增 `scripts/prepare_analysis_rasters.py`，按武汉 13 区边界生成固定目标网格，将原始 DEM/土地利用重投影为同一 CRS、分辨率、原点、范围和尺寸；原始数据保持只读。
- 本机真实输出目标为 `EPSG:32649`、30 米、4562×5277，`analysis-ready-report.json` 标记 `grid_alignment=aligned`；派生 manifest 5 项完整 SHA-256 已通过。
- 派生配置下真实建设适宜性执行完成：有效像元 576,040、候选像元 23,172、候选比例 0.040226，GeoJSON 导出包含真实候选要素。
- `DatasetCatalog`、健康报告和 `data_readiness` 已支持必需的分析就绪报告；缺失报告、非法 JSON、网格未对齐和派生输出失配都会阻止联合像元能力。
- runtime capability snapshot、Console 数据证据和中文答案已显示派生版本、目标 CRS、分辨率和对齐状态；真实建设候选答案已引用 `analysis-ready-v1`、`EPSG:32649`、30 米和 `aligned`。
- 新增 SQLite WAL 初始化锁重试，解决 GIS conda 环境多 worker 初始化竞态；Windows conda 中文 JSON 输出编码问题已记录并通过 ASCII 验收摘要规避。
- M70 专项 19 项通过；离线全量 369 项通过、41 项跳过；GIS 全量 369 项通过、9 项跳过；Smoke 通过；严格全局评测 8/8 场景、脱敏模型回放 2/2 通过。
- 真实武汉分析就绪配置位于 `D:\tmp\wuhan-gis`，派生文件、配置、manifest 和 evidence 均不得提交。Docker Linux engine 仍是外部部署验收边界。

## M71 全局重规划

1. 产品能力：把真实分析就绪数据纳入空间总览、道路/水体约束和多区域比较，统一返回候选像元、有限几何和数据版本证据。
2. 数据质量：为派生报告、manifest 和原始来源建立版本绑定/变更检测，补充 nodata、边界范围和重采样策略的可审计证据。
3. 真实模型：增加基于真实能力快照的开放式问题澄清与脱敏回放，验证模型能选择分析就绪工作流且不会绕过门控。
4. 部署可靠性：恢复 Docker Linux engine 后构建新镜像并执行 manifest/analysis-ready readiness、容器重启和多 worker 验收；FastAPI 依赖可用时补生产入口矩阵。
5. 用户体验：继续精简 Console 证据区，把数据版本、目标网格、候选统计、几何状态和降级原因做成可扫描的结果摘要，并补真实配置浏览器 smoke。

M71 仍最多 3 路并行；公共 schema、result envelope、数据 provenance 和 Console 证据由主线统一集成。阶段验收顺序保持“离线全量 -> Smoke -> GIS 全量 -> 全局评测 -> 部署/浏览器”，完成后提交并推送版本。

## M71 当前完成状态

- `/comparisons`、`/region-comparisons` 和道路/水体约束答案已统一传播 `analysis_ready` 证据；Console 比较结果显示派生版本、目标网格、分辨率和对齐状态。
- M71 专项 3 项通过；离线全量 373 项通过、42 项跳过；GIS 全量 373 项通过、9 项跳过；Smoke、严格全局评测 8/8 和脱敏模型回放 2/2 通过。
- 真实武汉分析就绪绑定配置验证：`analysis-ready-v1`、`EPSG:32649`、30 米、4562×5277、`aligned`；洪山区 20° 候选 23,172 个，江夏区 20° 候选 59,045 个；道路/水体约束完成并返回版本证据。
- GIS 全量第一次运行中嵌套 smoke 出现一次异步 artifact 引用缺失，单测重复、单独 smoke 和完整复跑均通过；该验收时序问题已写入 `docs/agent-development-issues.md`。
- M71 已具备提交推送条件；`.idea/`、本机配置、真实派生数据和 evidence 仍不得提交。Docker Linux engine、生产 acceptance、浏览器真实配置 smoke 和 live provider 仍未验证。

## M72 下一步

进入 M72，全局推进结果证据统一、源数据/派生数据变更检测、真实能力快照驱动的模型回放、Docker/生产 acceptance 和真实配置浏览器 smoke；继续遵循最多 3 路并行与“整体规划 -> 实现 -> 测试 -> 全局重规划”循环。

## M72 当前完成状态

- 新增 `agent/analysis_ready_binding.py` 和 `scripts/verify_analysis_ready.py`；分析就绪报告现在记录行政区/DEM/土地利用源数据的 SHA-256 绑定指纹，换数后可在发布前显式检测变更。
- 健康报告展示受控源绑定摘要，不暴露逐文件哈希，也不在普通 readiness 请求中执行大文件完整校验；旧报告保持兼容。
- M72 专项 3 项通过；离线全量 375 项通过、42 项跳过；GIS 全量 375 项通过、9 项跳过；Smoke、严格全局评测 8/8 和脱敏模型回放 2/2 通过。
- 真实武汉源绑定 verifier 通过 14 个文件，`mismatch_count=0`，指纹为 `sha256:b648973f4707b9cb63ecfeb9c680c692dd34cd491ec8e8fed2b4ffbea6584f5f`；运行时 manifest 仍诚实标记为 metadata-only。
- M72 已具备提交推送条件；`.idea/`、本机配置、真实派生数据和 evidence 不得提交。Docker Linux engine、生产 acceptance、live provider 和真实配置浏览器 smoke 仍未验证。

## M73 下一步

进入 M73，优先把源绑定/派生版本接入发布能力快照和完整结果证据，再推进真实模型回放、浏览器 smoke 与 Docker 生产验收；继续按全局循环推进。

## M73 当前完成状态

- 运行时能力快照、DEM/土地利用数据证据、比较摘要和 Console 现在统一传播受控 `source_binding`；只展示版本、指纹、核验模式、数据集和状态。
- M73 专项 3 项、兼容回归 17 项通过；离线全量 379 项通过、42 项跳过；GIS 全量 379 项通过、9 项跳过；Smoke、严格全局评测 8/8 和脱敏模型回放 2/2 通过。
- 真实武汉能力快照返回 `analysis-ready-v1`、`EPSG:32649`、`aligned`、源绑定指纹 `sha256:b648973f4707b9cb63ecfeb9c680c692dd34cd491ec8e8fed2b4ffbea6584f5f`，`data_readiness=ready`；运行时 manifest 仍为 metadata-only。
- M73 已具备提交推送条件；Docker Linux engine、生产 acceptance、live provider 和真实配置浏览器 smoke 仍未验证，`.idea/`、本机配置和真实数据不提交。

## M74 下一步

进入 M74，优先完成 nodata/边界/重采样/派生输出一致性报告，再做真实模型基线、浏览器 smoke 和 Docker 生产验收。

## M74 当前完成状态

- 分析就绪报告与健康检查已支持 `derivation` 策略：DEM `bilinear`、土地利用 `nearest`、nodata、源 CRS、武汉 13 区边界和行政区数量；非法新报告会阻止必需 readiness。
- M74 专项 2 项通过；离线全量 381 项通过、42 项跳过；GIS 全量 381 项通过、9 项跳过；Smoke、严格全局评测 8/8 和脱敏模型回放 2/2 通过。
- 真实武汉配置返回派生策略和边界证据且 `data_readiness=ready`；源绑定 verifier 14/14、0 mismatch。
- M74 已具备提交推送条件；Docker Linux engine、生产 acceptance、live provider 和真实配置浏览器 smoke 仍未验证，`.idea/`、本机配置和真实数据不提交。

## M75 下一步

进入 M75，优先校验派生输出 manifest 与三类完整性证据的关系，再进行动态地图/结果集成、真实模型基线、浏览器 smoke 和 Docker 生产验收。

## M75 当前完成状态

- 健康报告、能力快照、比较结果和 Console 已增加 `analysis_ready.output_manifest`，比对报告输出与 manifest basename，并显示 metadata/完整 SHA-256 证据层级。
- M75 专项 4 项通过；离线全量 385 项通过、42 项跳过；GIS 全量 385 项通过、9 项跳过；Smoke、严格全局评测 8/8 和脱敏模型回放 2/2 通过。
- 真实武汉派生 DEM/土地利用输出与 manifest 匹配，`output_manifest.status=ready`、`data_readiness=ready`，但运行时完整哈希仍为 false，源/输出完整校验通过显式 verifier 获取。
- 修复 manifest 健康摘要丢失文件名导致输出一致性误报 unavailable 的问题；只保留 basename，避免泄露绝对路径。
- M75 已具备提交推送条件；Docker Linux engine、生产 acceptance、live provider 和真实配置浏览器 smoke 仍未验证，`.idea/`、本机配置和真实数据不提交。

## M76 下一步

进入 M76，优先完成动态地图/结果证据浏览器 smoke，再推进三层发布校验、真实模型基线和 Docker 生产 acceptance。

## M76.1 当前完成状态

- Console 已增加“发布完整性”证据卡，统一展示元数据/目标网格、源绑定 SHA-256、输出 manifest 匹配和几何证据；能力快照与比较 API 传播受控输出 basename 匹配摘要。
- M76.1 专项 3 项、离线全量 388 项（42 项跳过）、GIS 全量 388 项（9 项跳过）、Smoke、严格全局评测 8/8 通过。
- 内存总览、真实武汉 GIS 总览和建设候选地图浏览器 smoke 均通过；真实总览 79 个空间要素，GeoJSON 截断状态正常显示，行政区/道路/水体三色图层通过。
- 真实配置快照：`health=ready`、`data_readiness=ready`、`analysis_ready=ready`、`output_manifest=ready`；运行时继续明确 `verification_mode=metadata`、`hashes_verified=false`，完整 SHA-256 仍由显式 verifier 证明。
- GIS 全量首次出现既有异步 artifact 引用竞态，目标测试连续 5 次、GIS smoke 和完整复跑均通过；不把该一次性时序现象归因于本次证据展示改动。

## M76.2 下一步

继续建立可下载的 metadata/源绑定 SHA-256/输出 SHA-256 三层发布报告，贯通运行 ID、答案、轨迹和地图；随后执行真实模型澄清/计划修复/live GIS 基线。Docker Linux engine 恢复后再进行当前版本生产 acceptance。该阶段当时按并发度 3 执行，属于历史记录。

## M76.2.1 当前完成状态

- 新增 `agent/release_evidence.py`、`scripts/release_evidence.py` 和 `GET /release-evidence`；报告显式分离 metadata、源绑定 SHA-256、输出 manifest SHA-256 和全量 manifest 状态。
- 开发 HTTP、生产 FastAPI 和 Console 下载链接已统一接入；报告只显示受控摘要，不暴露绝对路径或逐文件哈希。
- 真实武汉报告总体 `ready`：源绑定 14 文件、manifest 5 文件、派生输出 2 文件均完整 SHA-256 通过，0 mismatch；运行时 readiness 仍保持 metadata-only。
- 修复并记录派生配置直接验证源绑定的误报：源层从原始 binding 重建，输出层从当前派生 catalog 验证。
- M76.2.1 专项 6 项、离线全量 391 项（42 项跳过）、GIS 全量 391 项（9 项跳过）、Smoke、严格全局评测 8/8、真实 API 和浏览器 smoke 通过。

## M76.2.2 下一步

开始真实能力快照驱动的模型澄清/计划修复/live GIS 基线；Docker Linux engine 恢复后进行生产 acceptance。随后贯通发布报告与运行 ID、答案、轨迹、地图和 GeoJSON，并覆盖换数失配状态。该阶段当时按并发度 3 执行，属于历史记录。

## M76.2.2 当前完成状态

- 新增 `evaluation/live_baseline.py` 与 `scripts/live_baseline.py`，live 入口显式 opt-in；输出为脱敏结构化报告，不包含 API key、绝对路径、URL、原始模型响应或错误正文。
- 真实武汉能力快照：`health=ready`、`data_readiness=ready`、`analysis_ready=ready`、`derived_version=analysis-ready-v1`、`grid_alignment=aligned`，本地 GIS 依赖可用。
- 真实模型基线 2/2：未注册地下管线三维风险请求进入结构化澄清；“分析洪山区空间概况”完成 8 步真实 GIS 计划，包含道路和水体两次 `get_zonal_vector_summary` 调用，计划质量和中文答案通过。
- 脱敏澄清/计划修复回放 2/2；离线 394（42 跳过）、GIS 394（9 跳过）、Smoke、严格全局评测 8/8 通过；live 两请求合计 5051 token，延迟 3706.899–11176.822 ms，provider 错误 0，重试 0。

## M76.2.3 下一步

从项目全局推进部署可靠性、结果引用闭环和真实模型能力扩展：Docker 恢复后执行生产 acceptance；Console 覆盖换数失配/截断/失败重试状态；真实模型在稳定结果证据契约后扩展建设筛选与跨区域比较。该阶段当时按并发度 3 执行，属于历史记录。

## M76.2.3 当前完成状态

- `result_contract` 新增 `lineage`：运行 ID、答案状态、轨迹状态、artifact、GeoJSON 状态、地图图层和 `/release-evidence` 数据卷发布证据均有稳定索引；不暴露绝对 artifact 路径。
- `AgentService` 的同步、异步、重启恢复和 retry 路径在 trace/provenance/导出字段齐备后统一构建 envelope；已修复恢复结果缺少 trace lineage 导致跨入口不一致的问题。
- Console `renderRun` 立即渲染 lineage，再异步补全 runtime snapshot；真实浏览器总览、地图、健康、会话和清空 smoke 均通过。
- 验证：专项 3 项；离线 397（42 跳过）；GIS 397（9 跳过）；Smoke；严格全局 8/8；总览地图路径 57 个且三色图层、运行 ID 索引和空间选择均通过。

## M76.2.4 下一步

必须先进行全局能力重规划，再推进实现：产品/架构闭环扩展到异步观测、比较、重试和会话；真实模型扩展到建设筛选/道路水体约束/跨区域比较；Docker 恢复后做生产 acceptance；数据 provenance、对齐和发布报告作为支撑证据层维护。该阶段当时按并发度 3 执行，属于历史记录。

## M76.2.4 完成状态与 M76.3 规划

- 运行 lineage 已贯通完整结果、异步观测、比较结果、失败 retry 和会话历史；`retry_count` 与运行 ID 一起持久化，历史仅输出安全导航索引。
- M76.2.4 验证：离线 401 通过/42 跳过，GIS 401 通过/9 跳过，严格全局 8/8，脱敏回放 2/2，Smoke 和开发 HTTP lineage 验收通过。
- Windows worker 存活探测误判导致的 SQLite 重复接管已修复；明确查询权限/API 异常时保守视为存活，显式退出进程仍可 recovery。
- M76.3 从全局推进 Console lineage 导航、开发/生产契约版本化、Docker production acceptance 和真实模型建设/比较基线；数据 provenance/对齐/manifest 只作为跨系统证据层。
- Docker Linux engine、容器生产 acceptance 和 FastAPI production 证据仍未验证。

### M76.3.1：Harness 与上下文工程（已完成）

- 新增 `agent/context_engineering.py` 的 `ContextBuilder` 和 `ContextPacket`，定义 `spatial-agent.context.v1`，统一生成有字符预算的结构化 Planner 上下文。
- 上下文构建包含请求/追问状态、会话绑定、工作流、可用工具和 Planner 类型；按工具目录、工作流、Planner 元数据、请求内容的顺序结构化裁剪，最终 JSON 始终可解析。
- 过滤 `api_key`、`authorization`、`password`、`secret`、`token` 等敏感键，并限制深度、条目数和字符串长度。持久化只保留 `context_evidence`，包括版本、预算、长度、裁剪状态、section 大小和请求哈希。
- `AgentRuntime` 通过签名探测兼容带 `context` 和旧版 Planner；`LLMPlanner` 把上下文作为可信运行时元数据传给模型，但计划仍必须经过 TaskPlan 校验、工作流门控和 ToolRegistry。
- `context_evidence` 已传播到 `AgentRunResult`、SQLite 恢复、artifact、result envelope 和 Console。M76.3.1 专项 7 项、离线全量 408 项通过（42 项跳过）、Smoke 通过。
- 未验证项：GIS 全量、Docker Linux engine/生产 acceptance、FastAPI production、真实模型新增 baseline。恢复时必须分层执行，不能将离线结果替代这些证据。

### M77 全局规划

先复盘产品、架构/Harness、数据质量、真实模型、部署可靠性、前端体验、测试证据七维能力矩阵，再进入下一轮：

1. 让 Console 历史、比较和 retry 结果通过 lineage 打开原运行详情，贯通答案、轨迹、地图、GeoJSON、发布报告和上下文证据。
2. 建立开发 HTTP 与生产 FastAPI 的 result/observability 契约 Harness，覆盖同步、异步、SQLite 恢复、幂等、取消、超时和重试。
3. 按请求意图受控扩展会话摘要、运行时能力快照和工具结果上下文，增加上下文不足、污染、超长、成本和 token 评测；再扩展真实建设筛选、道路/水体约束和跨区域比较 baseline。
4. 继续维护 provenance、栅格对齐、manifest 和发布报告，重点验证换数失配、降级、几何截断和证据引用一致性。
5. Docker Linux engine 恢复后执行当前版本生产数据卷、readiness、多 worker、重启和 FastAPI acceptance；宿主机仍不可用时保留明确的未验证状态。

M77 及后续阶段不启动并行子任务，所有工作按依赖顺序执行。公共 result envelope、上下文契约和 Console 集成由主线统一；每阶段仍执行“全局盘点 -> 实现 -> 分层测试 -> 全局重规划”，完成后提交并推送版本。

## M81.3 当前完成状态：模板蓝图驱动的确定性 Planner

- 当前 goal 已明确为建设可测试、可观测、可替换的通用 Agent Runtime；空间 GIS 只是业务载体。
- `agent/workflow_templates.py` 新增 `goal_template`、`step_blueprint`、`output_template` 和 `compile_workflow_plan`，可以从声明式工作流模板生成完整 `TaskPlan`，并复用既有工具 allowlist、结果类型、约束、evidence 和 DAG 校验。
- `agent/rule_planning.py` 中行政区边界查询、栅格元数据、空间总览和道路/水体约束建设筛选已改为模板编译路径；RuleBasedPlanner 只绑定 RequestFacts 到模板约束，不再为这些稳定 DAG 手写步骤。
- Planner 内部自然语言 evidence 是软偏好，按模板支持项过滤；外部 workflow 选择仍保持严格校验。该问题已记录到中文开发问题日志。
- 验证：M68/M69/M77 专项 32 项通过；`python scripts/test_profile.py --profile quick` 通过；`python scripts/smoke_check.py` 通过，内嵌离线全量 550 项通过、42 项跳过；服务 smoke 通过。
- 新增 `scripts/test_profile.py` 和 `docs/test-strategy.md`：后续默认用 `quick` / `smoke` / `stage` 做分层门禁；`quick` 已进一步收敛为 3 个核心契约 tripwire，服务 smoke 独立为 `smoke` profile，`gis-core` 只跑真实 GIS 抽样用例；真实模型和 Docker 分别使用 `live-short`、`docker` profile，不再默认跑完整 live 矩阵。
- 本轮真实验收已确认：GIS Python 全量 550 项通过、9 项跳过；使用 analysis-ready 配置的精简 live 两个代表 case 2/2 通过，token 合计约 6,939；未显式设置 analysis-ready 配置时 constrained case 会因 raw 栅格 `grid_mismatch` 被正确门控。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。

## M81.4 下一阶段

从项目整体看，下一阶段不要继续添加单个 GIS 功能，而应把 LLMPlanner、模板蓝图、能力目录和可观测证据统一起来：

1. 让 LLMPlanner 消费 workflow template 蓝图/约束/result type，减少 prompt 中手写工具编排。
2. 在运行结果中记录 plan 来源、template_id、约束和安全模板证据，支撑前端解释与评测。
3. 让前端/HTTP 能展示模板计划预览、工具 DAG、执行状态和 result lineage，而不是按工具名猜测结果类型。
4. 增加离线脱敏回放和 planner 契约测试；默认 CI 不访问真实模型或私有数据。
5. Docker/GIS/live 仍作为可选分层验收，不得替代离线契约测试。
6. 测试策略继续保持 profile 化：日常只跑 3 个核心契约 tripwire 的 `quick`，服务 smoke 按需跑 `smoke`，普通阶段收口跑小型 `stage`（quick + 3 个离线 acceptance 场景）；需要旧式重型阶段门禁时显式运行 `full-stage`。真实验收按改动范围选择抽样 `gis-core`、`live-short` 或 `docker`。完整 unittest/GIS/live 只按风险触发。

## M81.4 当前完成状态：模板上下文与计划来源证据

- `workflow_template_context_summary()` 已作为模板目录对 Planner 的安全上下文接口，输出 template id、约束、result type、allowed tools、step blueprint 形状和输出类型。
- `ContextBuilder` 已注入 `workflow_templates` section，并调整预算裁剪顺序：先省略重复的 `available_tools`，尽量保留模板契约；安全裁剪深度放宽到 5。
- `LLMPlanner` prompt 已要求真实模型优先按模板契约输出普通 `TaskPlan`，减少依赖手写工具编排说明。
- `AgentRuntime` 已记录 `plan_evidence`，并通过 SQLite、artifact、result envelope 与 Console 传播；前端证据区显示计划来源。
- 验证：M68/M77/M2 目标测试 53 项通过；`quick` 与 `stage` profile 通过；`git diff --check` 仅有 Windows LF/CRLF 提示。
- 新增中文问题日志：上下文预算裁剪不能先丢模板契约。

## M81.4.1 当前完成状态：测试入口再精简

- `scripts/test_profile.py` 的默认 `quick` 已进一步收敛为 3 个核心契约 tripwire，不再包含服务 smoke。
- 服务 smoke 独立为 `smoke` profile；普通 `stage` 运行 `quick + 3 个离线 acceptance 场景`，旧式 `quick + smoke + strict global evaluation + 脱敏模型评测/回放` 改为显式 `full-stage`。
- `scripts/smoke_check.py` 默认只运行服务 smoke，完整 `unittest discover` 改为显式 `--with-unit-tests`。
- `gis-core` 抽样从 4 个真实 GIS 用例降为 3 个，保留行政区、Rasterio metadata 和 analysis-ready 门控。
- 验证：M81 profile/smoke 专项 6 项通过；`quick`、`smoke`、`stage` profile 均通过；`git diff --check` 仅有 Windows LF/CRLF 提示。
- 新增中文问题日志：Smoke 默认嵌套全量测试会绕过 profile 分层。

## M81.5 阶段规划（已执行）

从项目整体看，下一阶段继续把 Planner 契约从“上下文可见”推进到“离线可验收”：增加脱敏 LLM 回放，验证真实模型计划匹配模板 allowlist、result type、DAG 和 result reference；同时让 HTTP/Console 验收覆盖 `plan_evidence`，并评估把 `spatial_analysis` 等复杂 composer 路径模板化。默认 `quick` 只保留 3 个核心 tripwire，不因新增专项回归膨胀。

## M81.5 当前完成状态：模板计划证据离线验收

- `evaluation/model_evaluation.py` 新增 `workflow_template_match` 质量维度，脱敏模型回放现在验证模板 result type、工具 allowlist、max steps、DAG 和 result references。
- 评测报告区分 `matched_template_ids` 与 `exact_template_ids`；指定 `expected_template_id` 且模板有 blueprint 时，必须 exact 匹配才算通过。
- `tests/fixtures/m67_spatial_overview_model.json` 已要求 `spatial_overview` 精确匹配；新增反例测试覆盖缺失 result reference 的失败路径。
- 新增 `tests/test_m81_plan_evidence_acceptance.py`，验证开发 HTTP 响应的顶层 `plan_evidence`、`result.planning` 和 artifact 计划证据一致；Console 静态验收确认显示“计划来源”和 exact template。
- 验证：M67/M81 目标测试 11 项通过；`stage` profile 通过；默认 `quick` 未膨胀。

## M81.6 下一阶段

从项目整体看，下一阶段应把复杂 composer 路径纳入模板化与跨入口 Harness：先评估 `spatial_analysis` 是否补蓝图或拆为子模板，再做 CLI/HTTP/artifact/历史恢复/Console 的 result envelope 一致性验收。真实 GIS/live 只在复杂路径模板化后作为可选验收运行。

## M81.6 当前完成状态：复杂空间分析蓝图化与跨入口一致性

- `spatial_analysis` 已补充 9 步模板蓝图：数据健康、行政区 schema/query、高程、坡度、土地利用、道路、水体和约束建设筛选。
- 完整综合空间分析请求现在由 `RuleBasedPlanComposer` 绑定 RequestFacts 到 `compile_workflow_plan("spatial_analysis", ...)`；局部组合请求仍保留 composer 兜底，避免 optional step 复杂度扩散。
- Runtime Planner 上下文改用 compact 模板摘要，避免新增复杂蓝图后 `workflow_templates` 被 8KB 预算裁掉；评测默认摘要仍保留 `arg_shape` 做 exact result reference 验收。
- 复杂请求的 `plan_evidence.matched_template_ids` 与 `exact_template_ids` 均命中 `spatial_analysis`，`template_context_available=true`。
- 新增复杂请求跨入口 Harness：直接服务调用、HTTP POST、HTTP run detail、session history 和 artifact 的 result envelope、计划证据、步骤序列和 trace 可用性一致。
- 验证：M81/M68/M77 目标测试 33 项通过；`stage` profile 通过；`git diff --check` 仅有 Windows LF/CRLF 提示。

## M81.6.1 当前完成状态：阶段测试例再精简

- `evaluation/cases/stage-acceptance.json` 新增 3 个代表性离线验收场景：通用问答、复杂空间分析模板、未注册空间问题澄清。
- `scripts/test_profile.py --profile stage` 现在只运行 quick tripwire 加小型 stage acceptance；旧式重型阶段门禁改为 `--profile full-stage`。
- `scripts/evaluate_global.py` 新增 `--no-model-replay`，stage 可同时跳过脱敏模型评测和多轮回放，避免普通阶段验收隐式扩大测试例数量。
- README、测试策略和演示清单已同步，完整 discover / full-stage / live / Docker 仍保留为按风险触发的显式入口。

## M81.7 下一阶段

从项目整体看，下一阶段应做计划预览和 DAG 展示：新增只规划不执行的轻量预览接口，让 Console 能在执行前/执行中展示模板 DAG、依赖、参数来源和 evidence；随后补 `spatial_analysis` 脱敏 LLM 回放，验证真实模型也能精确遵守复杂蓝图。

## M81.7 当前完成状态：计划预览与 DAG 展示

- `AgentRuntime.preview()` 复用上下文、Planner、模板校验和计划证据，但只返回 `TaskPlan`/DAG，不执行 `ToolRegistry`、不保存 `AgentRunResult`、不生成 artifact。
- `AgentService.preview()` 复用成本治理和请求上下文；`agent/api_contract.py`、`serve_api.py`、`production_api.py` 已共享 `POST /runs/preview` 的参数边界。
- Console 有显式“预览计划”按钮、`renderPlanPreview()` 和 `renderPlanDag()`；前端只展示 Runtime 的节点、依赖和参数键。
- M81.7 专项 5 项通过；复杂空间分析 preview 为 9 节点/8 条边；Python 编译、内嵌 JS 语法和 `git diff --check` 均通过。

## M81.7 阶段规划（已执行）

先补四入口 preview envelope 一致性 Harness，再补复杂 `spatial_analysis` 脱敏 LLM 回放和 preview fingerprint/plan version。真实模型、真实 GIS 与 Docker 仍只通过显式 profile 验证；默认 quick 保持 3 个核心 tripwire，当前最大并发度为 1。

## M81.8 当前完成状态

- `tests/fixtures/m81_spatial_analysis_model.json` 已通过正常 LLM Planner 回放链路，精确匹配 `spatial_analysis` 9 步蓝图、结果引用和输出类型。
- Service preview 与开发 HTTP `/runs/preview` 的状态、计划、DAG、上下文证据、计划证据和安全门控逐字段一致；生产 FastAPI 路由和共享 `preview_kwargs` 有静态契约证据。
- 目标/相关回归 41 项、精简 `stage`、Python 编译和 `git diff --check` 通过。当前环境未安装 `fastapi`，没有宣称 production runtime acceptance。
- 当前 DeepSeek 配置为 `deepseek-v4-flash`、Chat Completions、`https://opencode.ai/zen/go/v1` 网关；`config/openai.local.json` 不含 key，当前进程没有 `OPENAI_API_KEY`，真实 live 需显式注入。

## M81.9 当前完成状态

已完成 `agent/plan_identity.py` 和 `preview_fingerprint` 执行前校验；preview 与执行结果共享 `spatial-agent.plan-identity.v1` fingerprint，不匹配时不 dispatch 工具。真实 DeepSeek 元数据请求和修复后的 9 步 `spatial_analysis` preview/执行均通过，相关回归 38 项通过。

当前宿主没有 `fastapi`，生产 FastAPI 仅有源码契约证据，运行时 acceptance 留到 M81.10。下一阶段先补生产依赖环境 acceptance，再把匹配状态接入 Console/artifact，并用真实 GIS backend 运行带 fingerprint 的 live-short。默认 quick/stage 离线，最大并发度为 1。


## M81.10 当前完成状态

生产 FastAPI acceptance 已补齐运行时证据：当前代码容器重建后通过 `/health/live`、`/health/ready`、runtime capabilities、真实数据卷、`/runs/preview`、带 `preview_fingerprint` 的 `/runs`、错误响应 envelope 和异步幂等验收。Console 已显示计划身份和预览匹配状态，预览后执行同一请求会自动携带 fingerprint。真实本地 GIS backend 的行政区边界 preview -> fingerprint -> execute 样例通过，artifact 和 GeoJSON 均导出；当前 DeepSeek-compatible 中转 smoke 通过，`raster_metadata_result`、3546 tokens、无重试。

发现并记录生产部署问题：`env_file` 不参与 Compose volume 变量插值，必须使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build` 或显式进程环境，否则 `/data` 会挂到仓库空目录。当前私有 `config/openai.local.json` 和 Windows 用户级环境变量保存中转 key，均不得提交；默认 quick/stage 仍离线。

## 下一阶段 M82

M82.1 已完成开放式能力发现的第一层接口：`CapabilityRouter.discover()` 输出版本化、JSON-safe 的 `spatial-agent.capability-discovery.v1`，Runtime 将 `capability_discovery` 注入 Planner 受信上下文，并在 `plan_evidence` / Console 运行证据中显示选中能力、候选能力、候选数量和信号。保持 `select()` 兼容，未改变现有 RuleBasedPlanner 路由行为。M77/M81 目标测试 27 项通过。

M82.2 已完成 Planner 能力目录摘要：`capability_context_summary()` 输出 `spatial-agent.capability-catalog-context.v1`，只展开候选能力范围内的能力目录、数据门控、后端支持、analysis-ready 摘要和工具参数形状；`ToolRegistry.definition_summary()` 暴露只读 schema 摘要，不暴露 handler 或绕过 Registry；Runtime factory 将 memory/local backend_name 注入 Runtime，`plan_evidence` 记录能力目录可用性、后端、能力 id 和工具 schema 数量。默认 `ContextBuilder` 预算提高到 12,000 字符。M59/M77/M81 目标测试 37 项通过（1 项因缺少 FastAPI 依赖跳过）。

M82.3 已完成 CLI/HTTP/artifact/session 跨入口 Harness：`run_demo.py` 改为复用 `AgentService.run()` 输出统一 payload，CLI 与 HTTP/Service 共享 `result` envelope、中文答案、`trace_summary`、`provenance`、`plan_evidence` 和可选 artifact 引用；新增 `--export-artifact`、`--artifact-root`、`--export-geojson`。M81 Harness 已覆盖 direct service、CLI、开发 HTTP、run detail、artifact fallback recovery、session history 和 Console 静态证据，断言 `capability_discovery`、`capability_catalog`、`workflow_templates`、`plan_identity`、trace、artifact 一致。复杂请求下能力目录详情收紧为“选中能力详情”，候选排序仍由 `capability_discovery` 提供。目标测试 18 项通过（1 项 GIS 跳过），M59/M77/M81 回归 38 项通过（1 项 FastAPI 跳过）。

M82.4 已完成生产入口 M82 证据门禁：`scripts/production_acceptance.ps1` 新增 `Assert-PlanningEvidence`，生产同步运行启用 `export_artifact=true`，并检查 `capability_discovery`、`capability_catalog`、选中能力、候选能力、能力目录后端和 plan identity 在 `plan_evidence`、`result.planning` 与 artifact 中一致。M66/M63/M81 目标测试 16 项通过（2 项 live Docker / FastAPI 跳过），PowerShell parser、quick、stage、编译和 diff check 通过。尚未启动 Docker production acceptance、真实 GIS 或 live LLM。

下一步从项目整体继续，不陷入单个区域或单个数据细节：进入真实数据降级矩阵，覆盖空数据卷、缺道路/水体、栅格未对齐、后端不可用、GeoJSON 截断，并把降级结果接入 result envelope / answer / trace 的一致性 Harness。当前最大并发度仍为 1；默认 quick/stage 离线，真实 GIS/Docker/live 模型只按显式验收运行。

M82.5 已完成结构化降级矩阵：`result_contract.py` 输出 `spatial-agent.degradation.v1`，在 `result.degradation` 与 `result.data.degradations` 中统一暴露运行状态、几何证据、工具错误、数据健康、analysis-ready、source binding 和 output manifest 限制。Artifact 保存 `result` 与顶层 `degradation`，artifact fallback recovery 能恢复同一矩阵；Console 优先读取后端矩阵，旧响应才走前端兼容推断；production acceptance 新增 `Assert-DegradationEvidence` 和 `sync_degradation_status`。

M82.5 验证：M76/M76.2.4/M81/M66 目标测试 26 项通过（1 项 live Docker acceptance 跳过），`production_acceptance.ps1` PowerShell parser 通过。抽样复杂内存综合空间分析为 `COMPLETED + result.degradation.status=degraded`，明确列出内存后端、DEM/土地利用像元、道路/水体几何和约束建设筛选限制。尚未运行 Docker production acceptance、真实 GIS 或 live LLM。

下一阶段先做全局盘点再规划 M83。优先考虑“结果类型与前端动态工作区”通用 contract，让 `result.type` 驱动可视化、表格、地图、证据和 artifact 展示，避免继续在页面里为单个空间请求写局部分支。

M83 已完成后端驱动的动态工作区契约：`result_contract.py` 输出 `spatial-agent.workspace.v1`，在 `result.workspace` 中声明 `result_type`、`registered_type`、`primary_panel`、`common_panels`、`panels` 和 `map` 证据；覆盖能力目录中的全部 `result_types`。Console 删除前端 result-type registry，不再按工具名推断面板，只把 workspace panel 名映射到 DOM 区域；工具结果只填充已选中的 panel。`renderRun` 去掉后置 monkey patch，栅格元数据面板现在能显示元数据摘要。production acceptance 新增 `Assert-WorkspaceEvidence` 和 `sync_workspace_panels`。

M83 验证：M46/M79/M81/M76 目标测试 29 项通过；M66 生产静态门禁 6 项通过（1 项 live Docker acceptance 跳过）；PowerShell parser、quick、stage 和 Python 编译通过，`git diff --check` 仅有 Windows LF/CRLF 提示。尚未运行 Docker production acceptance、真实 GIS 或 live LLM。

下一阶段 M84 建议继续全局规划，不陷入页面局部：把 panel 内部 metrics/table/chart/map payload 逐步变成后端 view model，减少前端继续扫描 `steps` 填内容；稳定后再做 Docker/GIS/live 小型 acceptance。

M84 已完成后端结果视图模型契约：`result_contract.py` 输出 `spatial-agent.views.v1`，在 `result.views.panels` 中统一给出栅格元数据、栅格统计、空间总览和地图预览所需的有界 view model。Console 的 raster/overview 面板改为消费 `resultViewPanels(data)` 和 `renderMetricGrid()`，不再扫描 `steps` 自行生成栅格/总览指标；栅格 bounds 预览也改用后端 map view。M46/M79 红测覆盖 `raster_metadata`、`raster_statistics`、`spatial_overview` 与 `raster_bounds/geojson` map view。

M84 验证：M46/M79 目标测试 15 项通过；M46/M79/M81/M76/M66 相关回归 37 项通过（1 项 live Docker acceptance 跳过）；Python 编译、quick、stage 和 `git diff --check` 通过，diff check 仅有 Windows LF/CRLF 提示。尚未运行 Docker production acceptance、真实 GIS 或 live LLM。

下一阶段 M85 需要先做全局盘点：优先把 health、composite、buildability、vector/table/chart 等剩余复杂面板继续下沉到 backend view model，并把 `views` 纳入 artifact、HTTP run detail、session recovery 和 production acceptance 证据。等 `workspace/degradation/planning/lineage/views` 五类 result envelope 证据稳定后，再做小型真实 GIS + live LLM + Docker acceptance。

M85 已完成复杂结果面板 view model 收敛：`result.views.panels` 扩展 `dataset_health`、`spatial_composite` 和 `buildability_screening`，把健康检查、综合分析和建设筛选的 metrics、rows、categories、coverage、note 下沉到后端 result contract。Console 的 `healthStats`、`compositeStats` 和 `buildabilityStats` 改为消费 `resultViewPanels(data)`，删除按工具名扫描 `steps` 的页面端业务聚合。`production_acceptance.ps1` 新增 `Assert-ViewEvidence`，同步响应和 artifact 都必须包含 `spatial-agent.views.v1`，且 view panel 不能越过 workspace 声明。

M85 验证：M46/M79 目标测试 16 项通过；M46/M79/M81/M76/M66 相关回归 38 项通过（1 项 live Docker acceptance 跳过）；Python 编译、quick、stage、production acceptance PowerShell parser 和 `git diff --check` 均通过，diff check 仅有 Windows LF/CRLF 提示。

下一阶段 M86 需要先做全局盘点：优先补 `views` 在 CLI/HTTP/artifact/run detail/session recovery/Console 的跨入口一致性 Harness，并评估 vector/table/chart 通用 view contract。真实 GIS、live LLM 和 Docker production acceptance 仍作为显式验收路径。

M86 已完成 `views` 跨入口一致性 Harness：`tests/test_m81_plan_evidence_acceptance.py` 的 `_normalized_contract()` 纳入 `result.views.schema_version`、view panel 集合和 panel kind，直接比较 direct service、HTTP `/runs`、HTTP run detail、CLI、artifact 和 artifact fallback recovery。红测发现 `AgentService.get_run()` 从 artifact fallback 恢复时会重新 `build_result_contract()`，在缺少完整 `steps` 时把 `views.panels` 重建为空；现已在恢复路径保留 artifact 中已有的 `result.views`，旧 artifact 仍可重建基础 envelope，新 artifact 不丢展示契约。

M86 验证：M81 目标 Harness 9 项通过。阶段收口还需运行 M46/M79/M81/M76/M66 相关回归、Python 编译、quick、stage、PowerShell parser、`git diff --check`，通过后提交推送。

下一阶段 M87 需要先做全局盘点：评估并设计 vector/table/chart 通用 view contract，让新结果类型优先扩展 result envelope，而不是继续增加页面 DOM 专用分支；同时考虑把 artifact viewer 也改为消费 `result.views`。

M87 已完成 artifact viewer 消费 `result.views`：`agent/artifact_viewer.py` 新增 `Result Views` 区块，从 artifact 的 `result.views.panels` 渲染 schema、panel 名、kind、metrics 和 note；旧 artifact 没有 views 时仍按原有 Plan / Tool Steps / Answer / Trace 展示。`tests/test_m17_artifact_viewer.py` 新增 views 渲染测试，M17 目标测试 3 项通过，`agent/artifact_viewer.py` Python 编译通过。

下一阶段 M88 需要先做全局盘点：优先设计 vector/table/chart 通用 view contract，补齐非栅格/非建设类结果的可复现展示 payload，并把该 contract 纳入 Console、artifact viewer、CLI/HTTP artifact 的一致性 Harness。

M88 已完成矢量结果 view contract：`result_contract.py` 在 `spatial-agent.views.v1` 下新增 `vector` panel，覆盖 `range_query`、`get_zonal_vector_summary` 和 `spatial_join` 三类矢量输出，统一生成 metrics、rows 和可选 table，且不内联原始几何。Console 的结构化结果区改为优先渲染 `resultViewPanels(data).vector`，支持 `vector_query`、`zonal_vector_summary` 和 `spatial_relation`；没有后端 vector view 时才回退 JSON。

M88 验证：M46/M79 目标测试 17 项通过；M17/M46/M79/M81/M76/M66 相关回归 42 项通过（1 项 live Docker acceptance 跳过）；Python 编译、quick、stage 和 production acceptance PowerShell parser 均通过。尚未运行 Docker production acceptance、真实 GIS 或 live LLM。

下一阶段 M89 需要先做全局盘点：继续把 table/chart 通用展示 payload 下沉到 `result.views`，补齐 artifact viewer 对 table payload 的渲染，并在 result envelope 稳定后做小型真实 GIS + live LLM + Docker acceptance。

M89 已完成 artifact viewer 的 rows/table view 渲染：`agent/artifact_viewer.py` 的 `Result Views` 区块通用渲染 view `rows` 和 `table` payload，保留 HTML escape、行列裁剪和自包含样式。新增 M17 测试覆盖矢量分类 table、rows 和 HTML escape。M17 目标测试 4 项通过；M17/M46/M79/M81 相关回归 30 项通过。

M89 验证：Python 编译、quick、stage、production acceptance PowerShell parser 和 `git diff --check` 均通过，diff check 仅有 Windows LF/CRLF 提示。尚未运行 Docker production acceptance、真实 GIS 或 live LLM。下一阶段规划要从全局 Agent Runtime 展示短板出发，在 chart view contract 与真实 GIS/live LLM/Docker 小型 acceptance 之间排序。

M90 已完成对比图 chart view contract：`result_contract.py` 新增 `build_comparison_views()`，阈值对比、多区域对比和道路距离约束对比统一返回 `spatial-agent.views.v1` 的 `chart` panel，包含 metrics、bar chart series、encodings、table 和 note。Console 的 comparison 面板优先渲染 `resultViewPanels(data).chart` / `renderChartView(view)`，旧 rows 表格仅作兼容 fallback；artifact viewer 同步渲染 `comparison_chart` series。M46/M57/M79/M17 目标测试 29 项通过；M17/M46/M57/M79/M81/M76/M66 相关回归 51 项通过（1 项 live Docker acceptance 跳过）。

M90 验证：Python 编译、quick、stage、production acceptance PowerShell parser 和 `git diff --check` 均通过，diff check 仅有 Windows LF/CRLF 提示。尚未运行 Docker production acceptance、真实 GIS 或 live LLM。下一阶段应优先做小型真实 GIS + live LLM + Docker acceptance，验证真实入口仍保持 planning/lineage/degradation/workspace/views 一致；MCP 只作为未来 ToolProvider adapter 方向，不替代 ToolRegistry 核心 seam。

## M91 当前完成状态

M91 已完成小型真实入口验收。Docker production 容器使用当前代码和 `.env.production` 重建后 healthy，`scripts/production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088` 通过；验收摘要为 liveness ok、readiness ready、runtime/data/core/optional health 均 ready、核心/可选缺失数据集为空、同步运行 `COMPLETED`、artifact 可用、异步运行 `COMPLETED`、重复提交幂等为 true。生产验收脚本修复了空 view panel 误判：`views.panels` 为空是合法状态，脚本现在过滤空属性名后只校验非空 view panel 是否由 workspace 声明。

真实本地 GIS 抽样通过：生产 `/runs` 请求 `查询洪山区行政区边界`（rule planner + local backend + artifact/GeoJSON）返回 `admin_area_result`，`geometry.available=true`、`feature_count=1`、`workspace.panels=[map]`，`views.panels.map.kind=map` 且 `mode=geojson`。真实 LLM 抽样通过：`planner=openai` 请求 `查询DEM栅格元数据` 返回 `COMPLETED`、`raster_metadata_result`、1 个工具步骤、`workspace.panels=[raster,map]`、`views.panels=[raster,map]`，不输出任何密钥或私有配置。

M91 验证：`tests.test_m66_data_volume` 6 项通过（1 项 live Docker acceptance 按门控跳过），production acceptance PowerShell parser 通过，Docker production acceptance 通过。PowerShell 直接写中文 JSON 请求体可能产生 mojibake，后续 CLI/生产手工验收优先使用 JSON unicode escape 或显式 UTF-8 body。

下一阶段 M92 需要从全局 Agent Runtime 视角规划工具管理深化：保留 ToolRegistry 作为核心执行 seam，抽象 `ToolProvider` 以支持内置工具和未来 MCP adapter；MCP 只能作为外部工具来源适配层接入 ToolRegistry/CapabilityCatalog/WorkflowTemplate，不能替代 schema 校验、dispatch、trace、degradation、workspace 和 views 契约。

## M92 当前进展

新增 `agent/tool_provider.py`：`ToolProvider` 是工具定义目录与 provider-specific invocation 的最小接口，`NativeToolProvider` 负责仓库 JSON schema 和进程内 adapter。`ToolRegistry` 新增 `from_provider()` 与 `provider_info()`，旧构造方式保持兼容；所有 provider 调用仍先经过 Registry 的 schema/参数校验，动态工具仍归 Registry 管理。

Runtime 的能力上下文和 `plan_evidence` 增加安全的 `tool_provider` 身份/工具数量证据；这让能力目录知道 schema 来源，但不把 provider handler 或原始连接信息暴露给 Planner、artifact 或前端。MCP 暂不实现为核心依赖，后续仅作为 `MCPToolProvider` adapter 候选。

M92 已完成验证：ToolProvider 专项 5 项、M59/M77/M81 相关回归 29 项、M30/M35/M66/M67/M79 相关回归 18 项通过；quick、stage 通过；离线全量 591 项通过、42 项按环境跳过；M69 多进程幂等测试连续复跑 5 次通过；Python 编译和 `git diff --check` 通过。GIS profile 的 3 项因当前普通 Python 环境缺少真实 GIS 依赖/数据而跳过，不能宣称 GIS 验收。

M92 当前部署复验受宿主环境阻塞：Docker CLI 无法连接 `dockerDesktopLinuxEngine` named pipe；`com.docker.service` 虽显示存在但为 Stopped，启动时报无法打开 service handle。不能把 M91 旧容器响应当作 M92 当前代码证据。离线 provider 契约、quick/stage 可作为当前阶段证据，Docker acceptance 需环境恢复后重跑。

下一阶段 M93 先从全局 Runtime 盘点 provider 健康、权限/数据依赖、超时/错误分类、trace/metrics 和 HTTP/artifact/recovery 一致性，再决定是否实现真实 `MCPToolProvider`；没有真实外部工具来源时不引入 MCP 依赖。

## M94 当前完成状态

- `runtime_capability_snapshot()` 和 `/capabilities/runtime` 暴露有界 `tool_provider`、`tool_provider_health`、`tool_governance`，不执行业务工具；生产 acceptance 已增加对应 schema、状态和 tool count 门禁。
- `ToolRegistry.governance_for()`、`timeout_seconds()`、`data_dependencies()` 成为 Runtime 消费工具治理的唯一 seam；权限、审批、严格依赖证据和不可用数据均在 dispatch 前门控，并保留机器可读错误分类。
- Registry 已真正执行声明的 per-tool timeout；run-level timeout 仍为协作式步骤边界控制，避免影响既有取消/超时状态机。12 个内置工具 schema 均声明 timeout。
- M94 专项 8 项、M92/M93 provider 回归 11 项、M37/M60/M81 contract 共 22 项通过；stage 通过；离线全量 605 项、42 项按环境跳过；编译、schema、PowerShell 静态门禁、diff check 通过。
- 普通 Python 环境未执行真实 GIS profile；Docker Linux engine 仍不可用，不能把旧容器 acceptance 作为 M94 当前版本证据。

### M95 全局重规划入口

下一阶段先盘点 RequestFacts、CapabilityCatalog、WorkflowTemplate、ToolRegistry governance、Result envelope、trace/artifact 和 HTTP 配置的重复约束，建立“规划约束 -> 执行门控 -> 结果证据”一致性矩阵，再决定应收敛哪个公共契约。没有真实远程工具来源时不引入 MCP 运行时依赖；如未来出现远程 GIS/数据库/第三方工具，仅实现满足现有 Registry contract 的 `MCPToolProvider` adapter。当前最大并发度为 1。

## M95 已完成

- `agent.request_model.RequestFacts` 输出 `spatial-agent.request-facts.v1`，`SpatialRequest` 保留为兼容别名。Runtime 在规划前一次性抽取 facts，preview、`AgentRunResult`、result envelope、SQLite 和 artifact 均保留无原文的安全 projection。
- `ToolRegistry.governance_for()` 作为治理读取唯一 seam；plan evidence 增加 `spatial-agent.execution-policy.v1`，实际 StepRun 保存同一权限/数据依赖/审批/timeout 快照，result evidence、artifact 和 SQLite recovery 复用它；step observability 保留安全错误码。
- M95 专项 3 项通过；M81 跨入口 normalization 已覆盖 direct/HTTP/CLI/artifact/recovery 的 RequestFacts、execution policy 和 StepRun governance 一致性。quick、stage 和离线全量通过：608 项通过、42 项按环境跳过；Python 编译、PowerShell acceptance 解析和 diff check 通过。
- 生产 acceptance 已加入版本化 RequestFacts、execution policy 及 artifact 证据门禁。本轮未执行真实 GIS、Docker production acceptance 或 live LLM，不能把旧容器或按环境跳过当作当前版本证据。

下一步：完成阶段提交后，从全局 Agent Runtime 角度重新评估真实环境验收、失败修复/重规划、契约演进和外部工具 adapter 的优先级。MCP 仍只作为未来真实外部工具来源的 adapter。

## M96 已完成

- `ToolRegistry` 接入 provider 时统一调用 `validate_tool_definitions()`，校验工具名、目录 key、object schema、治理字段和 timeout；新增 `spatial-agent.tool-provider-contract.v1`。
- provider health、runtime capability 和 plan evidence 暴露有界定义合同；非 Native provider 回放验证外部工具来源仍受权限、schema、timeout、StepRun governance 和结果契约约束。
- M96 专项 4 项、M92–M95 回归 26 项、quick/stage、离线全量 612 项通过、42 项按环境跳过；编译、PowerShell acceptance 解析和 diff check 通过；真实 GIS core 3 项通过。
- Docker Linux engine 仍不可用，未宣称 M96 Docker production acceptance；live LLM 仍按环境门控。MCP 继续保持未来真实远程工具来源的 adapter，而不是当前依赖。

下一步：先从全局七维矩阵安排当前版本真实入口/部署复验和失败重规划组合验收，再根据是否出现真实外部工具来源决定 MCP adapter；不得为使用 MCP 而改变 ToolRegistry 核心 seam。

## M97 已完成

- 新增 `agent/failure_contract.py` 与 `spatial-agent.failure.v1`，Runtime 运行级失败证据统一记录 status、category、code、phase、retryable，原始错误仍只保留在兼容的人读字段中。
- 失败证据已贯通 result envelope、HTTP/service、artifact、SQLite recovery；生产 acceptance 有预览指纹不匹配的失败样例门禁。
- M97 专项 4 项通过；离线全量 616 项通过、42 项按环境跳过；quick/stage、GIS core、编译、PowerShell 解析和 diff check 通过。本阶段已准备提交推送。

下一步：完成阶段推送后，从全局七维矩阵重新评估 Docker/真实模型验收、计划修复与动态能力扩展；Docker Linux engine 恢复后再执行当前版本 production acceptance。MCP 继续保持未来真实远程工具来源的 adapter。

## M98 已完成

- observability run event 已增加安全的 `error_code`、`failure_phase`、`failure_retryable`；异步 worker 异常及 SQLite 恢复保持同一 failure evidence。
- Console 通过通用 `failureEvidenceBadge()` 消费顶层或 result envelope 的 `spatial-agent.failure.v1`，显示阶段、错误码和可重试性。
- M98 专项 3 项、M80 observability 回归 6 项、Console 回归 2 项通过；离线全量 620 项通过、42 项按环境跳过；quick、stage、GIS core、编译、PowerShell 解析和 diff check 通过。Docker Linux engine 仍不可用，不能宣称真实容器验收。

下一步：先完成 M98 最终验收和推送，再从全局七维矩阵安排真实 Docker/LLM/GIS 入口或脱敏模型计划修复回放。MCP 继续保持未来真实远程工具来源的 adapter。

## M99 已完成

新增 `spatial-agent.replanning.v1`，统一 `result.replanning`、`result.lineage.replanning`、trace 和 Console 消费；顶层 `replan_events` 保持兼容。M99 专项回归 36 项、离线全量 624 项（42 项按环境跳过）、真实 GIS core 31 项、真实模型 planner smoke 和显式绑定武汉分析就绪配置的 live GIS 总览均通过。Docker Linux engine 仍无法连接，不能宣称当前版本 production acceptance。下一阶段 M100 先从全局七维矩阵安排 Docker/真实入口复验；没有真实外部工具来源时不引入 MCP 运行时依赖。

## M100 已完成

`scripts/test_profile.py` 的本地 `live-short` 现在强制要求显式数据配置，避免真实 GIS 测试静默回退到示例 catalog。M100 profile 回归 8 项、离线全量 625 项（42 项按环境跳过）通过；M99 的真实 GIS/live 验收证据保持通过。Docker Linux engine 仍无法连接，下一阶段 M101 优先复验当前版本的 Docker/HTTP/SQLite/artifact/Console 部署链路；没有真实外部工具来源时不引入 MCP 运行时依赖。

## M101 已完成

生产 acceptance 已新增 `Assert-ReplanningEvidence`，同步结果与 artifact 校验 `spatial-agent.replanning.v1`、事件边界和 lineage 计数一致。full-stage、strict offline evaluation、smoke、PowerShell 解析和离线全量 625 项（42 项按环境跳过）通过；M101 相关回归 10 项通过。Docker Linux engine 仍无法连接，下一阶段 M102 优先用当前版本重建容器并复验 readiness、真实数据卷和跨入口证据；没有真实外部工具来源时不引入 MCP 运行时依赖。

## M102 已完成

`result_contract.py` 现在兼容顶层 `replan_events` 与旧/外部 artifact 的嵌套 `result.replanning.events`，并继续统一有界归一化。M102 相关回归 30 项、离线全量 627 项（42 项按环境跳过）和 GIS core 31 项通过。Docker Linux engine 仍无法连接，下一阶段 M103 优先重建当前版本容器并验收 readiness、真实数据卷及 HTTP/artifact/recovery/Console；没有真实外部工具来源时不引入 MCP 运行时依赖。

## M103 已完成

- 当前版本离线全量 627 项通过、42 项按环境跳过；quick、stage、smoke、Python 编译和 `git diff --check` 通过。
- GIS core 抽样 3/3 通过；显式绑定武汉 analysis-ready 数据配置的真实模型 + 本地 GIS `live-short` 2/2 通过，0 次重试，安全记录 token 总量 11,546，不记录密钥或模型原始响应。
- 本地 HTTP 入口已验证健康、runtime capability、同步/异步、artifact 和统一 result envelope；`result.type`、`result.views`、`result.workspace` 与重规划证据保持在同一结果契约中。
- Docker Linux engine 仍因 `dockerDesktopLinuxEngine` named pipe 不存在无法启动，因此没有宣称当前版本 Docker/FastAPI production acceptance。隔离 Chrome CDP headless 进程退出码 13，本轮动态浏览器 smoke 未记为通过；静态前端契约和既有浏览器测试仍通过。

下一阶段 M104 从全局角度优先做当前版本 Docker/FastAPI 生产复验和跨入口结果契约矩阵，再深化开放式请求理解、数据 provenance、真实模型回放和动态前端证据。ToolRegistry 继续作为唯一执行 seam；没有真实远程工具来源时不引入 MCP 运行时依赖。

## M93 当前完成状态

M93 已完成 provider 治理基础闭环：`NativeToolProvider.health()`、`ToolRegistry.provider_health()`、`ToolRegistry.governance_summary()` 和 `ToolProviderError` 已接入。内置 12 个工具的 schema 声明了 `spatial_data:read` 权限和数据依赖；provider 错误的 category/code/retryable 会安全保留在步骤、SQLite/artifact、result envelope 和 observability 中。Planner 上下文与 plan evidence 记录 provider health/governance，治理细节通过选中工具 schema 传递。

M93 还将默认 ContextBuilder 预算提高到 16,000 字符，并调整裁剪优先级，复杂请求不再因治理摘要丢失 `capability_discovery`、`capability_catalog` 或 `workflow_templates`。M93 专项 6 项、M92/M81 相关回归 14 项通过；离线全量 597 项通过、42 项按环境跳过；quick、stage、编译和 diff check 通过。

M93 的 GIS profile 在当前普通 Python 环境下按依赖条件跳过；Docker Linux engine 仍无法连接，不能把 M91 旧容器作为当前版本生产证据。下一阶段 M94 先做 provider health/runtime capability、权限/数据依赖实际门控和 per-tool timeout 的全局规划，再决定是否引入真实 MCP adapter。

## M104 已完成

- GitHub Actions 已从只运行 `smoke_check.py` 扩展为服务 smoke、stage 契约 profile 和完整离线 unittest 回归。
- 本地等价验证通过：smoke、stage 和离线 627 项通过、42 项按环境跳过；CI 不依赖真实模型、私有配置、原始 GIS 数据或 Docker。
- 当前阶段没有改变 Runtime/HTTP 运行时语义；Docker/FastAPI production acceptance 和动态浏览器 CDP 仍按宿主条件单独验收，不能用 CI 结果替代。

下一阶段 M105 从全局角度优先做 Docker/FastAPI 生产矩阵、开放式请求回放和动态前端证据；ToolRegistry 继续作为唯一执行 seam，没有真实远程工具来源时不引入 MCP 运行时依赖。

## M105 已完成

- 新增脱敏 `open_region_query` 回放，使用江夏区边界请求验证同一能力目录、TaskPlan、工具 DAG 和结果类型，不增加区域专用规则。
- `RequestFacts` 跨区域参数、result envelope 和计划参数一致性测试已补齐；结构化空间澄清、Console 规划证据和 HTTP/artifact/recovery 回归继续通过。
- 回放套件 3/3、M105 相关回归通过；full-stage、严格离线评测和离线全量 628 项通过、42 项按环境跳过。
- Docker Linux engine named pipe 和隔离 Chrome CDP 退出码 13 的宿主限制仍未解决，当前版本真实 FastAPI/Docker 与动态浏览器证据不能宣称通过。

下一阶段 M106 从全局角度优先做生产入口矩阵、非固定表达的开放式空间请求基线、真实数据证据边界和动态 Console 验收；ToolRegistry 继续是唯一执行 seam，没有真实外部工具来源时不引入 MCP。

## M106 已完成

- 真实模型 + 武汉本地 GIS 通过 `AgentService` 完成非固定表达“查询江夏区道路与水体分布”：`zonal_vector_summary_result`、5 个工具步骤、vector workspace/views、道路 10,051 个、水体 1,189 个、0 次重试。
- 该请求未使用空间总览或建设筛选固定模板，仍通过同一 Planner、ToolRegistry 和 Service result formatting；内部 Runtime 原始对象与外部 result envelope 的边界已记录。
- Docker Linux engine named pipe 和隔离 Chrome CDP 退出码 13 的宿主限制保持未解决，当前版本 FastAPI/Docker 与动态浏览器证据不能宣称通过。

下一阶段 M107 从全局角度优先做生产入口矩阵、更多开放式表达/未注册能力澄清、真实数据证据边界和动态 Console 验收；没有真实远程工具来源时不引入 MCP 运行时依赖。

## M107 已完成

- GitHub Actions 失败步骤已通过 run/job 元数据定位为 `Run stage contract profile`；smoke 成功，离线 unittest 因前一步失败而跳过。原始 Actions 日志读取返回 403，未把摘要当作完整堆栈。
- 修复 CI harness 的 Windows 编码边界：profile 子进程显式使用 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` 和 UTF-8 捕获；workflow job 同样声明环境；新增中文子进程输出回归。
- 本地验证：smoke 通过、stage 通过、离线全量 629 项通过、42 项按环境跳过。stage profile 继续作为代表性契约门禁保留。

### M108 全局规划

1. 以跨入口 Contract Harness 统一 CLI、HTTP、artifact、recovery 和 Console 的稳定结果证据，避免各入口复制 envelope 投影。
2. Docker engine 恢复后执行当前版本 FastAPI/readiness、SQLite 多 worker、artifact/recovery 和真实数据卷验收。
3. 从整体 Agent Runtime 盘点开放式能力组合、真实模型回放、数据质量和动态 Console 证据；无真实外部工具来源时不引入 MCP 运行时依赖。

## M108 当前进展

- 新增 `evaluation/contract_harness.py`，统一 CLI、HTTP、artifact 和 recovery 的稳定结果投影、等价比较及有界差异路径。
- M81 复杂空间分析跨入口回归已改用 Harness；新增 M108 专项 4 项，连同既有跨入口验收共 13 项通过。
- 修复异步服务在 Runtime 中间 `COMPLETED` 快照与 artifact/GeoJSON 最终引用之间的轮询竞态；50 次 targeted loop 全部通过。
- Docker Linux engine 仍不可用；FastAPI/Docker production acceptance 和动态浏览器 smoke 继续保持未宣称状态。

## M109 已完成

- 新增脱敏 `open_capability_query` 回放，使用“请概括江夏区的道路和水体分布”验证非固定模板的开放式多工具能力。计划包含道路/水体 schema 与分区矢量汇总两个 DAG 分支，结果类型为 `zonal_vector_summary_result`。
- M109 回放 4/4、full-stage 和离线全量 634 项通过、42 项按环境跳过；没有访问真实模型、私有配置或原始 GIS 数据。
- 该回放仅是通用能力的离线证据，不替代真实 GIS、Docker 或动态浏览器验收；Docker Linux engine 和动态 Chrome CDP 的宿主限制仍未解决。

## 下一步

1. Docker engine 恢复后重建当前版本，完成 FastAPI/readiness、真实数据卷、SQLite 多 worker、artifact/recovery 和跨入口 acceptance。
2. 从全局 Agent Runtime 角度扩展结构化澄清、能力发现和受控失败修复，继续复用 RequestFacts、CapabilityCatalog、WorkflowTemplate、ToolRegistry 和 Result contract。
3. 恢复可控浏览器后验收动态 workspace、views、地图、轨迹和会话清空；没有真实远程工具来源时不引入 MCP 运行时依赖。

## M110 已完成

- 新增 `scripts/contract_harness_check.py`，生产 `production_acceptance.ps1` 通过同一 `evaluation/contract_harness.py` 比较同步运行结果与 artifact 的稳定契约。
- 新增等价、差异、真实 Service/artifact 和生产脚本调用回归；PowerShell parser、full-stage 和离线全量 638 项通过、42 项跳过。
- M110 记录了跨语言边界：直接执行 scripts 下的 Python 文件需显式加入仓库根目录；PowerShell JSON 数组需使用 `ConvertTo-Json -InputObject` 并固定 UTF-8。
- Docker Linux engine 仍无法连接 `dockerDesktopLinuxEngine` named pipe；当前版本 FastAPI/Docker production acceptance 和动态浏览器 smoke 未宣称通过。

## M111 下一步

1. Docker engine 恢复后重建当前版本，执行 readiness、真实数据卷、同步/异步、SQLite 重启恢复和 production acceptance。
2. 从全局 Agent Runtime 角度扩展结构化澄清、能力发现和受控失败修复，不增加区域专用分支。
3. 恢复可控浏览器后完成动态 workspace、views、地图、轨迹和会话清空验收；无真实远程工具来源时不引入 MCP 运行时依赖。

## M111 已完成

- `agent/spatial_intent.py` 的结构化澄清现在输出 `spatial-agent.clarification.v1`、CapabilityCatalog 中文标签、匹配/候选能力详情和有界下一步动作。
- 修复分类结果到最终 clarification 的字段丢失；Service、HTTP、result envelope 和开放式计划预览回归通过。
- Docker Linux engine 仍无法连接 `dockerDesktopLinuxEngine` named pipe；真实 FastAPI/Docker 和动态浏览器验收继续保持未宣称状态。

## M112 已完成

- 已新增 `DomainPack` seam，Runtime、runtime factory 和 planner context 可由领域包提供 catalog、discovery 和 workflow context；默认 GIS 行为保持兼容。
- GIS 数据集名称、工具映射、能力定义、数据分组、GIS discovery 和 workflow context 已迁入 `domains/gis`；公共 catalog 构造器已参数化，旧 GIS 常量只保留兼容别名。
- 非 GIS fake pack 与非 GIS catalog builder 回归通过，证明 Runtime 不需要知道 `dem`、`land_use`、`roads`、`water` 或洪山区。
- M112 专项 3 项和 `full-stage` 通过，编译/diff check 通过；M69 三 worker SQLite 用例单独连续 20 次通过。完整离线套件偶发同一既有 SQLite 并发用例，按开发问题记录处理，不能作为 M112 领域解耦失败。

### 当前真实边界

项目仍是“通用 Agent Runtime + GIS Domain Pack”，不是已经支持任意领域的成品平台。结果 composer、data quality、部分 workflow/result view 和 production capability endpoint 仍包含 GIS 语义；下一阶段必须按全局七维矩阵继续识别并收敛这些领域泄漏，再补独立 adapter/replay。

### M113 下一步

1. 跨领域 contract/replay：验证非 GIS adapter 也能经过同一 RequestFacts、TaskPlan、ToolRegistry、result envelope、trace 和 artifact。
2. 领域泄漏审查：检查 workflow、result views、provenance、failure/replanning、HTTP capability endpoint 是否需要 Domain Pack 化。
3. 真实环境验收：Docker 恢复后复验 GIS Domain Pack 的 HTTP、SQLite、artifact、地图和 live model；保持 CI 离线。
4. MCP 仍只作为未来真实外部工具来源的 ToolProvider adapter，不进入核心 Runtime。

## 当前进度：M113 已完成

- 当前版本已用 `domains/text` 验证最小非 GIS Domain Pack 闭环：请求事实提取、能力发现、TaskPlan、ToolRegistry schema/dispatch、Runtime、Service、result envelope 和 artifact。
- `AgentService(runtime_factory=...)` 是非 GIS 入口复用的注入 seam；`result_contract` 可输出 `text_summary_result` 和 generic workspace。
- planning evidence 已包含通用 `domain_id`，不依赖 GIS 字段；M113 专项 3 项、M112 回归 3 项、full-stage、离线全量 646 项（42 项按环境跳过）、compileall、diff check 通过。

## 下一阶段 M114

进行全局领域泄漏审计：优先检查 HTTP/runtime capability 快照、结果 views/workspace、provenance、failure/replanning 和前端动态渲染，继续将 GIS 语义保留在 `domains/gis`，并补跨领域契约测试。Docker/真实数据/真实模型仍是可选验收路径，默认 CI 不依赖它们。

## 当前进度：M114 已完成

- Runtime 的默认 answer composer 与默认权限由 Domain Pack 提供；GIS 与 Text 均有各自实现，Text Runtime 不再显式注入这些领域细节。
- 公共结果契约不再为 `text_summary_result` 写专用标题，计划 output metadata 可直接驱动标题，generic workspace 仍作为未知类型的安全降级。
- M114 定向 17 项、full-stage、离线全量 646 项（42 项按环境跳过）、compileall、diff check 通过。
- 尚存 GIS 领域泄漏：result view/panel 注册、生产 capability endpoint、provenance/data-health；下一阶段 M115 处理这些公共边界。

## 下一阶段 M115

优先建立 Domain Pack 驱动的 result type/view 注册契约，并让 HTTP capability snapshot 复用实际 Runtime；随后补 provenance/failure/replanning/前端的跨领域契约测试。继续保持最大并发度 1，真实 Docker/GIS 作为显式验收路径。

## 当前进度：M115 已完成

- `ResultContractRegistry`/`ResultTypeSpec` 已成为 Domain Pack 的结果 metadata seam；GIS 和 Text 分别提供自己的 result type/title/panel 注册。
- Runtime、Service、重试、运行详情和 artifact 构建统一使用选定 registry；旧 Runtime 没有 registry 方法时使用兼容 fallback。
- M115 定向 16 项、full-stage、离线全量 646 项（42 项按环境跳过）、compileall、diff check 通过。

## 下一阶段 M116

改造 HTTP capability snapshot，使其通过实际 Runtime/Domain Pack 提供目录；补 Text/GIS 双入口契约测试，并将 GIS 数据健康限制在可选领域证据层。最大并发度保持 1。

## 当前进度：M116 已完成

- 普通 `/capabilities` 已经通过 `Service -> Runtime -> Domain Pack` 获取目录；开发 HTTP 与生产 FastAPI 不再直接依赖公共 GIS catalog。
- Text Domain Pack 的 Service/HTTP 目录返回只包含 `text_summary`，跨入口回归通过；GIS `/capabilities/runtime` 数据健康路径暂保持兼容并等待独立抽象。
- M116 定向 18 项、full-stage、离线全量回归、compileall、diff check 通过。

## 下一阶段 M117

抽象 runtime capability snapshot：通用 provider/tool governance 由 Runtime 提供，GIS 数据健康/覆盖/provenance 作为 Domain Pack 可选 evidence；补 production/development HTTP 双领域契约测试。

## 当前进度：M117 已完成

- Runtime/Service 已提供通用 runtime capability snapshot，包含 domain、backend、provider health、tool governance 和 bounded metadata。
- Domain Pack 可选实现 runtime evidence；Text 已验证 `not_applicable`，旧 GIS runtime snapshot 兼容保留，HTTP endpoint 迁移留给 M118。
- M117 定向 25 项、full-stage、离线全量回归、compileall、diff check 通过。

## 下一阶段 M118

迁移 `/capabilities/runtime` 到新 Service/Runtime seam，并将 GIS 数据健康、manifest、对齐和 provenance 作为领域证据注入；同时补开发 HTTP/生产 FastAPI 的双领域契约测试。

## 当前进度：M118 已完成

- HTTP runtime snapshot 已通过 Service/Runtime/Domain Pack seam 运行；GIS 数据 evidence 和 Text `not_applicable` evidence 均可进入同一返回结构。
- 旧 snapshot provider 名称保留为兼容包装，隔离测试的 `service=None` 路径不影响正常请求；M118 定向 23 项、full-stage、离线全量回归、compileall、diff check 通过。
- FastAPI 依赖未安装，生产专用用例按环境跳过，不能把本阶段开发 HTTP 结果宣称为生产验收。

## 下一阶段 M119

从全局证据链审计 release evidence、provenance、failure/replanning 和前端动态消费，拆分通用/GIS evidence；Docker/FastAPI 恢复后做真实生产矩阵。

## 当前进度：M119 已完成

- 几何降级判断已由 `ResultTypeSpec.requires_geometry` 驱动，公共结果模块不再维护独立 GIS result type 集合。
- provenance 已版本化并记录 `domain_id`/有界通用计数；failure/replanning 维持领域无关。
- M119 相关回归、full-stage、离线全量 650 项（42 项按环境跳过）、compileall、diff check 通过。
- 尚存边界：result view builder 仍识别部分 GIS tool/type，provenance 仍保留旧 GIS 字段用于兼容。

## 下一阶段 M120

建立 Domain Pack view builder registry，并将 provenance GIS 字段转成可选领域 evidence；补前端 Text/GIS 动态结果契约后再做真实环境矩阵。

## 当前进度：M120 已完成

- Result registry 已控制 view builder 调用：GIS 保留既有 view 算法，Text 不触发 GIS builder，generic views 可正常输出。
- M120 定向 25 项、full-stage、离线全量 650 项（42 项按环境跳过）、compileall、diff check 通过。
- 下一步继续移动 GIS view 实现和 provenance 兼容字段，保持前端只消费结构化结果。

## 下一阶段 M121

将 GIS view builder 下沉到 `domains/gis`，清理公共结果模块中的 GIS 实现依赖；补 provenance projection 与前端 Text/GIS smoke。

## 当前进度：M121 已完成

- provenance projector 已下沉到 Result registry：Text 使用通用安全摘要，GIS 保留兼容领域字段。
- M121 定向回归、full-stage、离线全量 651 项（42 项按环境跳过）、compileall、diff check 通过。
- 公共结果模块仍保留 GIS view 实现本体，下一阶段进行物理迁移并补前端 generic views smoke。

## 下一阶段 M122

移动 GIS view builder 实现到 `domains/gis`，让前端完全以结构化 result views/workspace 驱动，并在真实依赖可用后执行生产验收矩阵。

## 当前进度：M122 已完成

- `domains/gis/views.py` 现在拥有 GIS raster、overview、health、composite、buildability、vector 和 map view builder；`domains/gis/result_registry.py` 直接通过 `ResultContractRegistry` 注册。
- 公共 `result_contract.py` 只保留通用 envelope、workspace/geometry evidence、lineage、comparison views 和通用 view primitive；不再定义 GIS `_view_model`/面板实现。
- `tests/test_m122_domain_views.py` 覆盖 GIS view 物理归属和 Text generic Console smoke；Text 结果的 workspace 只有 `generic`，views 为空，不需要前端领域分支。
- 当前验证：离线全量 653 项通过、42 项按环境跳过；quick、full-stage、compileall、`git diff --check` 通过。
- FastAPI、Docker、真实 GIS 数据和 live LLM 未因本阶段离线通过而被宣称完成；仍需在对应宿主环境执行生产矩阵。

## 当前 M123 全局规划

1. 审计前端静态 GIS controls、比较接口和 GIS 兼容 fallback，保留 GIS Domain Pack 深度但继续缩小公共层领域知识。
2. 增加 Domain-owned view metadata/renderer seam，前端只依据结构化 view kind/schema/metadata 渲染。
3. 用第二个非 GIS Domain Pack 回放验证 Service、HTTP、artifact、Console generic 结果一致性，并接入 Contract Harness。
4. Docker/FastAPI/真实模型/真实数据可用后执行跨入口生产验收；数据集只能作为领域证据，不能成为公共 Runtime 分支。

## 当前进度：M123 已完成

- `agent/result_registry.py` 新增有界 `ViewSpec`；`result.workspace.view_specs` 和 capability context 统一暴露 Domain-owned renderer metadata。
- GIS registry 声明各类 view 的通用 renderer；Console 对未知 panel id 使用 generic metrics/table/chart renderer，不要求新增 GIS 页面分支。
- 前端已移除 `needsRaster`、固定 GIS 数据集关键词和本地 GIS 发送前预判，具体能力、依赖与降级由 Service/Runtime 决定。
- 当前验证：离线全量 654 项通过、42 项按环境跳过；quick/full-stage、Node 内联脚本语法、compileall、`git diff --check` 通过。
- M123 初次全量中既有 SQLite 多 worker 用例出现一次抖动；单用例重跑和整套重跑均通过。该宿主并发问题仍按既有问题处理，不能归因于 view metadata 改动。
- Docker、FastAPI、真实 GIS 数据和 live LLM 仍未完成本轮生产验收。

## 当前 M124 全局规划

1. 将 GIS comparison endpoints/Console controls 收敛为 Domain-owned action metadata，公共层只处理通用 action contract。
2. 增加第二个完整非 GIS Domain Pack replay，跨 Service、HTTP、artifact、recovery、generic Console 和 Contract Harness 验证。
3. 复验能力快照、数据质量降级、SQLite 恢复以及 Docker/FastAPI/真实数据/真实模型生产路径。
4. 继续以全局产品、架构、数据、模型、部署、前端和测试证据重规划，不因单一数据集细节改变公共 Runtime 方向。

## M124 收尾状态

- M124 已完成。`DomainActionSpec` 和 Domain-owned action catalog/dispatch 已接入 Runtime、Service、开发 HTTP、生产 FastAPI；GIS comparison 动作已从旧路径收敛到 `domains/gis/actions.py`。
- Console 已先读取 `/actions`，再调用通用 `/actions/{action_id}`；旧 GIS comparison 路由仍保留兼容，但不再被前端主流程调用。
- Text Domain Pack 已完成 HTTP、artifact、recovery、generic Console 和 Contract Harness replay；其 action catalog 为空，能力目录和 workspace 不泄漏 GIS action。
- M124 专项与 Console 回归 24 项通过；离线全量 659 项通过、42 项按环境跳过；Node 内联脚本、`git diff --check` 通过。
- 当前未完成的整体问题仍是公共 `agent/` 中的 GIS 兼容实现、GIS 数据健康/analysis-ready 规则和答案组合；它们应在 M125 继续下沉到 Domain provider，不应通过新增区域或数据集分支解决。

## M125 全局规划

1. 公共 Runtime 领域解耦：收口 answer composer、数据健康、analysis-ready、provenance/release evidence 的 Domain seam，保持显式 GIS bootstrap 和旧 artifact 兼容。
2. Action 工程契约：增加 bounded input schema 校验、结构化错误、trace/observability、artifact/recovery 一致性，禁止任意 Service 反射 dispatch。
3. Console 与部署：能力/action/view/evidence 全部消费 Runtime snapshot；验证非 GIS pack 的 HTTP、生产入口、SQLite、artifact 和前端 generic path。
4. 全局验收：覆盖产品闭环、架构替换、真实数据降级、真实模型可选 live、部署可靠性、前端体验和离线 CI；保持最大并发度 1。

## M125.1 收尾状态

- `agent/runtime.py` 已移除 GIS 数据预检规则，新增 `DomainPack.preflight_tool()` seam；GIS 健康、网格对齐和数据不可用门控位于 `domains/gis/preflight.py`。
- Domain action dispatch 已增加 bounded input schema 校验，catalog 继续只暴露有界 schema，执行继续要求显式 Domain-owned action。
- M125.1 领域预检、Action schema、M69 对齐门控、M94 治理和 M124 回归通过；离线全量 662 项通过、42 项按环境跳过；compileall、quick/full-stage、diff check 通过。
- 尚未完成：`agent/answer_composer.py` 的物理迁移、GIS data-quality/analysis-ready legacy provider 与 release evidence 的进一步收口，以及 Action 的结构化错误/观测/artifact 证据。

## M125.2 规划

先完成 GIS composer/provider 的物理归属和兼容测试，再把 Action 错误、trace、artifact/recovery 纳入统一结果契约；随后复验第二非 GIS Domain Pack、生产 HTTP/FastAPI、Docker、真实数据和可选真实模型路径。

## M125.2 收尾状态

- GIS Composer 已迁移到 `domains/gis/composer.py`，`agent/answer_composer.py` 仅为兼容 shim；归属测试和旧导入回归通过。
- Action 执行返回 `domain_id` 与 `spatial-agent.action-execution.v1`，包含输入已校验、完成状态和有界耗时；结构化 ActionContractError 暴露 `action_id` 与 `action_error_code`。
- Composer、Action、HTTP 与既有 Domain/治理回归 25 项通过；最近一次迁移后的全量离线 663 项通过、42 项按环境跳过；compileall、quick/full-stage、Node 页面语法、diff check 通过。
- 用户已要求后续阶段合并更多纵向任务、减少重复测试：开发期只做必要专项，阶段末统一专项+全量；当前最大并发度仍为 1。

## M126 全局规划

1. 继续迁移 GIS data-quality、analysis-ready、release evidence provider，保留有界 HTTP/旧 artifact 兼容。
2. 将 Action execution evidence 接入统一 trace/result/artifact，并用第二个非 GIS Domain Pack 回放成功、校验失败和恢复读取路径。
3. 全局复验 Console、FastAPI、Docker、真实数据、可选真实模型、部署和降级证据；完成阶段后再统一运行测试矩阵并推送版本。

## M126 收尾状态

- 领域证据已扩展为 `DomainPack.release_evidence()`；正常 Runtime/Service/HTTP 路径只消费当前领域 provider。GIS 的既有 data-quality、analysis-ready、manifest 和 release 实现由 `domains/gis/evidence.py` 适配，旧 `agent/` provider 保留给兼容脚本/隔离测试。
- Action 已形成统一的执行证据、trace、result envelope、artifact 和 recovery seam。成功与 schema 校验失败均可通过 action artifact 读取；普通 run 列表和运行指标会排除 action artifact。
- Text Domain Pack 提供 `text.summarize` 作为第二个非 GIS action，已覆盖 Service、开发 HTTP、artifact/recovery、runtime/release evidence 和 GIS 语义隔离。
- M126 开发期只执行编译、diff check 和必要专项；阶段收尾统一执行一次 M126/M125 代表性专项和一次离线全量回归。Docker、FastAPI、真实 GIS 与 live LLM 仍是环境条件验收，不能用离线测试代替。

## 当前执行节奏

每阶段合并更多相互依赖的纵向任务：同一阶段同时处理架构 seam、跨入口契约、可替换领域回放、部署影响和中文文档。开发中不重复运行长时间全量套件；只在接口发生变化时做必要专项，阶段结束集中测试、记录证据、提交并推送版本，再以产品、架构、数据、模型、部署、体验和测试七维度进行整体重规划。最大并发度保持 1。

## M127 已完成：Evidence Provider 与 Action 可恢复闭环

- 已实现 `spatial-agent.domain-evidence.v1` 证据 envelope，GIS/Text/旧 Domain Pack 通过统一 provider 兼容 seam 输出 runtime/release evidence。
- 已实现 Action 输入指纹、幂等复用、输入冲突、失败重放、Action metrics/observability、历史列表与专用 artifact 下载；Console 已展示 Action ID、状态、trace 和 recovery/artifact 链接。
- 脱敏模型 replay evaluator 已按 `domain` 选择 Text 或 GIS provider，并增加一个开放式文本请求与一个复杂 GIS 总览请求。
- M127 专项 7 项、离线全量 674 项通过（42 项跳过）；smoke、stage profile、`git diff --check` 和远端 CI 稳定门禁通过。
- FastAPI/Docker/真实 GIS/LLM 仍是环境条件验收，不能用离线结果代替；当前最大并发度保持 1。

## M128 全局规划

1. 从完整 Agent 闭环审计 Run 与 Action 两套执行记录，抽取通用 Execution Record/事件投影 seam，使状态、trace、metrics、artifact/recovery 和幂等证据可以跨入口复用，而不是只在 Action 侧复制一份。
2. 将 CLI、开发 HTTP、生产 FastAPI、artifact 和 Console 的请求/计划/执行结果通过同一 Contract Harness 验证；补一条 Text 与一条复杂 GIS 的同步、异步、恢复矩阵。
3. 保持真实数据只作为 GIS Domain evidence，增加数据健康/降级证据与运行结果的关联；真实模型继续用脱敏回放作为默认证据，live 只做可选基线。
4. 以 Docker/FastAPI 可用性、CI 稳定门禁、前端动态 workspace 和跨领域回放为阶段验收，缺失环境必须输出明确阻塞证据而不是伪造通过。

## M128 当前进度

- 已新增 `spatial-agent.execution-record.v1` 深模块：Run 与 Domain Action 通过同一有界投影暴露身份、状态、领域、结果类型、轨迹数量、artifact 可恢复性、幂等存在性和错误码，不复制请求文本或工具 payload。
- Runtime `AgentRunResult`、Service、ArtifactStore、result envelope、Contract Harness、开发 HTTP 和 Console 均已接入该投影；历史无执行身份的旧 fixture 保持兼容。
- 已覆盖同步 Run/Action、失败 Action 重放、开发 HTTP、SQLite 异步恢复、artifact 和前端统一执行记录展示；M128 专项当前 7 项通过，受影响旧契约 13 项通过。
- 阶段收尾验证已完成：M128 专项 7 项、受影响契约 13 项、离线全量 681 项通过（42 项跳过），smoke、stage profile、compileall 和 `git diff --check` 通过；Docker/FastAPI/真实 GIS/LLM 仍按环境条件验收。

## M129 当前进度：Domain-owned Planner Guidance

- 已新增 `agent/planner_guidance.py`，定义 `spatial-agent.planner-guidance.v1`；`DomainPack.planner_guidance()` 是公共 Planner 与领域 policy 的唯一 seam。
- `LLMPlanner._system_prompt()` 已收敛为通用 JSON、ToolRegistry、工作流依赖、安全和澄清协议；GIS/Text policy 分别位于 `domains/gis/planner_guidance.py` 与 `domains/text/planner_guidance.py`。
- `runtime_factory`、脱敏模型评测和跨领域专项均显式绑定当前 Domain Pack guidance；公共 Planner 文件不再出现 DEM、土地利用、道路、水体或洪山区规则。
- 阶段收尾验证已完成：685 项离线测试通过、42 项按环境跳过；smoke、stage、full-stage、compileall 和 `git diff --check` 均通过。M129 已推送，随后完成 M129.1 测试门禁精简并进入 M130：Capability Routing/Catalog 与通用 Request Understanding。

## M129.1 当前状态：精简提交测试门禁

- 新增 `ci` profile：3 个 quick 核心契约、服务 smoke、1 个 `stage-spatial-analysis` 复杂编排场景；完整 `stage` 仍保留 3 个场景，按阶段收口显式运行。
- `evaluate_global.py` 支持有界 `--case-ids`；GitHub Actions push/PR 只运行 `ci`，完整离线回归保持 `workflow_dispatch` 手动入口。
- 未删除历史测试、GIS/live/Docker 专项或完整阶段 profile；只减少默认门禁中的低频重复场景。
- 本阶段完成后恢复 M130 的 Capability Routing/Catalog 与通用 Request Understanding 全局解耦，最大并发度保持 1。

## M130 规划参考

先从产品闭环、架构 seam、数据 evidence、真实模型、部署、Console 和测试证据全局盘点，再把 GIS 专用 capability routing 迁移为 Domain-owned discovery guidance；保持最大并发度 1。

## M130 当前实现状态

- 新增 `spatial-agent.request-understanding-guidance.v1`；Domain Pack guidance 进入 bounded Context 和 `plan_evidence`，GIS/Text 负向隔离已覆盖。
- Rule Planner 正常 Runtime 路径优先使用 Context 中已抽取的 `RequestFacts`；GIS parser、路由信号和路由表已物理下沉到 `domains/gis`，公共 `agent` 保留有界旧导入兼容。
- `agent/capability_discovery.py` 提供领域无关 discovery value objects；公共 catalog 的 GIS 默认只在兼容调用时惰性加载；Contract Harness 已比较请求理解 evidence。
- 当前已通过 M130 定向请求理解、M77/M78 路由目录、M95 facts、M112/M113 Text Domain 和 context 回归；`ci`、`stage`、跨入口 contract harness、compileall 和 `git diff --check` 均通过，全量离线 690 项通过、42 项按环境跳过。下一步按七维全局盘点进入 M131。

## M131 当前进度

- `DomainPack.rule_planner()` 已加入通用 Contract；GIS/Text Domain Pack 分别提供确定性 Planner，Runtime factory 与 Text Runtime 通过该 seam 选择，不再由公共 factory 假定单一 Planner。
- M131 适配回归、Text/GIS 既有跨入口回归和 M77 请求链路均通过；旧 `RuleBasedPlanner()` 入口保持兼容。
- 剩余缺口：GIS Rule Planner 的构建策略和固定回答仍在公共兼容实现中，下一步物理下沉到 GIS Domain，并补自定义非 GIS Planner 的完整跨入口 replay。

### M131 测试策略调整

- `quick` 只保留工作流编译和 Domain Planner 选择两个核心 tripwire；CI 的复杂空间代表场景负责验证实际编排，不再把同一个复杂运行放进 quick。
- `stage` 独立运行 3 个阶段验收场景；`full-stage` 独立运行完整全局离线评测/模型回放，均不再嵌套重复的 quick 或 smoke。
- 只收窄 profile 的默认执行集合，不删除历史测试；负向契约、跨入口、真实 GIS、live、Docker 和全量 discover 仍按风险显式运行。

## M132 当前实现：GIS Planner 物理归属收口

- GIS `RuleBasedPlanner` 与 `RuleBasedPlanComposer` 已物理下沉至 `domains/gis/planner.py`、`domains/gis/rule_planning.py`；GIS Domain Pack 直接返回该实现。
- 公共 `agent/planner.py` 只提供 `Planner` Protocol 与旧 `RuleBasedPlanner` 委托 facade；公共 `agent/rule_planning.py` 只提供旧 Composer 委托 facade，保持历史导入兼容。
- 已通过 M132 归属/兼容专项 24 项、`ci`、`stage`、编译和静态检查；下一阶段审计非 GIS Planner 的跨入口证据、动态入口和部署矩阵。

### M132 代码清理进度

- 新增 `docs/code-cleanup-plan.md`，以静态引用证据区分无效代码、兼容代码和可选环境入口；当前基线为 105 个运行/脚本/评测 Python 文件、124 个测试文件、695 个测试方法。
- 清理了确认无效的运行/测试导入、未使用局部变量与测试替身参数；修复 `capability_catalog` 的未定义动态全局读取和 Runtime 缺失 `List` 导入。
- Pyflakes、Ruff F401/F821/F841、Vulture、102 项受影响专项、M81 profile 9 项、`ci`、`stage`、compileall 和 diff check 均通过；测试 profile 的重复 subprocess 样板已抽成 helper，测试方法本身没有证据表明可以删除或存在完全重复体。

### M132.1 可疑死代码与测试替身审计

- 相对导入解析和入口搜索确认没有孤立的 `agent/`、`domains/`、`evaluation/` 运行模块；无直接 import 的脚本均由文档、PowerShell、profile 或专项测试作为显式入口使用。
- 删除 `AgentService._ensure_memory_session()`、`ServiceState` 中 7 个无调用的旧 state 操作，以及两个只赋值不读取的测试替身字段；保留兼容 alias、动态导出、registry 查询方法和反射序列化字段。
- 异步/重启/重规划/几何/profile 专项 43 项通过（1 项按 FastAPI 环境跳过），`ci`、`stage`、Ruff、Pyflakes、Vulture、compileall 和 diff check 均通过；下一步审计跨入口重复断言。

### M132.2 跨入口重复 fixture 审计

- `m65_spatial_overview_response.json` 与 M67 canonical model fixture 的 `response` 完全重复，已删除独立文件并让 M65 Runtime/ToolRegistry 测试读取 canonical response。
- M127 Domain replay 的同内容响应继续内嵌以保持 suite 自包含；没有删除 Service/HTTP/artifact/Console/模型质量的独立断言。
- M65/M67/M127/M81 相关 30 项通过，静态检查和编译检查通过；重复断言样板、删除 fixture 残留引用和过期运行注释复核完成，没有新增可安全删除项。

## M133 全局规划：跨领域 Runtime 闭环验收

下一阶段不再围绕单个 GIS 数据集增加规则，而是从完整 Agent 闭环推进：

1. 产品能力：让 Text 与 GIS 都走 `RequestFacts -> CapabilityCatalog -> TaskPlan -> Runtime -> Result/Trace/Artifact`，验证开放式问题仍能澄清、拒绝或完成。
2. 架构边界：补齐 Domain Pack、Planner、ToolProvider、Result Registry 和 HTTP/Console 的跨入口契约矩阵，继续保持公共 Runtime 不持有 GIS 规则。
3. 数据质量：把真实数据 provenance、CRS/栅格对齐、核心/可选数据降级统一投影到结果证据，不新增区域专用分支。
4. 真实模型：以脱敏回放作为默认证据，增加一个可选 live planner 基线，分别区分 provider、计划校验和工具执行失败。
5. 部署可靠性：按同步、异步、SQLite 重启、artifact 恢复和多进程观测检查同一执行记录，不让环境专项进入默认 CI。
6. 用户体验：Console 只根据结构化结果类型、证据和 workspace 动态展示，验证无结果时保持空态，有降级时可解释。
7. 测试证据：`quick`/`ci`/`stage` 保持分层，新增跨领域最小契约与一次显式真实环境验收，避免恢复重复 profile。

实现顺序为：先锁定跨领域结果与执行记录矩阵，再补 Text/GIS 双入口回归，随后验证 HTTP/Console/artifact/recovery，最后按环境运行 GIS、live、Docker 专项并整体重规划。

## M133.1 当前实现：Domain-owned ToolProvider seam

- `DomainPack.tool_provider(backend_name, root)` 已成为通用 Runtime Factory 的工具来源 seam；GIS 负责数据目录/后端与原生 provider，Text 负责 `text-native` provider。
- `build_runtime()` 不再默认先构造 GIS Registry；选定 Domain Pack 现在提供工具定义、dispatch provider 和默认权限，旧 Domain Pack 保留有界兼容 fallback。
- `domains/text/runtime.py` 已委托通用 Factory，`rule` 与 `openai` 经过相同的 Planner -> ToolRegistry -> Runtime 链路。
- M133.1 新增 2 项跨领域红绿回归，连同 M112/M113/M124/M126-M131 受影响回归共 49 项通过；Ruff F401/F821/F841、Pyflakes 和 compileall 通过。下一步补 HTTP/异步/artifact/recovery 的 Domain Pack 选择矩阵。

## M133.2 当前实现：Service/HTTP 的显式 Domain Pack 选择

- `AgentService` 新增 `domain_pack` 配置入口；它与自定义 `runtime_factory` 互斥，避免选择归属不明确；未配置时保持默认 GIS Factory 行为。
- Text Domain 已通过同一个 Service 配置路径覆盖同步运行、HTTP、artifact、异步 SQLite 和重启恢复，前端/HTTP 仍消费统一结果、规划和执行证据。
- M133.2 受影响回归 65 项通过；离线全量 700 项通过、42 项按环境跳过；`ci`、`stage`、Ruff、Pyflakes、Vulture、compileall 和 diff check 通过。真实 GIS/live/Docker 未因本次配置 seam 改动强行启动。

## M134 全局规划：部署边界的 Domain Registry 与跨入口矩阵

1. 产品：让部署配置选择的 Domain、Planner、Backend 在 capabilities、对话和结果证据中可见，避免前端/HTTP 默认为某个领域而用户无从判断。
2. 架构：建立受控 Domain Registry/选择器，统一 CLI、HTTP、生产 API 和 Console 的 Domain Pack 解析；禁止请求参数直接反射导入任意模块。
3. 数据质量：Domain 选择后仍沿用各自的 provenance、健康、对齐和降级策略，缺失配置要在 readiness 与结果中明确体现。
4. 真实模型：用同一 LLM Planner 接口分别做 Text/GIS 脱敏回放，保留可选 live 基线，比较计划契约而不是 provider 文本。
5. 部署可靠性：验证环境变量/配置文件、SQLite 重启、artifact 恢复和多 worker 缓存不会混用不同 Domain 的 Runtime。
6. 用户体验：根据 Domain 与结果类型动态展示能力、证据和 workspace，切换配置后清理旧会话/缓存，避免结果串域。
7. 测试：新增最小 Domain Registry 契约、配置错误负向测试和跨入口结果 Harness；默认 `ci`/`stage` 保持离线，真实环境作为显式验收。

## M134 已完成：受控 Domain Registry 与跨 Domain 持久化隔离

- `agent/domain_registry.py` 仅 allowlist `gis`/`text`，通过 `SPATIAL_AGENT_DOMAIN`、CLI `--domain`、Service、开发 HTTP、生产 API 和 Runtime Factory 统一选择；任意模块路径、未知值均拒绝；`GET /domains` 暴露有界目录。
- 真实 Runtime run、preview、artifact、SQLite snapshot、async payload 和 execution record 保存 `domain_id`；SQLite/artifact/history/metrics/Action 幂等和异步恢复按 Domain 过滤，同一 run_id 跨 Domain 覆盖会被拒绝，旧记录缺失字段按 GIS 兼容。
- M134 专项 7 项、受影响 Text/GIS/SQLite/Action 回归、离线全量 707 项（42 项按环境跳过）、full-stage、quick/ci/stage、Ruff、Pyflakes、Vulture、compileall 和 diff check 已通过；真实 GIS、live LLM、Docker 为显式环境验收，未被离线阶段强制启动。

## 下一阶段 M135 规划参考

围绕“不可变 Runtime Context/deployment snapshot”推进全局闭环：把 Domain、Planner、Backend、ToolProvider、权限、数据/模型证据和 schema 版本统一绑定到一次运行，验证配置变更、前端领域切换、SQLite 重启、多 worker、artifact/recovery 和 HTTP/Console 跨入口一致性。先完成 context contract 与负向隔离，再做真实 GIS/live/Docker 显式验收；最大并发度保持 1。

## M135 当前实现：Runtime Context 快照

- 新增 `agent/runtime_context.py` 的 `spatial-agent.runtime-context.v1`，只记录有界的 Domain、Planner、Backend、ToolProvider、权限、批准工具、策略和契约版本，不记录请求、凭据、工具参数或 provider 原文；TaskPlan 与 result envelope 版本由 `agent/contract_versions.py` 统一提供。
- Runtime 的 run/preview/capabilities、Service 的同步/异步、Domain Action、SQLite/artifact/recovery 和 Console 执行证据已接入同一快照；异步提交时先保存快照，worker 完成或重启恢复会校验当前 Runtime，配置漂移时明确失败而不静默换配置执行。
- M135 专项 8 项与 M128 执行记录回归 7 项通过；完整离线回归 715 项通过、42 项按环境跳过，`quick`/`ci`/`stage`/`full-stage`、GIS-core profile、Ruff、Pyflakes、Vulture、compileall 和 diff check 均通过。真实 GIS、live LLM 与 Docker 仍按显式环境验收，不因本阶段离线契约改动强制启动。

## 下一阶段 M136 规划参考

M136 从项目全局推进“跨入口 Runtime Context 与 Deployment Evidence Contract”：先把 `RuntimeContext` 纳入 `evaluation/contract_harness.py` 的 canonical projection，补直接 Service、HTTP、异步、artifact/recovery、Action 和 Text/GIS 的一致性与配置漂移负向矩阵；再绑定有界 data provenance、健康/manifest 和模型 replay/live 身份证据，最后让 Console 动态展示 Context、降级与漂移状态。所有任务保持单线程，默认测试不访问真实模型或私有数据，阶段完成后再按七维度重规划并推送版本。

## M136 当前实现状态

- Contract Harness canonical projection 已比较规范化 Runtime Context、版本化安全 model evidence 和 provenance Context fingerprint；顶层与 result envelope 的 Context 位置保持兼容，backend/domain 漂移会以有界字段路径报告。
- `model_evidence` 仅保留 provider/model/wire_api、状态、错误分类、重试、延迟和 token usage 白名单；`AgentRunResult`、result envelope、run/action artifact 写入均规范化 Context，未把 API key、私有路径或 provider 原文带入证据。
- 异步 polling/restart observability 增加 Context fingerprint；M136 补充 3 项跨入口回归，受影响矩阵 83 项通过，完整离线 722 项通过、42 项按环境跳过，分层 profile、静态检查和 compileall 通过。
- 真实 GIS、live LLM 和 Docker 没有被默认测试强制启动；data provenance/manifest 的发布校验与真实环境证据绑定保留为下一阶段任务。

## 下一阶段 M137 规划参考

M137 从全局推进“统一 Deployment Evidence Contract”：将 runtime/release 数据 provenance、manifest、CRS/栅格对齐、source/output binding、rule/replay/live 模型身份和可恢复性绑定到 Runtime Context fingerprint，形成公共、无私有路径的 evidence projection。先完成 release/runtime 与 Text/GIS 正负矩阵，再扩展模型 replay/live identity、Console 动态证据区和生产 acceptance；当前宿主 Docker 不可用，不能把旧容器结果当作当前版本证据，最大并发度保持 1。

## M137 当前实现进展

- runtime/release evidence 已返回 Context fingerprint；Text/GIS 共享该身份，数据健康、manifest、source binding 和 output manifest 仍由 Domain Evidence Provider 负责。
- `model_evidence` 支持 rule/offline replay/live model 执行模式，评测 fixture 只暴露 bounded identity；新增的 `deployment_evidence.v1` 聚合 Context、模型、数据状态和降级摘要，结果、能力快照、发布报告与 Console 共用。
- M137 专项 4 项通过，M135/M136 相邻 Context/跨入口专项 12 项通过；`quick`、`ci`、`stage`、`full-stage`、compileall、Ruff、Pyflakes、Vulture 和 `git diff --check` 均通过，完整离线回归 726 项通过、42 项按环境跳过。Docker 当前宿主不可用，不能把历史容器验收当作本版本证据。

## 下一阶段 M138 全局规划

M137 已建立统一 `spatial-agent.deployment-evidence.v1`，但生产 acceptance 尚未把 runtime capabilities、`/release-evidence`、同步/异步结果、失败运行和 artifact/recovery 的证据一致性作为门禁。M138 先完成跨入口 deployment evidence 验收与发布 readiness 闭环，再完善通用 Console evidence card；不新增 GIS 专用规则，最大并发度保持 1。

1. 统一 schema、Context fingerprint、状态语义和敏感字段检查。
2. 生产 acceptance 覆盖 runtime/release/run/artifact/failure/async，并接入 Contract Harness。
3. Console 展示配置、数据、模型、降级、恢复状态和发布证据引用，Text/GIS 共用。
4. 默认 profile 保持离线；Docker/FastAPI/GIS/live 仅在环境可用时执行当前版本显式验收。

## M138 当前实现状态

- 生产 acceptance 已覆盖 `spatial-agent.deployment-evidence.v1` 的 runtime/release/run/artifact/failure/async 入口，校验状态、Context fingerprint、模型模式、数据/降级 section 和敏感字段；runtime 与 release 证据必须共享 fingerprint。
- Console 统一执行证据卡显示 deployment 状态、数据 readiness、降级状态和发布证据链接，Text/GIS 共用动态路径。
- 关联回归 19 项通过（1 项真实 Docker acceptance 按环境跳过）；`quick`、`ci`、`stage`、`full-stage`、compileall、Ruff、Pyflakes、Vulture、PowerShell parser、Node 内嵌 JS 和 diff check 通过；完整离线 726 项通过、42 项按环境跳过。
- Docker Linux engine 当前不可用，当前版本 FastAPI/Docker/GIS/live production acceptance 未验证，不能把旧容器结果当作本版本证据。

## M139 当前实现状态

- GIS intent/clarification 实现已物理归属 `domains/gis/intent.py`；公共 `agent/spatial_intent.py` 仅保留惰性旧导入 facade，GIS Planner 不再从公共模块读取领域策略。
- `DomainPack.clarification_details()` 与 Runtime preview/run fallback 已接入，当前 Planner 未提供 details 时会生成选定 Domain 的结构化 clarification；Text Domain 保持中性。
- M139 专项 3 项、M62/M130 相关回归 11 项通过；`quick`、`ci`、`stage`、`full-stage`、compileall、Ruff、Pyflakes、Vulture 和 diff check 通过；完整离线 729 项通过、42 项按环境跳过。
- 真实 GIS/live/FastAPI/Docker 仍未宣称通过；下一阶段先将 capability requirements 从 GIS 澄清逻辑中进一步抽象，再增加开放式模型回放。

## 下一阶段 M139 全局规划

M138 已完成 deployment evidence 的跨入口验收门禁。M139 转向请求理解边界：将仍位于公共 `agent/spatial_intent.py` 的 GIS 词汇、能力提示和缺参策略下沉到 GIS Domain，建立可替换的 intent/clarification seam；保持旧导入兼容、Text/GIS 隔离、结构化澄清结果和默认离线 profile，最大并发度保持 1。

顺序为：Domain-owned projection -> GIS 迁移/兼容 facade -> preview/run/HTTP evidence 贯通 -> 脱敏开放式回放与跨入口验收 -> 全局七维重规划。

## M140 当前阶段：CapabilityCatalog-owned 请求需求与真实环境验收

- `agent/capability_catalog.py` 新增 `spatial-agent.capability-requirements.v1` 的有界归一化和通用澄清需求投影；GIS 能力在 `domains/gis/catalog.py` 声明实体、数据集、约束事实，GIS intent 不再按 capability ID 硬编码缺参；Text Domain 保持隔离。
- `domains/gis/evidence.py` 将历史 runtime snapshot 的 `capabilities` 适配为通用证据 seam 的 `capabilities_runtime`；M140 专项覆盖自定义 capability、GIS 澄清、Text/GIS 隔离和兼容适配。
- `production_acceptance.ps1` 会选择真实可运行 Python 并跳过 WindowsApps alias，Harness 失败会报告解释器和退出码。当前 Docker Engine 29.6.2 可用，容器以当前工作树重建并通过 `--env-file .env.production` 挂载 `D:/dataset/agent`，healthy 且真实 GIS 数据 ready。
- M140/M139/M62 15 项、`quick`/`ci`/`stage`/`full-stage`、GIS-core、全量离线 735 项（42 项跳过）、compileall、Ruff、Pyflakes、PowerShell parser、diff check 和 Docker production acceptance 已通过。
- live smoke 中约束建设案例通过；空间总览案例的真实模型返回了重复 `range_query` 和未声明依赖，被 `tool_validation` 正确拒绝，provider 错误分类为 none。不要把该部分 live 结果记为全量通过；问题已记录在 `docs/agent-development-issues.md`。

## M141 下一阶段全局规划

从全局 Agent Runtime 继续推进模型计划稳健性：建立 capability-guided、受预算限制的 plan repair seam，统一 rule/offline replay/live 的 TaskPlan schema、DAG、ToolRegistry 和 repair lineage；补复杂总览脱敏 replay 与可选 live 基线，并验证同步、异步、artifact/recovery、Text/GIS 和 Console 的同一证据契约。规划不得退化为某个区域或数据集的专用分支，最大并发度保持 1。

## M141 当前实现与验证状态

- planning-phase bounded plan repair 已接入 `AgentRuntime`：初始计划校验失败时最多修复一次，修复计划重新通过 workflow、TaskPlan 和 ToolRegistry 校验；planning repair 与 execution replan 共用预算，Rule Planner 保持确定性路径。
- repair context 只继承有界的 `available_tools`、`capability_discovery`、`capability_catalog` 和 `workflow_templates`，不把凭据或模型原文写入证据；`phase` 已贯通 preview、result envelope、trace 和 artifact/recovery。
- M141 及相邻回归 34 项、`quick`/`ci`/`stage`/`full-stage`、全量离线 739 项（42 项跳过）、F401/F821/F841、Pyflakes、compileall 和 diff check 通过。
- Docker Engine 29.6.2 可用；通过国内镜像重建并挂载 `D:/dataset/agent` 后，容器 healthy，production acceptance 通过。新增 `UTF8JSONResponse` 修复 PowerShell 对生产同步 JSON 中文的错误解码，避免 sync/artifact Contract Harness 假失败。当前未宣称复杂 live 总览完全通过。

## M142 下一阶段全局规划参考

围绕完整 Agent 闭环推进计划修复质量：脱敏 replay 评测“原计划无效 -> 修复成功/拒绝”的质量和预算，统一同步、异步、重启、HTTP、artifact、Text/GIS 的 repair lineage，再让 Console 动态解释已修复、拒绝和需澄清状态。保持单线程、默认离线和严格 Registry 边界，阶段收尾再做真实 GIS/live/Docker 验收。

## M142 当前阶段：极简测试门禁与历史测试隔离

- 默认 `unittest discover -s tests -t .` 通过 `tests/__init__.py` 的 active allowlist，只运行 `test_dev_gate` 和 `test_http_contract` 共 4 项；历史里程碑测试保留为显式诊断资产。
- `quick` 只运行 2 个 compact Runtime 契约；`ci` 只组合 quick 与 service smoke，不再隐式运行 stage 代表场景。`stage`、`full-stage`、GIS、live、Docker 仍按风险显式执行。
- README、CI、smoke、demo checklist、task resume 和 test strategy 的 discovery 命令已统一加 `-t .`；平铺 discovery 绕过 package `load_tests` 的原因和预防已写入 `docs/agent-development-issues.md`。
- 验证证据：compact discovery 4 项通过，quick 2 项通过，ci、stage、`smoke_check.py --with-unit-tests` 均通过。不要把这组 compact 结果描述为历史全量回归通过。

## M143 下一阶段全局规划参考

从项目全局继续保持“最小反馈、按风险扩展”：共享 Runtime/HTTP/结果契约改动时只增加必要的跨入口专项，真实 GIS/live/Docker 和完整历史模块测试继续作为显式验收；任何新增测试必须说明它属于 active gate、阶段 acceptance 还是专项诊断，禁止自动加入默认 discovery。

## M143 当前实现：跨入口最小契约证据

- compact active gate 仍保持 4 项，但其中一项现在用同一个请求比较 direct `AgentService`、真实 `run_demo.py` CLI、HTTP `POST /runs` 和两份 run artifact 的 `evaluation.contract_harness` 投影。
- 该投影覆盖结构化结果类型、中文答案、计划/能力证据、工具步骤、轨迹、workspace/view 和执行身份；忽略 run ID、路径和时间等传输差异，因此前端作为 HTTP 结果消费者也有可验证的稳定入口契约。
- compact discovery 4 项、CI（quick + service smoke）、Pyflakes、compileall 和 diff check 已通过；没有新增默认测试数量，也没有把真实模型或私有 GIS 数据引入门禁。

## M144 下一阶段全局规划参考

下一阶段优先检查“统一结果契约是否真的支撑动态前端”：让 Domain-owned view spec、通用 renderer 和 workspace 空态形成一个跨 GIS/Text 的小型契约；仅补一个跨领域负向证据，避免把前端逻辑重新扩展成领域分支。真实 GIS、live、Docker 和历史测试继续保持显式入口，最大并发度为 1。

## M144 当前实现：跨领域动态 view contract

- Text Domain 新增 `domains/text/views.py`，为 `text_summary_result` 生成受限 `generic` view model，并在 Domain-owned `ResultContractRegistry` 中声明 `ViewSpec`；公共 Runtime、`result_contract.py` 和前端没有新增 Text/GIS 专用分支。
- Console generic renderer 现在会直接消费 `generic` view，而不是将非 GIS 结果退化为 raw JSON；未知 view 仍通过 view spec 和通用 rows/metrics/table/error/note fallback 渲染。
- M122/M113/M124/M133 跨领域专项 21 项、Console 静态 smoke 14 项、compact 4 项、Pyflakes、compileall、Node smoke 脚本语法检查和 Docker production acceptance 已通过。
- 宿主 Chrome CDP 本轮仍未启动，动态浏览器 smoke 未伪称通过；容器真实 API/数据卷验收通过，静态 Console 契约提供当前前端证据。

## M145 下一阶段全局规划参考

下一阶段从完整 Agent 闭环补齐“结果契约 -> 动态前端 -> 可恢复证据”的最后一段：让 generic view 的空态、降级和 artifact 引用也由结构化 evidence 驱动，并在 Text/GIS 两个 Domain 下验证同步、异步恢复和浏览器可消费字段一致。继续保持 compact 默认门禁，真实浏览器/CDP 恢复后只运行显式 smoke。

## M145 当前实现：统一 view 空态与恢复证据

- `result_contract.build_result_contract()` 会为声明但没有实际数据的 ViewSpec 生成 bounded `kind: unavailable` view，携带结构化降级原因和 `artifact_available`，同步、异步、artifact 和恢复入口共享同一 envelope。
- 旧 artifact 的空 `views.panels` 不再覆盖当前生成的 unavailable view；非空 artifact view 仍作为成功/恢复结果的权威视图。Console generic renderer 显示空态原因，并在有 artifact 时提供运行记录链接。
- M122/M113/M124/M133 相关 22 项、Console 静态 smoke 14 项、compact 4 项、CI、Pyflakes、compileall、Node 脚本语法检查和当前 Docker production acceptance 已通过。
- 宿主 Chrome CDP 仍未启动，动态浏览器 smoke 未宣称通过；Docker/API/静态 renderer 证据与浏览器证据保持分离。

## M146 当前实现与验证状态

- `agent/service_async.py` 新增 `spatial-agent.async-result-evidence.v1` 安全投影；`GET /runs/{run_id}/async` 现在直接返回 pending/success/degraded/unavailable 状态、结果类型、workspace/view kind 与 artifact 可恢复性，不复制请求、答案、原始错误或宿主路径。
- `AgentService.get_async_observability()` 从同一 Domain-owned result registry 重建 result contract；SQLite 终态、重启恢复和 HTTP 轮询共用相同 view evidence。artifact 引用只保留 basename。
- 新增 M146 专项 2 项，覆盖 success/degraded/unavailable 三态、路径脱敏、SQLite 重启、artifact、HTTP `/async` 轮询；M122/M124/M133 相邻专项 16 项、compact discovery 4 项、CI、compileall 均通过。
- Docker Desktop 已从 `D:\code\DockerDesktop` 启动；当前 Engine 29.6.2，容器 healthy，`D:/dataset/agent -> /data (ro)`；生产 acceptance 通过，包含 async polling view state=`success`。动态 Chrome smoke 仍未验证。
- 生产 acceptance 的只读 GET 超时从 5 秒调整为 30 秒：真实 GIS 容器冷启动首次生成 capabilities snapshot 实测约 8 秒，不能误报为服务失败；POST 超时保持 10 秒。

## M147 下一阶段全局规划参考

从全局 Agent Runtime 继续推进“证据可组合但不膨胀”：统一 async result evidence、deployment evidence、artifact lineage 与 Console 消费边界，优先处理结果契约版本迁移、旧 artifact 兼容和多 Domain 负向隔离；再评估真实模型计划修复的可观测性。默认 active suite 不扩张，阶段专项保持最小风险矩阵，最大并发度保持 1。

## M147 当前实现与验证状态

- `agent.contract_versions` 新增 `spatial-agent.run-artifact.v1`；新写入的 run artifact 带显式版本。缺少版本字段的历史 artifact 继续可恢复，未知未来版本不会被静默当作当前格式读取。
- `ArtifactStore` 对 run artifact 的写入和读取统一执行安全 `run_id` 文件名校验，拒绝斜杠、反斜杠、`.`、`..` 和超长值；Domain 过滤保持在 artifact recovery/list/read 边界。
- Console 新增通用 `renderAsyncResultEvidence()`，消费 `async_observability.result_evidence` 的状态、结果类型、view 状态和 artifact 可恢复性，没有增加 Text/GIS 结果类型分支。
- M147 专项 3 项（版本/旧格式/未知版本/跨 Domain/路径边界/Console 静态契约）与 M146 专项合计 19 项、compact 4 项、CI、内嵌 JS 语法检查通过；Docker 最终镜像专项 5 项和 production acceptance 通过。

## M148 下一阶段全局规划参考

从整体 Runtime 继续检查 evidence schema 的跨版本投影和真实入口一致性：先让 Contract Harness 显式比较 artifact/async evidence 版本与降级状态，再补 Text/GIS 双 Domain 的 HTTP/Console 负向隔离，最后进行真实模型 replay/live 与 Docker 显式验收。默认 active suite 不扩张，后续可将边界清晰、互不修改同一公共契约的任务并行拆分，最大并发度为 5。

## M146 下一阶段全局规划参考

下一阶段从整体可靠性收口 view evidence 的异步生命周期：验证 `unavailable`、degraded、成功 view 在 SQLite 重启、多 worker 轮询、artifact recovery 和 HTTP 详情中的一致性，并检查前端链接只消费安全的 artifact 引用。默认 active suite 不扩张，专项测试按风险显式运行。
