# Spatial Agent 对话恢复文档

本文档用于在新对话中恢复 Spatial Agent 项目的开发上下文。新对话开始后，应先阅读本文档，再检查 Git 状态和相关文件，然后继续当前任务。

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

## 当前恢复位置：M60 已完成，下一阶段为 M61

已获取并核验武汉道路、水体、行政区、DEM 和土地利用数据。M50 已完成真实栅格候选与 OSM 道路/水体约束闭环；M51 已新增 `get_dataset_health_report`，并接入工具 schema、规则 Planner、LLM guidance、中文 AnswerComposer 和 Console 的数据健康面板；M52 又增加了 DEM/土地利用跨栅格覆盖关系检查。

真实武汉健康检查结果：行政区、道路、水体为 `ready`；DEM 和土地利用文件可读取，但跨 `EPSG:32649`/`EPSG:32650`，因此标记为 `degraded`。M54-M56 已将健康预检接入综合建设分析、单独区域栅格统计和复合行政区栅格分析，并增加能力声明和不可用数据门控。M60 验证结果为 208 个离线测试、205 个 GIS 测试通过，smoke、全局评测、生产 acceptance 和浏览器烟测通过。

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

大阶段最多拆分 5 路并行；仅将边界清晰、可独立测试且不同时修改同一公共契约的任务并行执行。推荐拆分为能力快照、SQLite 可靠性、几何证据、评测/答案契约、部署/Console 验收五路；所有任务必须在共享 schema、runtime 状态、result envelope 和能力目录上统一集成。

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
- 开发采用“整体规划 -> 可并行实现 -> 集成测试 -> 整体重规划”循环；可并行子任务最多 5 个。
- 每个阶段完成后更新 docs/milestones.md、恢复文档，并创建一个 GitHub 版本；私有配置和原始数据不得提交。
- 全局 goal：持续执行“整体规划 -> 最多 5 路可并行实现 -> 统一集成测试 -> 全局重规划”，阶段验收通过后提交并推送版本；规划必须覆盖产品能力、数据质量、真实模型、部署可靠性和用户体验。
