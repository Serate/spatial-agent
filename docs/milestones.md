# Spatial Agent 阶段记录

本文档记录项目每个阶段完成的功能、验证结果和关键工程决策。README 只保留当前能力与使用方式；后续阶段完成后，先更新本文档，再更新恢复文档，并创建对应 GitHub 版本。

## 当前执行规则

- 当前最大并发度为 5；阶段任务按依赖关系拆分，边界清晰的子任务可并行执行，共享契约由主线统一集成。
- 后文早期阶段保留当时的并行度作为历史事实；它们不代表当前有效规则。

## 基础 Agent Runtime

- M0：建立项目定位、设计基线、工具 schema 和评测用例。
- M1：实现 Planner、TaskPlan、Tool Registry、Agent Runtime 和内存空间后端。
- M2：接入 LLMPlanner、OpenAI 兼容客户端、计划 schema 校验和 Fake LLM 测试。
- M3：抽象 SpatialBackend 与 SpatialToolAdapter，保持后端可替换。
- M4：增加步骤耗时、评测运行器和 JSON 回归报告。
- M5：增加 GeoPandas/Rasterio 数据探测和本地数据配置。
- M6-M7：接入真实行政区 GeoJSON，支持自然语言行政区查询。
- M8-M9：增加中文答案组合、多轮澄清和 session 隔离。

## 服务与可观测性

- M10：实现 AgentService 和标准库 HTTP API。
- M11-M12：增加 smoke check、CI、API 契约文档和边界测试。
- M13：增加可读执行轨迹，覆盖完成、澄清和拒绝状态。
- M14：增加运行 artifact 导出，避免导出原始空间数据和敏感参数。
- M16：实现可选真实模型路径，支持自定义 provider、Responses、Chat Completions、超时和 usage metrics。
- M18：增加受限 GeoJSON summary 导出和空间引用边界。
- M21-M23：实现中文 Console、运行环境检查、生产 Docker 基线、会话交互和武汉本地数据配置。
- M28-M30：增加会话控制、真实模型可选验收和每步结果摘要。
- M32-M37：实现多步骤结果引用、fail-fast、失败重试、provenance、取消和超时。

## 栅格与区域分析

- M15：接入真实 DEM/土地利用栅格元数据查询。
- M24-M27：增加分块栅格统计、区域栅格统计、NoData 指标、受限值分布和 Console 可视化。
- M31：增加栅格 bounds/CRS 证据与覆盖范围预览。
- M38：接入真实土地利用区域分布和真实 DEM 派生坡度分析。
- M41-M44：实现建设适宜性演示筛选、自然语言变体和核心流程评测契约。
- M46-M48：统一结果 envelope、空间上下文、会话恢复和清空行为。
- M49：增加异步运行、状态轮询和协作式取消。

## 武汉真实数据与质量控制

- M50：下载并转换武汉 OSM 道路、水体为 GeoPackage；完成 DEM、土地利用候选与道路距离、水体排除的联合演示筛选。
- M51：增加 `get_dataset_health_report`，检查文件可读性、CRS、覆盖范围、要素数量和基础几何质量。
- M52：增加 DEM 与土地利用跨栅格覆盖关系检查，只读取元数据，不加载完整像元。
- M53：为联合建设筛选加入显式数据健康 preflight，并把预检证据写入答案和执行轨迹。
- M54：将 preflight 扩展到综合高程、坡度、土地利用和建设候选分析。
- M55：将 preflight 扩展到单独区域栅格统计及复合行政区栅格流程。

## 验证基线

M55 完成时的验证结果：189 个离线测试通过、36 个 GIS 重点测试通过，`scripts/smoke_check.py` 和浏览器健康烟测通过。真实 DEM/土地利用跨多个 UTM 分区时保留 `degraded` 状态，不伪装为完全可用。

## M56：证据驱动的执行策略

- 健康报告为每个数据集增加 `usable_for`，整体报告增加 `capabilities`，并根据 DEM/土地利用覆盖关系声明建设候选能力。
- Runtime 在健康预检完成后，在下游工具 dispatch 前检查明确不可用的数据；失败步骤和后续阻塞步骤保留在轨迹中。
- AnswerComposer、LLM guidance 和 Console 展示能力/停止原因；内存演示继续提供明确的占位结果。
- README 与阶段记录分离：README 聚焦功能、架构、部署和验证，阶段历史集中在本文档。
- M56 验证：191 个离线测试、38 个 GIS 重点测试、smoke 和浏览器健康烟测通过。

## M57.1：统一建设候选对比场景

- 阈值对比和多区域对比共享 `BuildabilityComparisonScenario`，统一行政区清洗、阈值去重、范围校验和场景序列化。
- 两个比较 API 都返回 `scenario`，保留原有字段以兼容现有 Console。
- M57.1 验证：194 个离线测试、19 个 GIS/真实数据重点测试通过。

## M57.2：全局验收矩阵

- 新增 `evaluation/cases/global-acceptance.json`，集中描述通用问答、单区域、多数据集、阈值对比、多区域、不可用数据、真实 GIS 和真实模型场景。
- 新增矩阵契约测试，验证 Runtime 与比较 API 的结果类型、工具序列、统一场景和不可用数据边界。
- M57.2 验证：197 个离线测试、36 个 GIS 重点测试、smoke 和浏览器健康烟测通过。

## M58.1：分环境全局评测报告

- `evaluation.runner` 报告增加 `evaluation_context`，记录 environment、execution_mode 和 planner。
- 显式 `expected_status` 现在参与评测，不再被默认状态推断覆盖。
- 新增 `evaluation.global_runner` 与 `scripts/evaluate_global.py`：可执行内存场景和比较 API，GIS/真实模型/部署场景未显式启用时明确标记 skipped。
- M58.1 验证：全局矩阵离线执行 7/7 通过、3 个可选环境跳过，197 个离线测试通过。

## M58.2：部署验收工具与 SQLite 重启验证

- 新增 `scripts/production_acceptance.ps1`，统一检查 liveness、readiness、异步提交、状态轮询和终态结果。
- 新增 SQLite 异步快照重建测试，验证服务对象重建后仍可读取已完成运行。
- 200 个离线测试通过，PowerShell 脚本解析通过。
- Docker Engine 当前返回 named pipe 权限错误，因此 Compose/容器实际启动验收保留为未完成的环境任务。

## M58.3：实际 Docker/Compose 业务验收

- Docker Engine 恢复后完成 Compose 配置解析、容器健康检查和 `/health/ready` 验收。
- 容器重启后再次执行异步业务请求，确认 SQLite 运行快照和最终结果契约可恢复。
- 修复生产 PowerShell 验收的 session 隔离和中文 UTF-8 请求编码，脚本返回 `status=ok`、`readiness=ready`、`async_status=COMPLETED`。
- M58.3 验证：离线 200 个测试通过、GIS 环境 190 个测试通过、smoke check 和浏览器健康烟测通过；重启后容器保持 healthy。

## 后续全局执行协议

- 目标扩展为围绕可演示、可观测、可替换、可测试和可部署的完整空间智能体，持续执行“整体规划 -> 实现 -> 集成验收 -> 全局重规划”循环。
- 每个大阶段先按模块边界拆成可独立验收的子任务，再按依赖顺序单线程执行，当前最大并发数为 1。
- 所有任务共享工具 schema、运行状态、结果 envelope、评测用例和数据能力契约，由主线统一集成并执行全量回归。
- 阶段完成的判定同时包含功能、离线测试、GIS 测试、浏览器/HTTP 验收和文档更新；通过后创建并推送一个 GitHub 版本。
- 每次阶段复盘必须从项目整体能力、数据质量、真实模型、部署可靠性和用户体验五个维度重新规划下一阶段。

## 下一阶段 M59：统一能力编排与全局评测扩展

- 将数据集健康能力、工具依赖、结果类型和环境要求收敛为可查询的能力目录，供 Planner、Runtime、Console 和评测共同消费。
- 扩展全局评测矩阵的跨环境执行与报告对比，明确区分规划成功、工具执行成功、真实空间几何和演示结果。
- 为异步运行、会话恢复、失败重试和结果引用增加跨进程部署契约测试。
- 以最多 4 路并行拆分能力目录、评测报告、部署契约和 Console 展示，最后统一集成验收并重新规划下一阶段。

## M59.1：统一能力目录与跨入口契约

- 新增 `agent/capability_catalog.py`，统一描述工作流、数据集、工具、结果类型、环境要求和几何证据边界。
- 数据健康报告增加带数据门控状态的能力目录；运行环境和 `/capabilities` API 只在有健康证据时标记 `ready`，否则标记 `unknown`。
- 全局评测用 `capability_id` 校验场景工具序列和结果类型，报告继续区分模型/工具成功与真实几何证据。
- Console 环境区显示能力目录摘要；开发服务和生产 FastAPI 入口均提供 `/capabilities`。
- M59.1 验证：离线 206 个测试通过、GIS 196 个测试通过，生产容器重建后 `/capabilities` 返回 8 项能力，production acceptance 和浏览器健康烟测通过。

## M59.2：跨进程运行与结果证据验收

- 将能力目录中的环境要求接入评测 optional gating，避免只凭 planner/tool 成功标记真实 GIS 能力完成。
- 为生产 SQLite 的会话、运行、重试、取消和结果引用增加跨进程契约矩阵。
- 让几何证据状态从 `unknown` 细化为真实 artifact 几何、边界几何、无几何演示和截断不可绘制，并接入 Console 与全局报告。
- 生产验收脚本纳入 `/capabilities`；内存导出验证为 `no_geometry`，真实 GIS 建设筛选验证为 `real_geometry`、101 个要素且可绘制。
- M59.2 验证：离线 207 个测试、GIS 197 个测试、smoke、全局评测、生产 acceptance 和浏览器烟测通过。

## 下一阶段 M60：真实数据能力与异步可靠性深化

- 将能力目录从静态定义扩展为带数据覆盖、CRS、质量等级和更新时间的运行时能力快照。
- 完成生产 SQLite 的重试、取消、会话清空和结果引用跨进程矩阵，并覆盖异常重启和重复请求。
- 将真实几何证据状态接入评测报告、答案组合和地图渲染，明确截断与不可绘制原因。
- 按依赖最多拆分 4 路并行任务，集成后重新验收真实模型、GIS 数据和部署链路。

## M60：运行时能力与异步可靠性深化（已完成）

- 新增 `agent/runtime_capabilities.py`，按需生成运行时能力快照；快照包含数据质量、覆盖范围、CRS、文件数、检查文件数和更新时间。
- `agent/capability_catalog.py` 新增 `runtime_capability_catalog()`；数据健康报告增加 `updated_at`。
- `serve_api.py` 和 `production_api.py` 均提供 `GET /capabilities/runtime`；`scripts/production_acceptance.ps1` 增加运行时能力快照验收并输出 `runtime_health`。
- 当前实现只按请求生成快照，不把快照本身当作真实几何或业务分析成功的证明；数据质量、CRS 警告和几何证据仍需由具体工作流验证。

### M60 当前验证状态

- 运行时能力与入口契约测试通过；默认环境缺少 FastAPI 的测试按环境条件跳过。
- 生产容器已重建；`/capabilities/runtime`、健康检查、异步提交/轮询和 production acceptance 通过。容器完整健康状态为 `unavailable`，原因是示例数据卷未提供 roads/water；DEM、land_use 和 admin_areas 的逐项证据仍为 `ready`。
- SQLite 跨进程测试覆盖结果引用、会话清空、取消标记和失败重试，4/4 通过；离线全量 208 项通过、GIS 全量 205 项通过、smoke、全局评测 7/7 和浏览器烟测通过。

### M60 并行拆分规则

- 历史记录：M60 当时最多拆成 5 个并行子任务；当前全局规则已调整为最大并发度 3。
- 推荐拆分为：运行时能力快照、SQLite 异步可靠性、几何证据与导出、评测/答案契约、部署与 Console 验收。
- 并行任务必须共享工具 schema、运行状态、结果 envelope、能力目录和测试数据；不得各自定义同名字段或独立改变公共协议。
- 集成前先运行各自聚焦测试，集成后统一执行离线、GIS、HTTP/浏览器和 Docker 验收；未通过集成验收不得创建阶段版本。

## M61 后续全局规划

1. 产品能力：扩展通用空间问题的意图识别、参数澄清和多工具编排，保持 ToolRegistry 与结果 envelope 边界。
2. 数据质量：补齐武汉道路/水体容器数据卷方案，区分核心数据缺失、可选数据缺失和 CRS/覆盖降级。
3. 真实模型：在不进入默认 CI 的前提下，继续验证结构化计划、超时、重试和 token 指标。
4. 部署可靠性：完善异步作业幂等、重启恢复、观测指标和生产验收矩阵。
5. 用户体验：让 Console 根据结果类型动态展示证据、地图和轨迹，减少固定面板并解释降级状态。

## M61 当前进展

- 数据健康已分为核心层（行政区、DEM、土地利用）和可选层（roads、water）；能力目录按能力单独计算 `capability_status` 与 `available`，可选数据缺失不会掩盖核心能力。
- 异步 SQLite 已支持请求指纹/显式 `idempotency_key`、并发重复提交复用同一 `run_id`、显式运行 ID 重放、清空会话删除去重键和新服务接管遗留作业。
- OpenAI 兼容客户端已支持可配置超时、暂态错误重试、指数退避上限和安全的 attempts/retries/latency/token usage 指标；鉴权失败和 WinError 10013 不重试。
- M61 专项测试目前 20 项通过；尚未完成全量离线、GIS、生产容器和阶段提交验收。

## M62 当前进展：开放式空间问题与能力驱动澄清

- 新增 `agent/spatial_intent.py`，只分类空间性、候选能力和提示词，不宣称工具已执行。
- RuleBasedPlanner 对未匹配的空间问题返回可继续对话的澄清，说明已识别的能力和需要补充的区域/数据集/阈值。
- 保留旧道路/坡度工作流的参数校验和 ToolRegistry 执行边界；新增 M62 契约测试覆盖未知空间问题、已匹配提示和非执行声明。

## M62.1：结构化空间澄清（已完成实现）

- `ClarificationNeeded` 支持可选详情；运行快照、SQLite 恢复和统一 `result` envelope 保留 `clarification`。
- 空间意图返回状态、匹配/建议能力、缺失字段和下一步动作，并兼容原有中文 `error` 文本。
- Console 在结果区展示澄清状态、相关能力和下一步动作，不再要求客户端解析错误字符串。
- 专项、核心工作流和结果契约测试通过；阶段版本仍需全量离线、HTTP/浏览器和 GIS 联合验收。

## M62 后续集成任务

1. 将结构化澄清纳入 HTTP 契约、全局评测和会话恢复验收矩阵。
2. 让能力目录提供中文标签和可执行入口，避免前端维护能力列表。
3. Docker 环境恢复后重新构建并验收开放式问题生产链路。

### M62.2 集成进展

- 澄清候选能力复用 `capability_catalog` 的 ID 和中文 label；Console 通过结构化字段渲染，不维护第二份能力名称表。
- 标准 HTTP `POST /runs` 已增加 `NEEDS_CLARIFICATION` 结构化返回契约测试。
- 当前离线全量 243 项通过、31 项按环境跳过；GIS、浏览器和 Docker 联合验收待环境条件满足后执行。

## M63：受控空间总览编排（实现中）

- 新增 `spatial_overview` 能力和 `spatial_overview_result` 结果类型。
- “分析洪山区空间概况”等开放表达会生成 8 步受控计划：数据健康、行政区解析、高程、坡度、土地利用、道路和水体摘要。
- 计划仍经 TaskPlan、依赖执行、ToolRegistry 和数据健康门控；内存后端只返回演示限制，真实几何和栅格证据仍需 GIS 环境验证。
- 已完成规则 Planner、能力目录、AnswerComposer 和专项测试；待完成全量回归、全局评测用例、浏览器展示和 GIS/Docker 验收。
- M63 真实 GIS 回归 41 项通过；Docker 重新构建后生产验收通过，容器 `healthy`，空间总览同步请求返回 8 步 `spatial_overview_result`。
- 生产入口修复了同步路由误传异步 `idempotency_key` 的问题；全量离线测试 245 项通过、32 项按环境跳过。

## M64：真实总览证据与动态地图（实现中）

- 武汉真实 GIS 总览已验证可生成行政区、道路和水体几何；导出后结果现在按最终 GeoJSON 正确标记 `real_geometry` 或 `truncated_geometry`，并保留 `geojson/geopackage` 来源。
- 总览导出 feature 增加 `dataset` 标签，Console 已注册总览结果面板，并准备按道路/水体/边界分层渲染。
- LLM Planner guidance 已加入总览计划约束；待完成浏览器实际渲染、真实模型 live 结构化计划和多进程生产矩阵。
- DeepSeek live 调用已生成完整 `spatial_overview_result` 和 8 个注册工具步骤；当前仍只证明规划结构，不把内存后端结果当作真实 GIS 证据。

## M66：端到端真实模型与跨入口证据（已完成）

- 真实 GIS live 测试显式要求 `SPATIAL_AGENT_LIVE_OPENAI=1`、`SPATIAL_AGENT_LIVE_GIS=1`，并使用 `spatial-agent-gis` conda 环境；区域 DEM、复合区域分析已通过，总览请求具备最多 3 次暂态重试的严格断言。
- 异步运行快照持久化最终 `geometry_evidence`，同步、异步轮询和服务重启后的 `result.geometry` 保持一致；新增几何/引用证据矩阵。
- Console 增加隔离 Chrome CDP 启动脚本和空间总览面板/地图分层 smoke；既有 smoke 支持 `CDP_URL` 和 `CONSOLE_URL`。
- 新增开放式空间澄清、跨区域对比全局评测契约；跨区域能力沿用现有 `buildability_comparison` scenario 和 API。
- M66 专项测试、离线全量 271 项、GIS 全量 271 项、Docker 生产 acceptance 和 Chrome CDP 联合验收均已通过。
- Docker 验收确认核心数据 `admin_areas`、`dem`、`land_use` ready；`roads`、`water` 作为可选数据缺失时报告 `core_ready_optional_partial`，不阻断核心能力。
- 真实 GIS 浏览器地图验收生成 59 条路径并支持洪山区选区；空间总览面板验证 8 个工具步骤、7 类数据来源和行政区/道路/水体三色图层。
- 异步同步、轮询和服务重启后的几何证据保持一致；M66 完成后下一阶段按产品能力、数据质量、真实模型、部署可靠性和用户体验五个维度重规划。

## M67：从受控演示到可扩展空间 Agent 工作流（已完成）

1. 产品能力：扩展空间总览为可配置工作流，支持用户选择分析目标、约束条件和输出证据，并保持开放式问题的澄清与安全边界。
2. 数据质量：补齐或提供可复现的武汉道路/水体数据卷，增加跨栅格 CRS/覆盖质量报告、数据版本和来源归因。
3. 真实模型：建立真实模型计划的脱敏回放、结构化输出修复、工具选择准确率和 token/延迟成本评测，明确 provider 暂态失败与代码失败。
4. 部署可靠性：完善生产 SQLite 多 worker 观测、作业超时/取消/重试、数据卷启动诊断和能力级 readiness；补充容器升级后的兼容性验收。
5. 用户体验：将 Console 结果区进一步改为 agent 驱动的动态视图，统一答案、轨迹、证据和地图的层级，增加降级状态与数据来源的可读解释。

M67 按最多 3 路并行实现并由主线统一集成。阶段联合验收结果：

- 数据 provenance 已进入数据集目录、健康报告和 runtime capability snapshot；来源、版本、署名和许可字段受 allowlist 与长度限制，旧配置保持兼容。
- 脱敏模型回放评测覆盖工具选择、DAG、结果类型、中文答案、token/延迟和 provider 错误分类；全局评测默认离线执行，不访问网络。
- SQLite 与内存异步作业均提供生命周期、排队/运行耗时、失败分类、取消和重启恢复观测；`/runs/{run_id}/observability`、`/runs/{run_id}/async` 和 `/metrics.async_jobs` 已接入服务入口。
- Console 结果证据按响应动态显示空间几何、运行时能力、数据来源、provenance 和降级说明；空间总览地图验证行政区、道路、水体三色分层。
- M67 专项 22 项、离线全量 293 项（35 项跳过）、GIS 全量 293 项（9 项跳过）、smoke、全局评测、Docker production acceptance 和串行 Chrome CDP 联合验收通过。
- Docker 验收确认核心数据 ready；道路/水体可选数据缺失明确报告为 `core_ready_optional_partial`，不阻断核心能力。

## M68 全局规划

1. 产品能力：把当前受控总览抽象为可配置工作流模板，补齐用户约束、证据选择和多轮修订的结构化契约。
2. 数据质量：继续完善武汉道路/水体可复现数据卷与 provenance 校验，并增加栅格对齐、覆盖和时间版本的可比较报告。
3. 真实模型：扩展脱敏回放到开放式空间问答、澄清和失败修复，建立模型规划质量基线与真实 provider 可选验收。
4. 部署可靠性：验证 SQLite schema 升级、多个生产 worker 的观测一致性、超时/取消边界和容器滚动重启后的作业恢复。
5. 用户体验：将答案、轨迹、证据和地图统一为按结果类型驱动的动态工作区，减少空面板并清晰呈现不可用与截断状态。

M68 继续最多拆分 3 个独立子任务；集成后必须执行离线、GIS、Docker、HTTP 和串行浏览器验收，再创建阶段版本。

## M68：配置化工作流、数据对齐证据与运行可靠性（已完成）

- 产品能力：新增受控工作流模板目录和严格校验，模板约束工具 allowlist、结果类型、必需条件、步骤上限与依赖 DAG；新增 `/workflows` API，并接入能力目录。
- 数据质量：新增 metadata-only 栅格对齐报告，区分 CRS、分辨率、原点、范围、尺寸、旋转变换、覆盖关系和缺失元数据；健康报告与 runtime capability snapshot 均暴露 `grid_alignment`，不读取像元、不伪造空间分析证据。
- 部署可靠性：增加 `SPATIAL_AGENT_ASYNC_WORKERS` 配置（1-16，默认 4），并将 SQLite 旧 schema 生命周期字段迁移、重复初始化和新任务创建纳入测试；内存模式会话也支持创建、列表、历史恢复、清空和删除。
- 用户体验与 API：内存会话与持久化会话遵循同一会话契约，文档补充工作流目录、worker 配置和对齐状态说明。
- M68 专项 47 项，另加 smoke 回归 1 项；离线全量 340 项（35 项跳过）、GIS 全量 340 项（9 项跳过）、smoke check 和全局评测严格模式通过；全局评测执行场景 8/8 通过、可选场景 3 项跳过。
- Docker Desktop 当前缺少 `dockerDesktopLinuxEngine` named pipe，`docker info` 无法连接，且 `com.docker.service` 服务项不可用；因此 M68 不宣称新镜像、容器 readiness 或 production acceptance 已通过。该外部环境缺口已记录在 `docs/agent-development-issues.md`。

## M69 全局规划

1. 产品能力：把工作流模板从“校验契约”推进到可编辑的约束表单、模板版本和计划修订；由同一模板驱动 Planner、Runtime、Console 和评测，保持未知空间问题进入澄清。
2. 数据质量：提供道路/水体数据卷 manifest、下载校验和版本锁定；将栅格对齐报告扩展为可执行的像元级对齐前置检查，并对真实数据覆盖缺口给出可操作诊断。
3. 真实模型：增加开放式问题的脱敏多轮回放，覆盖澄清补全、非法工具/参数修复、失败重试和结果类型选择；保留可选 live 基线并记录安全 token、延迟和 provider 错误分类。
4. 部署可靠性：补充多 worker 下的超时、取消、重复提交、滚动重启和 schema 迁移组合矩阵；恢复 Docker 后再执行新镜像、readiness 和容器重启验收。
5. 用户体验：将动态结果区收敛为答案、轨迹、证据、地图四个互相引用的视图，显示模板/约束、数据版本、对齐状态和降级原因，避免成功但无证据的空结果。

M69 最多拆分 3 路可独立验收的子任务：工作流编辑与计划契约、数据 manifest/对齐门控、模型回放与运行可靠性。主线统一公共 schema、runtime、result envelope 和 Console 集成；阶段完成后执行离线、GIS、HTTP、串行浏览器和 Docker（环境恢复后）验收，再创建 GitHub 版本。

## M70 全局规划

1. 数据质量：把原始栅格的 CRS/网格差异转化为可复现、可审计的分析就绪派生层，原始数据只读保留并由 manifest 锁定。
2. 产品能力：让真实建设候选筛选从门控状态进入真实像元统计和有限几何导出，同时保留 demo/规划合规边界。
3. 真实模型：为模型返回的建设筛选约束补充派生数据版本、对齐状态和可用性提示，避免模型把原始数据与分析就绪数据混淆。
4. 部署可靠性：验证派生数据卷挂载、manifest readiness 和派生文件变更后的完整性失败路径；Docker 恢复后纳入新镜像验收。
5. 用户体验：在答案、轨迹和地图证据中显示数据版本、目标 CRS、分辨率、对齐状态和候选像元统计。

M70 最多拆分 3 路独立任务；公共结果契约、数据 provenance 和 Console 证据由主线统一集成。

### M70：分析就绪栅格与证据闭环（已完成）

- 新增 `scripts/prepare_analysis_rasters.py`，使用武汉 13 区边界生成固定目标网格，将 DEM/土地利用派生为同一 CRS、分辨率、原点、范围和尺寸，输出 `analysis-ready-report.json`。
- 真实本机验证生成 `EPSG:32649`、30 米、4562×5277 网格；`grid_alignment=aligned`，派生 manifest 5 项完整 SHA-256 通过。
- 真实建设适宜性已通过派生配置执行：有效像元 576,040，候选像元 23,172，候选比例约 4.02%，候选 GeoJSON 可导出真实要素。
- `DatasetCatalog`、健康报告和 readiness 已绑定必需的分析就绪报告；缺失、非法 JSON、未对齐和派生输出失配均有失败路径和能力门控。
- runtime capability snapshot、Console 数据证据和中文答案显示派生版本、目标 CRS、分辨率与对齐状态；真实建设候选执行成功并返回 576,040 个有效像元、23,172 个候选像元。
- SQLite WAL 初始化增加多 worker 锁重试；Windows conda 中文 JSON 输出编码问题已记录，验收摘要使用 ASCII JSON。
- M70 专项 19 项、离线全量 369 项（41 项跳过）、GIS 全量 369 项（9 项跳过）、Smoke 和严格全局评测（8/8 场景、脱敏回放 2/2）通过。
- Docker Linux engine 仍未恢复，新镜像、生产 readiness/acceptance 和容器重启证据继续保持未宣称状态；真实派生数据留在 `D:\tmp\wuhan-gis`。

## M71 全局规划

1. 产品能力：把分析就绪栅格证据扩展到空间总览、道路/水体约束和多区域比较，统一候选像元、有限几何和版本引用。
2. 数据质量：增加派生报告、manifest、源数据版本绑定与变更检测，补充 nodata、边界和重采样策略证据。
3. 真实模型：让开放式问题的澄清和脱敏回放消费真实能力快照，验证模型不会绕过分析就绪门控。
4. 部署可靠性：Docker 恢复后完成新镜像、readiness、容器重启和生产 FastAPI 矩阵，继续验证 SQLite 多 worker 可靠性。
5. 用户体验：继续精简动态结果区，并为真实配置补浏览器 smoke，确保答案、轨迹、地图和降级说明一致。

M71 最多拆分 3 路并行；公共 schema、result envelope、provenance 和 Console 证据由主线统一集成。

### M71：比较与约束证据一致性（已完成）

- 阈值比较 `/comparisons` 和多区域比较 `/region-comparisons` 现在保留统一的 `analysis_ready` 摘要；每个结果行也绑定相同的派生版本、目标网格、对齐状态和数据就绪状态。
- 道路/水体约束建设筛选的中文答案引用分析就绪派生版本、目标 CRS、分辨率和网格对齐状态；Console 的阈值、多区域比较结果同步显示这些证据。
- 新增 M71 契约测试，覆盖比较 API 行级证据、约束答案和 Console 标记；离线全量 373 项通过、42 项跳过，GIS 全量 373 项通过、9 项跳过。
- `scripts/smoke_check.py` 通过；严格全局评测执行场景 8/8 通过、脱敏模型回放 2/2 通过。
- 真实武汉分析就绪配置验证通过：`analysis-ready-v1`、`EPSG:32649`、30 米、4562×5277、`grid_alignment=aligned`；洪山区 20° 候选 23,172 个，多区域比较返回洪山区 23,172 个、江夏区 59,045 个候选像元；道路/水体约束返回完成状态并引用同一证据版本。
- GIS 全量首次出现一次嵌套 smoke 的异步 artifact 引用时序失败；目标测试单独 5/5、单独 smoke 和完整 GIS 复跑均通过，验收编排竞争已记录到中文问题日志，不能据一次失败宣称业务回归。
- Docker Linux engine、生产新镜像/readiness、FastAPI 生产入口和真实模型 live 仍未获得新证据，继续作为后续外部验收边界。

## M72 全局规划

1. 产品能力：统一空间总览、比较、约束筛选和动态 Console 的结果 envelope、证据引用与地图图层状态，补真实配置浏览器端到端 smoke。
2. 数据质量：增加源数据与分析就绪派生层的版本绑定、变更检测、nodata/边界/重采样策略报告，并让 readiness 明确区分 metadata 校验和完整哈希校验。
3. 真实模型：用真实能力快照驱动开放式问题澄清和计划修复回放；在可用时执行 live GIS 模型基线，分别记录 provider、模型输出、工具门控和后端执行结果。
4. 部署可靠性：Docker Linux engine 恢复后构建当前提交镜像，执行数据卷挂载、readiness、容器重启、多 worker 异步恢复和生产 FastAPI acceptance。
5. 用户体验：让结果区默认空白、按结果类型动态出现，并把候选统计、数据版本、几何可用性和降级原因压缩为可扫描的证据摘要。

M72 最多拆分 3 路并行；数据质量、真实模型和部署验收分别保持边界，公共 result envelope、能力快照与 Console 由主线统一集成。阶段验收仍按“专项 -> 离线全量 -> Smoke -> GIS/live -> 全局评测 -> 部署/浏览器”串行收口。

### M72：源数据绑定与派生变更核验（已完成）

- 新增 `agent/analysis_ready_binding.py`，在生成分析就绪栅格时为行政区、DEM、土地利用源文件建立确定性的 SHA-256 绑定指纹。
- 新增 `scripts/verify_analysis_ready.py`，发布或换数时显式重算源文件指纹；源文件被修改、缺失或绑定版本不兼容时返回 `degraded`/`unavailable`，不把旧派生层继续当作可复现输入。
- `analysis-ready-report.json` 记录源绑定；健康报告只展示版本、指纹、数据集名称和 `recorded` 状态，不在普通 readiness 请求中重新读取大文件，也不向 API 暴露逐文件哈希。
- 派生配置保留有限源绑定元数据；旧 M70 报告和旧配置保持兼容，未包含绑定时不会被误判为新版本完整核验。
- 新增 M72 专项 3 项；离线全量 375 项通过、42 项跳过；GIS 全量 375 项通过、9 项跳过；Smoke 和严格全局评测 8/8 通过，脱敏模型回放 2/2 通过。
- 真实武汉源配置已重新生成分析就绪报告并通过显式 SHA-256 verifier：14 个源文件、`verified_files=14`、`mismatch_count=0`，指纹为 `sha256:b648973f4707b9cb63ecfeb9c680c692dd34cd491ec8e8fed2b4ffbea6584f5f`。
- 当前运行时绑定 manifest 仍明确是 `verification_mode=metadata`、`hashes_verified=false`；完整哈希通过 verifier 单独证明。Docker Linux engine、生产 acceptance、真实模型 live 和真实配置浏览器 smoke 继续保留为后续边界。

## M73 全局规划

1. 产品能力：把源绑定、派生版本、GeoJSON 几何和地图图层状态统一纳入总览/比较/约束结果 envelope，补真实配置浏览器 smoke。
2. 数据质量：将源绑定核验结果接入发布检查与能力快照，补 nodata、边界范围、重采样策略和 derived output manifest 的联动校验。
3. 真实模型：基于真实能力快照执行开放式问题澄清、非法计划修复和 live GIS 模型基线，区分 provider 错误、计划校验和后端门控失败。
4. 部署可靠性：Docker Linux engine 恢复后构建当前版本，执行数据卷、manifest/analysis-ready readiness、重启恢复、多 worker 与 FastAPI production acceptance。
5. 用户体验：继续保持结果面板按类型动态出现，缩短证据摘要并让数据版本、几何状态和降级原因可直接追溯到轨迹步骤。

M73 最多拆分 3 路并行；源绑定/能力快照、模型回放、部署验收各自保持边界，公共结果契约由主线统一集成。

### M73：源绑定证据传播（已完成）

- 运行时能力快照的 `analysis_ready`、DEM/土地利用 `data_evidence`、比较 API 摘要和 Console 证据区现在复用同一份受控 `source_binding`：版本、SHA-256 指纹、核验模式、源数据集和状态。
- 不把逐文件哈希或本地绝对路径放入 API；运行时继续明确 `manifest.verification_mode=metadata`，完整 SHA-256 仍由发布前 verifier 提供证据。
- 新增 M73 专项 3 项，覆盖能力快照、比较结果和 Console；兼容回归 17 项通过。
- M73 变更后离线全量 379 项通过、42 项跳过；GIS 全量 379 项通过、9 项跳过；Smoke、严格全局评测 8/8 和脱敏模型回放 2/2 通过。
- 真实武汉能力快照返回 `analysis-ready-v1`、`EPSG:32649`、`aligned` 以及源绑定指纹 `sha256:b648973f4707b9cb63ecfeb9c680c692dd34cd491ec8e8fed2b4ffbea6584f5f`，运行时数据就绪状态为 `ready`。

## M74 全局规划

1. 产品能力：将源绑定、manifest、GeoJSON 几何和地图图层状态纳入空间总览/比较/约束的统一证据摘要，并补真实配置浏览器 smoke。
2. 数据质量：校验 nodata、边界范围、重采样策略、派生输出 manifest 和源绑定之间的一致性，形成可审计的发布报告。
3. 真实模型：基于真实能力快照做开放式澄清、计划修复和 live GIS 模型基线，记录 provider 错误与本地门控的分界。
4. 部署可靠性：Docker Linux engine 恢复后构建当前提交镜像，执行数据卷、readiness、重启恢复、多 worker 和 FastAPI production acceptance。
5. 用户体验：让结果区按响应类型动态渲染绑定指纹、完整性状态、几何可用性与降级原因，避免静态面板抢占空间。

M74 最多拆分 3 路并行；数据质量、真实模型和部署验收保持边界，结果 envelope 与 Console 集成由主线统一完成。

### M74：派生策略与边界证据（已完成）

- 分析就绪报告新增 `derivation`：DEM 使用 `bilinear`、土地利用使用 `nearest`，分别记录 nodata 值，并记录武汉 13 区边界范围、源 CRS 和行政区数量。
- 健康检查对新报告执行重采样策略、nodata 类型/有限性和边界证据校验；非法策略会将必需分析就绪状态置为 `degraded`，进而将 `data_readiness` 置为 `not_ready`。
- 旧 M70 报告没有 `derivation` 时保持兼容；新报告只输出受控摘要，不读取像元验证 nodata 内容，完整内容由生成报告和发布前 manifest/verifier 共同提供。
- 新增 M74 专项 2 项；离线全量 381 项通过、42 项跳过；GIS 全量 381 项通过、9 项跳过；Smoke 和严格全局评测 8/8 通过，脱敏模型回放 2/2 通过。
- 真实武汉 readiness 返回 `bilinear/nearest`、DEM `-9999`、土地利用 `0`、源 CRS `EPSG:4490`、13 个行政区，状态为 `ready`；源绑定 verifier 14/14、0 mismatch。
- Docker Linux engine、生产 acceptance、真实模型 live 和真实配置浏览器 smoke 仍没有新证据，继续保持未宣称状态。

## M75 全局规划

1. 产品能力：把 nodata/边界/重采样/源绑定/manifest 摘要接入所有空间结果和地图图层，并完成真实配置浏览器 smoke。
2. 数据质量：增加派生输出与 manifest 的显式一致性报告，区分 metadata 读取、源绑定 SHA-256 和输出文件 SHA-256 三类证据。
3. 真实模型：执行真实能力快照驱动的开放式澄清、计划修复和 live GIS 模型基线，保留 provider 与本地执行分层错误。
4. 部署可靠性：Docker Linux engine 恢复后构建当前版本并验收数据卷、readiness、重启、多 worker 和 FastAPI 生产接口。
5. 用户体验：动态证据区按结果类型展示完整性、几何可用性和数据限制，确保地图、轨迹、答案引用同一个运行快照。

M75 最多拆分 3 路并行；数据质量、真实模型和部署验收保持独立，统一结果契约与 Console 由主线集成。

### M75：派生输出 manifest 一致性（已完成）

- 健康报告将分析就绪报告中的 DEM/土地利用输出文件名与 manifest 的受控 basename 列表进行比对，返回 `output_manifest.status`、匹配结果、核验模式、完整哈希状态和 mismatch 数。
- 运行时能力快照、比较结果摘要和 Console 复用输出 manifest 证据；当前真实配置显示输出匹配 `ready`，但完整哈希仍诚实显示 `hashes_verified=false`，由显式 verifier 单独证明。
- 新增 M75 专项 4 项，覆盖直接匹配、失配、basename 健康摘要、能力快照和比较结果；离线全量 385 项通过、42 项跳过，GIS 全量 385 项通过、9 项跳过。
- Smoke、严格全局评测 8/8、脱敏模型回放 2/2 和真实武汉 readiness 均通过；真实派生 DEM/土地利用均与 manifest 匹配，`data_readiness=ready`。
- 修复一次真实配置暴露的集成缺口：manifest 校验摘要原先没有保留文件名，导致输出一致性被误报为 unavailable；现仅保留 basename，避免暴露路径并保持可审计。
- Docker Linux engine、生产 acceptance、真实模型 live 和真实配置浏览器 smoke 仍无新证据，继续不宣称通过。

## M76 全局规划

1. 产品能力：完成动态结果/地图工作区对完整性、源绑定、输出 manifest 和几何证据的统一展示，并执行真实配置浏览器 smoke。
2. 数据质量：建立发布前三层校验报告：metadata、源绑定 SHA-256、派生输出 SHA-256；补 nodata 统计与边界覆盖关系的可选像元级核验。
3. 真实模型：执行真实能力快照驱动的开放式澄清、非法计划修复和 live GIS 总览基线，记录完整错误分层与 token/延迟指标。
4. 部署可靠性：Docker Linux engine 恢复后构建当前提交版本，执行生产数据卷、readiness、重启、多 worker 异步和 FastAPI acceptance。
5. 用户体验：把证据摘要压缩为可扫描的状态行，并让轨迹步骤、答案和地图点击互相定位到同一个运行引用。

M76 最多拆分 3 路并行；浏览器/结果展示、真实模型和部署验收保持边界，数据证据与公共 result envelope 由主线统一集成。

### M76.1：结果区三层发布证据与真实 GIS 浏览器验收（已完成）

- Console 新增“发布完整性”证据卡，统一显示元数据/目标网格、源绑定 SHA-256、输出 manifest 和几何结果的边界状态；输出文件只显示受控 basename，不泄露本机路径或逐文件哈希。
- 运行时能力快照的 DEM/土地利用数据证据和比较 API 均保留输出 manifest 的 `reported`、`manifest`、`matched` 摘要，Console 可直接定位每个派生输出是否与发布记录匹配。
- `scripts/console_overview_smoke.js` 增加三层发布证据 fixture；内存总览浏览器 smoke、真实武汉 GIS 总览 smoke 和真实 GIS 建设候选地图 smoke 均通过。真实 GIS 总览产生 79 个空间要素并明确标记 GeoJSON 截断状态。
- M76.1 专项 3 项、离线全量 388 项（42 项跳过）、GIS 全量 388 项（9 项跳过）、Smoke、严格全局评测 8/8 均通过；真实配置 `health=ready`、`data_readiness=ready`、输出 manifest `ready`，运行时仍诚实标记为 metadata-only。
- GIS 全量首次执行再次出现一次既有异步 artifact 引用时序失败；目标测试单独及连续 5 次、GIS smoke、完整复跑均通过，未修改业务逻辑掩盖该验收竞争。

### M76.2 全局下一步

1. 数据质量：增加显式发布报告，把 metadata、源绑定 SHA-256、派生输出 SHA-256、nodata 与边界覆盖证据汇总为可下载 artifact，并区分启动 readiness 与发布校验。
2. 真实模型：用真实能力快照执行开放式澄清、非法计划修复和 live GIS 总览，记录 provider 错误、计划校验、工具门控、后端失败和 token/延迟指标。
3. 部署可靠性：Docker Linux engine 恢复后构建当前版本，验收数据卷、readiness、重启恢复、多 worker、FastAPI 和发布报告接口。
4. 用户体验：让发布证据、轨迹步骤、答案、地图图层和 GeoJSON 下载引用同一个运行 ID，并补失败/截断/换数后的浏览器状态验收。

M76.2 仍最多拆分 3 路并行；发布报告和 result envelope 由主线统一，真实模型与 Docker 验收分别隔离。

### M76.2.1：三层发布校验报告（已完成）

- 新增 `agent/release_evidence.py` 和 `scripts/release_evidence.py`，显式编排 metadata、源绑定 SHA-256、当前派生输出 SHA-256 三层校验；报告只输出受控摘要，不输出绝对路径或逐文件哈希。
- 开发 HTTP 与生产 FastAPI 均提供 `GET /release-evidence`；Console 发布完整性卡片提供下载链接。缺失配置、manifest、源绑定和输出失配均返回结构化状态与 mismatch，不伪装成 ready。
- 正确处理派生配置的源层/派生层分离：从原始 source binding 重建源文件视图，再用当前 catalog 校验派生输出。
- M76.2.1 专项 6 项、离线全量 391 项（42 项跳过）、GIS 全量 391 项（9 项跳过）、Smoke、严格全局评测 8/8、真实 API 报告和真实配置浏览器 smoke 均通过。
- 真实武汉报告：总体 `ready`；source SHA-256 14 个文件、manifest 5 个文件、派生输出 SHA-256 2 个文件，均 0 mismatch。运行时 readiness 仍保持 metadata-only 语义。

### M76.2.2 全局下一步

1. 真实模型：执行真实能力快照驱动的开放式澄清、非法计划修复和 live GIS 总览基线，沉淀安全的 provider/计划/工具/后端错误分类及 token/延迟指标。
2. 部署可靠性：Docker Linux engine 恢复后构建当前版本，验收生产数据卷、`/health/ready`、发布报告、重启恢复、多 worker 和 FastAPI acceptance。
3. 用户体验：把发布报告的运行 ID、答案、轨迹、GeoJSON 和地图图层引用贯通，并补换数、失配、截断和失败状态的浏览器验收。

M76.2.2 仍最多拆分 3 路并行；真实模型、生产部署和 Console 体验边界清晰，公共 result envelope 由主线统一。

### M76.2.2：真实模型与 GIS 基线（已完成）

- 新增 `evaluation/live_baseline.py` 和 `scripts/live_baseline.py`。入口必须显式使用 `--allow-network`，并设置 live 模型/GIS 环境变量；默认单元测试和 CI 不访问网络。
- 基线从真实运行时能力快照读取数据就绪状态、分析就绪版本、目标网格对齐状态和能力工具清单；报告只保留受控状态，不输出配置路径、原始模型响应、URL、错误正文或密钥。
- 真实武汉验收：能力快照 `health=ready`、`data_readiness=ready`、`analysis_ready=ready`、`grid_alignment=aligned`；地下管线三维风险请求正确返回结构化澄清；空间总览 8 步真实 GIS 执行完成，结果类型为 `spatial_overview_result`，工具覆盖、依赖 DAG 和中文答案均通过。
- 计划修复/澄清脱敏回放 2/2 通过；live 两个请求 2/2 通过，合计 5051 token，延迟 3706.899–11176.822 ms，provider 错误 0，重试 0。
- M76.2.2 专项 3 项、离线全量 394 项（42 项跳过）、GIS 全量 394 项（9 项跳过）、Smoke、严格全局评测 8/8 和最终 live 基线均通过。

### M76.2.3 全局下一步

1. 部署可靠性：Docker Linux engine 恢复后构建当前提交，执行真实数据卷、`/health/ready`、发布证据、重启恢复、多 worker 和 FastAPI acceptance；宿主机不可用时保持分层未验证状态。
2. 产品能力与体验：贯通运行 ID、发布报告、答案、轨迹、GeoJSON 和地图图层，补充换数后 degraded/unavailable、几何截断和失败重试的 Console 浏览器验收。
3. 真实模型：把 live 基线纳入可选阶段验收，保留能力快照驱动澄清、计划质量和安全 provider 指标；扩展到真实建设筛选与跨区域比较前先定义工具多重调用和结果证据契约。

M76.2.3 仍最多拆分 3 路并行；Docker、Console 和真实模型验收保持边界，运行 ID/result envelope 与数据证据由主线统一集成。

阶段规划约束：后续每次整体重规划都必须先复盘项目全局能力矩阵（产品、架构、数据质量、真实模型、部署、体验、测试），再确定局部实现任务。不得让最近一次数据问题、工具错误或页面缺陷单独决定下一阶段目标。

规划执行门槛：阶段计划必须先说明完整 Agent 系统的当前闭环、主要系统级缺口、模块依赖和跨入口验收方式；数据集、单个工具、模型调用或页面问题只能作为实现手段或风险项，必须绑定到产品/架构/部署/体验目标后才能进入任务拆分。阶段完成后，先用全局能力矩阵复盘结果，再决定下一阶段，不得沿着最近修复点自然追加局部任务。

### M76.2.3：运行证据索引与跨入口体验（已完成）

- `result_contract` 新增 `lineage` 索引，统一描述运行 ID、答案、轨迹、artifact、GeoJSON、地图图层和当前数据卷发布证据；保留原有顶层字段与引用兼容性。
- 同步、异步、轮询、服务重启和失败重试路径统一在导出字段准备完成后构建 result envelope，避免轨迹/导出证据在恢复后缺失或状态不一致。
- Console 结果证据区立即渲染 lineage，并在运行时能力快照返回后增量补全；总览 smoke 验证运行 ID、地图三色图层和发布报告链接，地图 smoke 验证 57 个路径和要素选择。
- 新增运行 lineage、跨入口稳定性和浏览器索引测试；M76.2.3 专项 3 项、离线全量 397 项（42 项跳过）、GIS 全量 397 项（9 项跳过）、Smoke、严格全局评测 8/8、总览/地图/健康/会话/清空浏览器 smoke 均通过。
- 本阶段的下一步规划遵循全局约束：部署、产品闭环、模型扩展和数据证据并列评估，不把 lineage 实现收窄成单个数据集任务。

### M76.2.4 全局下一步

1. 产品与架构：把 lineage 继续贯通异步观测、比较 API、失败重试和会话历史，形成同一运行 ID 下可回溯的完整 Agent 交互闭环。
2. 真实模型：基于稳定的结果证据契约扩展建设筛选、道路/水体约束和跨区域比较 live 基线，分别验证模型计划、工具门控、后端执行和用户答案，不把模型调用当作孤立 demo。
3. 部署可靠性：Docker Linux engine 恢复后构建当前版本，完成生产 readiness、数据卷、重启、多 worker、FastAPI 和发布报告 acceptance；同时保留宿主机边界证据。
4. 数据与测试支撑：继续维护武汉数据 provenance、对齐和发布完整性，但只作为上述产品能力和部署闭环的证据层；扩展端到端矩阵与浏览器状态覆盖。

M76.2.4 仍最多拆分 3 路并行；规划先按全局能力矩阵排序，再拆分局部实现，不能由单一数据细节决定阶段目标。

### M76.2.4：跨入口 lineage 闭环（已完成）

- `result_contract.py` 新增统一运行 lineage、历史摘要 lineage 和比较集合 lineage；异步观测、会话历史、阈值比较、多区域比较和 retry 均能回到受控运行引用。
- `AgentRunResult` 增加持久化 `retry_count`，结果契约仅在实际发生 retry 时生成 retry 引用；同步/异步/重启结果归一化保持一致。
- 新增 4 项 M76.2.4 专项和开发 HTTP 验收；离线 401 项通过（42 项跳过），GIS 401 项通过（9 项跳过），Smoke、严格全局评测 8/8 和脱敏回放 2/2 通过。
- 修复 Windows worker 存活探测在权限/API 查询失败时误报死亡，造成同一 SQLite job 重复接管和运行快照状态撕裂；三 worker 场景连续 12 次通过。
- Docker Linux engine 与生产 acceptance 仍是外部环境未验证项，保持分层记录。

### M76.3 全局规划

1. 产品体验：Console 历史、比较和 retry 结果直接显示 lineage 导航，统一回到答案、轨迹、地图、GeoJSON 和发布证据。
2. 架构部署：版本化开发/生产 HTTP 结果契约与 observability 契约；Docker 恢复后完成数据卷、readiness、多 worker、重启和 FastAPI production acceptance。
3. 真实模型：在稳定结果证据之上扩展建设筛选、道路/水体约束、跨区域比较 live 基线，区分模型、计划、门控、后端和答案证据。
4. 数据测试：维护 provenance、栅格对齐、manifest 和发布报告作为系统证据层，覆盖换数失配、截断、retry 和部署恢复矩阵。

M76.3 及后续阶段不拆分并行任务；先做全局能力矩阵，再按依赖顺序实现，任何局部数据问题都必须绑定到上述系统级目标。

### M76.3.1：Harness 与上下文工程（已完成）

- 新增 `agent/context_engineering.py`，提供版本化、限长、结构化裁剪、敏感字段过滤和请求哈希；超长上下文在对象层裁剪，保持 JSON 合法。
- `AgentRuntime` 统一构建上下文并把安全摘要写入 `AgentRunResult.context_evidence`；LLMPlanner 以独立的可信运行时元数据接收上下文，旧 Planner 签名继续兼容。
- 上下文摘要已贯通内存、SQLite 恢复、artifact、result envelope 和 Console；前端显示版本、长度和是否发生预算裁剪，不展示原始上下文。
- M76.3.1 专项 7 项通过；离线全量 408 项通过、42 项跳过；Smoke 通过。GIS 全量、Docker Linux engine、FastAPI production acceptance 和新的 live 模型基线尚未在本子阶段重新验证。
- 本阶段完成 Harness/上下文工程的最小闭环，但还没有把会话摘要、能力快照和工具结果按意图纳入上下文，也没有完成上下文成本与污染评测。

### M77 全局规划

### 总体 Goal 重组说明

从当前阶段起，项目主线调整为建设通用、可组合、可解释的空间智能体。系统通过独立请求建模层抽取空间实体、任务意图、数据需求、约束条件和输出证据，再由能力目录与工具 schema 动态发现并组合多工具 DAG。行政区、数据集和分析类型是运行时参数与能力声明，不应形成大量区域专用分支。

验收重点从“某个洪山区问句能否执行”提升为“同一套 Planner/Runtime/ToolRegistry 契约能否迁移到不同区域、不同数据集、单任务和多任务组合”。洪山区综合空间分析保留为复杂回归样例，不再作为总体设计中心。

1. 产品与体验：历史、比较和 retry 结果点击后打开原运行详情，直接定位答案、轨迹、地图、GeoJSON、发布报告和上下文证据，不重新调用模型。
2. 架构与 Harness：版本化 HTTP/result/observability 契约，建立跨同步、异步、SQLite 恢复、artifact 和 Console 的一致性验收入口。
3. 上下文与真实模型：按意图受控加入会话摘要、能力快照和工具结果；增加上下文不足、污染、超长、成本和 token 评测，并在稳定契约上扩展建设筛选、道路/水体约束和跨区域比较 baseline。
4. 数据质量：继续使用 provenance、栅格对齐、manifest 和发布报告作为上下文与结果的证据来源，覆盖换数失配和降级状态，不把单个数据集作为阶段中心。
5. 部署可靠性：Docker Linux engine 恢复后执行当前版本数据卷、readiness、多 worker、重启恢复和 FastAPI production acceptance；保留宿主机不可用时的分层证据。

M77 不拆分并行任务，按依赖顺序单线程执行；上下文/result envelope/Console 集成由主线统一，真实模型与部署验收保持边界。阶段验收仍按离线 -> Smoke -> GIS -> 全局评测 -> 浏览器/生产入口顺序执行。

### M77：通用请求建模与组合式空间分析（已完成）

- 新增 `agent/request_model.py`：独立中间表示抽取空间实体、任务意图、数据需求、约束条件和输出证据；`parse_spatial_request` 只解释请求文本，不做规划或执行声明。
- 新增 `agent/capability_routing.py`：声明式能力路由，从请求事实选择能力 id，不构建 TaskPlan；计划组合仍留在 `rule_planning.py`，避免实体识别、意图判断和工具编排耦合在单个规划器分支中。
- `agent/planner.py` 瘦身为确定性兜底 facade（约 569 行规则分支收敛为 51 行适配层），`RuleBasedPlanner` 与 `LLMPlanner` 继续产出同一 `TaskPlan` 契约。
- 新增组合式 `spatial_analysis_result` 结果类型：能力目录、工作流模板、AnswerComposer 中文答案（含失败/阻塞步骤报告）同步接入；复杂请求如"请对洪山区进行综合空间分析……"路由到 `composed_spatial_analysis` 并生成 9 步受控 DAG。
- 上下文工程：`ContextBuilder` 新增 `spatial_request` 段（受控、脱敏、非逐字），Runtime 构建上下文时注入请求事实；运行快照保留 `context_evidence`。
- 异步可靠性：移除 `run_async` 提交前的 runtime 预初始化，慢 runtime 初始化不再阻塞异步提交线程；新增回归测试验证提交快速返回、终态由 worker 写入。
- Console：结果区、聊天、证据卡、地图与工作台设置重构为统一设计系统（CSS 变量、状态色、动效），保留全部 JS 函数与 DOM 契约；桌面工作台布局与移动端堆叠均通过浏览器验证。
- M77 验证：离线全量 417 项通过（42 项跳过）、`scripts/smoke_check.py` 通过、严格全局评测 8/8 + 脱敏模型回放 2/2 通过、console 浏览器 smoke（overview/health/clear/session）4/4 通过；Docker Linux engine 与真实模型 live 仍为外部环境边界，未宣称新证据。

### M69 当前实现进展

- 工作流模板已增加语义版本、约束规格（字符串/数值/整数/布尔/枚举及边界）、证据选项和默认选择；计划校验输出模板版本、归一化约束与证据。
- 新增 `POST /workflows/{template_id}/validate` 和 `POST /workflows/{template_id}/revise`，开发 HTTP 与生产 FastAPI 入口均接入；修订只合并声明的约束并重新经过模板、schema 和 DAG 校验。
- 新增 `agent/dataset_manifest.py` 和 `scripts/dataset_manifest.py`，支持相对路径、文件大小、SHA-256、数据类型和受控 provenance 的确定性 manifest；配置 manifest 后健康检查执行轻量路径/大小/provenance 校验。
- 全局评测新增脱敏多轮模型回放，覆盖澄清补全和非法计划修复；当前 M69 相关专项测试和全局回放已通过，尚未完成 Console 动态编辑、武汉 manifest 生产配置、可靠性组合矩阵及 Docker/live 验收。

### M69.1：工作流运行绑定与像元对齐门控（已完成）

- Console 通过 `GET /workflows` 动态生成工作流下拉、约束字段和证据选项；发送前调用模板校验接口，用户选择的 `land_use` 等参数会实际改变 Planner 生成的工具参数。
- `workflow` 运行上下文贯通开发/生产 HTTP、同步/异步提交、Planner、Runtime、内存状态和 SQLite 服务重启恢复；运行前按模板重新校验工具 allowlist、结果类型和依赖 DAG。
- 联合 DEM/土地利用像元工具增加 `grid_alignment=aligned` 门控，修复文件覆盖 ready 被误当作像元可对齐的问题；对应问题已记录在中文开发问题日志。
- 修复无工作流请求向旧 Runtime 替身传递 `workflow=None` 的兼容性回归，异步几何证据与 smoke 全量回归恢复。
- 验证：M69.1 专项 22 项通过；工作流浏览器交互通过；`scripts/smoke_check.py` 通过，内嵌离线全量 355 项（35 项跳过）；默认不访问真实模型。
- 外部环境仍未提供 Docker Linux engine，因此新镜像、readiness、生产 acceptance 和 live provider 不纳入本子阶段通过证据。

### M69.2：武汉 manifest 正式绑定与完整性证据（进行中）

- `DatasetCatalog` 支持字符串或结构化 manifest 配置，并支持 `manifest_required`；本地绑定配置由 `scripts/bind_dataset_manifest.py` 生成，不把机器路径写入仓库。
- manifest 校验明确区分启动时 metadata 检查与显式 SHA-256 检查；缺少哈希时完整校验失败，不再把元数据结果误报为完整性证据。
- runtime capability snapshot 暴露 manifest 状态、校验模式、已核对文件数和 `data_readiness`；生产入口可通过 `SPATIAL_AGENT_REQUIRE_DATASET_MANIFEST=1` 阻止缺失或不匹配的必需 manifest。
- 当前本机武汉真实数据已生成 16 个文件的 manifest，完整 SHA-256 核验 `ready`，并输出到仓库外的 verification evidence；DEM/土地利用像元网格仍因真实元数据不一致保持门控。
- SQLite 多 worker 组合矩阵新增 3 worker 幂等提交、超时终态重放、取消/超时重启接管和滚动重启结果复用；同时修复直答计划绕过取消/超时检查的问题。
- 离线全量 363 项通过（35 项跳过），GIS 全量 363 项通过（9 项跳过），Smoke 和全局严格评测通过；真实武汉 manifest 16 文件完整 SHA-256 通过，真实 DEM 元数据和道路/水体摘要调用通过。
- Docker Linux engine 仍因宿主机 `dockerDesktopLinuxEngine` named pipe 缺失无法获得新镜像/容器验收证据；FastAPI 生产依赖在当前 GIS Python 中未安装，生产入口测试按环境跳过。

## M65：生产异步、模型执行一致性与总览结果体验（已完成）

- 增加录制模型响应回归，验证空间总览 8 步计划、依赖 DAG、`$from` 绑定和 ToolRegistry 实际执行；默认测试不访问网络。
- 修复并发异步首次提交被误标为幂等复用的问题；增加多 worker 提交、独立轮询和 FastAPI 入口幂等契约测试。
- 修复 Windows 已退出 worker 被误判为存活、导致重启恢复跳过的问题；增加 claim 后崩溃、服务重启接管回归测试。
- Console 为 `spatial_overview_result` 增加紧凑摘要面板，显示步骤数、数据来源数、空间要素数和几何证据状态；已有多区域对比能力纳入全局验收，不重复定义新协议。
- M65 专项测试、全量离线/GIS、Docker 和 production acceptance 已通过，并已推送 `1fbc4cc`。

## M78 全局规划：架构债清理（P1）

承接 M77 通用化重组，本阶段清理架构债，目标是让"可替换、可测试、可观测"的声明与代码实际一致，按依赖顺序单线程执行，不拆分并行任务：

1. **能力契约对齐（M78.1）**：`capability_routing` 的路由 id 与 `capability_catalog` 的能力 id 对不上（`composed_spatial_analysis`/`terrain_land_use`/`zonal_vector_summary`/`constrained_buildability` 等与 catalog 的 `spatial_analysis`/`zonal_terrain_land_use`/`vector_summary`/`constrained_buildability_screening` 漂移，且 `dataset_health`/`raster_statistics`/`legacy_road_slope`/`admin_raster_composite`/`vector_relation`/`vector_query` 未在 catalog 声明）。统一为 catalog 单一事实源：路由只消费 catalog 能力 id，缺失能力补 catalog 声明，全局评测按 catalog id 校验。
2. **service.py 拆分（M78.2）**：`agent/service.py`（约 1183 行）是上帝对象，且反向依赖根目录 `run_demo.py` 的 `build_runtime`（分层倒挂）。按职责拆分为 runtime 工厂（`agent/runtime_factory.py`，供 run_demo/HTTP/评测共用）、同步运行、异步作业与恢复、会话、对比、观测、格式化与几何证据模块；`AgentService` 保留为门面。
3. **双 HTTP 入口统一（M78.3）**：`serve_api.py`（标准库）与 `production_api.py`（FastAPI）的端点参数映射、异常映射大量重复，且错误码不一致（如 create_session 503 vs 400）。收敛为共享的请求处理层（参数归一化 + 错误分类），两个入口只做框架适配；消除重复实现。
4. **结构化错误契约（M78.4）**：错误响应目前只有 `{"error": str}`，无错误码/分类；`failure_category`（timeout/provider/planning/tool/execution）只存在于观测层。提升为统一结构化错误契约（HTTP 错误响应与运行结果都带 `error.code`/`error.category`），并覆盖同步、异步、轮询与恢复路径。

阶段验收纪律不变：每个子阶段完成全量离线测试、Smoke、严格全局评测、console 浏览器 smoke，更新 milestones/task-resume 文档后提交推送；Docker Linux engine 与真实模型 live 保持外部边界，不宣称新证据。

### M78.1：能力契约对齐（已完成）

- `agent/capability_catalog.py` 补齐 6 个实际可路由但未声明的能力：`dataset_health`、`raster_statistics`、`vector_query`、`vector_relation`、`legacy_road_slope`、`admin_raster_composite`（含工具、结果类型、环境和数据层声明）。
- `agent/capability_routing.py` 的 4 个漂移 id 收敛到 catalog 命名：`composed_spatial_analysis -> spatial_analysis`、`terrain_land_use -> zonal_terrain_land_use`、`zonal_vector_summary -> vector_summary`、`constrained_buildability -> constrained_buildability_screening`。
- `agent/rule_planning.py` 的 builder 注册表与路由 id 同步；`test_m77_request_model.py` 断言更新。
- 新增 `tests/test_m78_capability_contract.py` 契约测试：路由 id ⊆ catalog id、builder 覆盖每个路由 id、无孤儿 builder、全局评测用例的 `capability_id` 全部存在于 catalog。
- M78.1 验证：离线全量 422 项（42 跳过）、Smoke、严格全局评测 8/8、console 浏览器 smoke 4/4 通过。

### M78.2：service.py 拆分与分层修复（已完成）

- 新建 `agent/runtime_factory.py` 承载 `build_runtime`（planner/backend → AgentRuntime），`run_demo.py` 改为 re-export，`agent/service.py` 不再导入根目录 demo 脚本，**分层倒挂消除**（`agent/` 包内 0 处 `from run_demo import`）。
- 按职责拆分辅助层：`agent/service_async.py`（异步作业观测契约、failure 分类、进程存活、时序工具）、`agent/service_format.py`（结果 envelope、几何证据、请求/工作流归一化）、`agent/service_sessions.py`（会话校验、历史 lineage、runtime key）。
- `agent/service.py` 从 1183 行减至约 730 行，`AgentService` 保留为门面：公开方法签名与行为不变，内部委托给上述模块。
- 新增 `tests/test_m78_service_split.py` 契约测试：agent 包不导入 run_demo、门面委托到聚焦模块、runtime_factory 共享、公开方法齐全。
- M78.2 验证：离线全量 426 项（42 跳过）、Smoke、严格全局评测 8/8、console 浏览器 smoke 4/4 通过。

### M78.3：双 HTTP 入口统一（已完成）

- 新增 `agent/api_contract.py` 共享请求处理层：`run_kwargs`/`async_run_kwargs`/`retry_kwargs`/`cancel_kwargs`/`comparison_kwargs`/`region_comparison_kwargs` 统一 payload 归一化，`workflow_action_result` 统一 workflow validate/revise（原两份实现完全重复），`error_status`/`error_body` 统一异常→状态码映射。
- `serve_api.py` 与 `production_api.py` 的 POST 路径全部委托共享层；错误码收敛（create_session 统一 503，get_run/observability 统一 404，其余 ValueError 400，未知异常 500）。
- 保留 production 特有的 `/health/ready` GIS/manifest 门控与 artifact 安全路由；默认环境无 FastAPI 时 production 入口测试继续按环境跳过。
- 新增 `tests/test_m78_http_contract.py`：双入口源码都导入共享层、payload 映射一致、错误码一致、dev POST 路径不硬编码状态码。
- M78.3 验证：离线全量 430 项（42 跳过）、Smoke、严格全局评测 8/8、console 浏览器 smoke 4/4、dev 服务关键端点实测（run/会话/错误输入/workflow）通过。

### M78.4：结构化错误契约（已完成）

- `agent/api_contract.py` 新增 `error_response(exc, not_found, service_unavailable)`：错误响应统一为 `{"error": 消息, "error_code": invalid_request|not_found|unavailable|internal_error, "error_category": provider|planning|tool|timeout|invalid_input|execution}`；`error` 字段保持向后兼容。
- `serve_api.py` 的 GET/POST/DELETE 异常路径与 `production_api.py` 全部走结构化错误；do_GET 硬编码的路由 404 保留 `{"error": ...}` 简洁形式。
- 运行结果契约：`service_format._attach_error_category` 为失败运行（REJECTED/FAILED/TIMED_OUT/CANCELLED/NEEDS_CLARIFICATION 及按文本分类的 provider/planning/tool）附加 `error_category`，贯通 `run`/`retry`/`get_run`/异步轮询结果；成功结果不伪造该字段。
- 新增 M78.4 断言：HTTP 错误码/分类一致、拒绝运行结果带 `error_category=rejected`、成功结果无该字段。
- M78.4 验证：离线全量 432 项（42 跳过）、Smoke、严格全局评测 8/8、console 浏览器 smoke 4/4、dev 服务实测（400/404 结构化错误、REJECTED 结果分类）通过。

## P1 架构债清理复盘（M78 完成）

七维全局矩阵复盘：

- **架构**：能力契约收敛到 catalog 单一事实源；`service.py` 1183→约 740 行并解除 `run_demo` 反向依赖；双 HTTP 入口共享 `api_contract`；错误契约结构化。四个子阶段均带契约测试锁定。
- **产品能力**：能力目录补全 6 个可路由能力，开放式空间问题的澄清与能力展示更完整；结构化错误让前端能按 `error_code`/`error_category` 分支处理而非解析字符串。
- **数据质量 / 部署可靠性**：证据链与 SQLite 异步链路行为不变（全量回归证明），未引入新边界。
- **真实模型**：live 基线仍为外部环境边界，未宣称新证据。
- **前端体验**：console 浏览器 smoke 4/4 通过，前端契约未受影响。
- **测试**：432 项离线（+10 项 M78 契约测试），覆盖能力契约、服务拆分、双入口一致性、结构化错误。
- **遗留风险**：`AgentService` 仍是门面但内部状态多（runtime 缓存/异步作业字典/SQLite 双模式）；作业级 wall-clock 超时与周期 reaper 未做；真实模型 live 与 Docker 生产验收仍依赖外部环境。

M78 已推送版本：`8e391e7`（M78.1）、`853d55c`（M78.2）、`5255e0b`（M78.3）、`b7988ae`（M78.4）。

## M79 全局规划（P2 产品闭环）

按依赖顺序单线程执行，不拆分并行任务：

1. **lineage 导航贯通**：历史、比较、retry 结果点击后打开原运行详情，直接定位答案、轨迹、地图、GeoJSON、发布报告与上下文证据，不重新调用模型。
2. **动态结果区收敛**：Console 按结果类型动态展示证据/地图/轨迹，减少固定面板；错误分类按 `error_category` 显示结构化状态而非字符串。
3. **真实模型基线扩展**（可选边界）：在稳定错误契约上扩展建设筛选、道路/水体约束与跨区域比较 live baseline。
4. **部署可靠性**：Docker Linux engine 恢复后执行当前版本数据卷、readiness、多 worker、重启恢复与 FastAPI production acceptance。

## M79.1：lineage 导航贯通（已完成）

### 实现内容

- **后端**
  - `agent/artifact_store.py`：artifact 新增持久化字段 `session_id`/`result_type`/`clarification`/`retry_count`/`geojson_ref`/`artifact_ref`；新增 `read_run(run_id)` 单条读取。`run()`/`retry()` 在 payload 完成后刷新 artifact，使落盘文件携带最终导航引用。
  - `agent/service.py`：`get_run()` 增加三级详情回退——指定 planner/backend 的 runtime → 扫描全部 live runtime（后端无关查找，覆盖比较子运行）→ artifact 降级详情（进程重启后仍可打开答案/轨迹/provenance/上下文，不重新调用模型）。
- **前端**（`web/index.html`，无构建步骤）
  - 历史列表主按钮改为打开原运行详情（`GET /runs/{id}`，不重跑模型），新增「重跑」副按钮显式标注会再次调用模型。
  - `appendMessage(role, text, runId)` 支持可点击回源消息；`openRunDetail(runId)` 拉取详情、切换会话、渲染答案/轨迹/地图/证据。
  - 阈值比较与多区域比较表格新增「详情」列，每行携带子运行 `run_id`。
  - `renderRun` 对重试结果显示「第 N 次重试后的运行详情（沿用原运行 ID）」徽标。

### 验收证据

- 新增 `tests/test_m79_lineage_navigation.py`（9 项）：artifact 持久化字段、`read_run`、重启后 artifact 降级详情、历史记录导航字段、历史 lineage deferred、比较/多区域子运行 `run_id`、retry 保持 `run_id` 且 `lineage.retry` 标记。
- 新增 `scripts/console_lineage_smoke.js`：历史主按钮打开详情 `run_count` 不变、可点击消息回到同一 `run_id`、比较详情入口携带 `run_id` 且打开后不重跑。
- 离线全量 441 项（42 跳过，+9）、Smoke、严格全局评测 8/8（0 失败）、console 浏览器 smoke 5/5（health/clear/session/overview/lineage）通过；map smoke 仍为 GIS 环境门控（`geopandas is required`），与既往记录一致。

## M79.1 复盘（七维全局矩阵）

- **产品能力**：历史/比较/retry 三处入口均可一键回到原运行详情（答案、轨迹、地图、GeoJSON、发布证据、上下文），且打开详情零模型调用——可回溯演示从被动展示变为主动导航。
- **架构**：详情读取按「指定 runtime → 全 runtime 扫描 → artifact 降级」三级回退，后端无关、跨进程可用；artifact 升级为 durable lineage 层。
- **数据质量**：artifact 摘要字段扩展（session_id/result_type/geojson_ref），仍不含原始上下文与原始工具参数（test_m35 `args` 不落盘断言通过）。
- **真实模型**：无新增 live 依赖；`get_run` 不触发规划，导航对 openai planner 同样生效。
- **部署可靠性**：memory 模式服务重启后历史详情仍可打开（artifact 回退），补强了 SQLite 之外的恢复路径；SQLite 模式本就持久化。
- **前端体验**：历史区分「打开详情 / 重跑」两个明确动作，消息可点击回源，比较表逐行可导航；浏览器 smoke 5/5。
- **测试**：+9 项离线 + 1 个浏览器 smoke；同时修正 smoke 脚本正则过宽问题。

**遗留风险**
- 比较子运行默认不导出 artifact，进程重启后比较行的详情入口只能命中 live runtime；历史列表（artifact 导出）才是持久导航。
- artifact 降级详情只有步骤摘要（无完整结果与几何要素），地图预览在降级态不可用——有意的「降级详情」语义，前端已展示原因。
- `AgentService` 内部状态多的架构债（M78 遗留）未在本阶段处理。

## M79.2 全局规划（下一阶段）

按依赖顺序单线程执行：

1. **动态结果区收敛**：Console 按 `result.result_type` 动态组合证据/地图/轨迹/统计面板，错误状态按 `error_category` 显示结构化徽标而非解析字符串；消除固定面板的空白与误导。
2. **比较子运行持久化（支撑项）**：比较接口子运行开启 artifact 导出，使比较行的详情导航跨重启可用。
3. **真实模型基线扩展**（可选边界）：建设筛选、道路/水体约束与跨区域比较 live baseline。
4. **部署可靠性**：Docker Linux engine 恢复后执行当前版本数据卷、readiness、多 worker、重启恢复与 FastAPI production acceptance。

## M79.1.5：部署可靠性实测（Docker Linux engine 恢复后）

按用户要求启动 Docker Desktop 实测部署链路（此前多阶段该边界一直标记为外部待办）。engine 就绪（server 29.6.2）后，层缓存重建镜像 → `docker compose up -d --force-recreate` → healthy → 完整验收链，**实测发现并修复两个真实生产缺陷**：

### 缺陷 1：内存模式重复异步提交永久死锁

- 现象：`production_acceptance.ps1` 的重复幂等提交（第二次 `POST /runs/async`）无限挂起（30s/60s 客户端超时均无响应、无 uvicorn 日志），首次提交正常。
- 根因：`run_async` 在 `with self._async_lock:`（非重入 `threading.Lock`）**内部** return，`_async_submission_response` → `get_async_observability` 在同线程再次获取同一把锁 → 永久死锁。M61 幂等测试只用 SQLite 模式，内存重复路径从未被覆盖（测试盲区）。
- 修复（`agent/service.py`）：锁内只记录 `(run_id, status, reused)` 元组，锁外统一调用 `_async_submission_response`；同时新增 `AgentService.close()`（executor 确定性收尾，消除测试中 SQLite 文件句柄竞态导致的 WinError 32）。

### 缺陷 2：生产容器运行在内存模式（SPATIAL_AGENT_STATE_DB 配置回归）

- 现象：即使修复死锁，2 个 uvicorn worker 的内存字典互不可见 → 重复提交落到另一 worker 时返回**新** run_id（幂等失效）、轮询 `GET /runs/{id}` 404（与 `docs/api.md` 声明的「生产 SQLite 模式支撑多 worker」矛盾）。
- 根因：Dockerfile/env 未设 `SPATIAL_AGENT_STATE_DB`，`AgentService()` 走内存模式（`outputs/spatial-agent.db` 是旧容器遗留文件）。
- 修复（`Dockerfile`）：ENV 增加 `SPATIAL_AGENT_STATE_DB=/app/outputs/spatial-agent.db`，生产镜像强制 SQLite 模式。

### 回归测试与验收证据

- 新增 `tests/test_m79_production_reliability.py`（5 项）：内存重复提交不死锁（看门狗防挂死）、env 驱动 SQLite 选择、SQLite 跨服务实例运行可见、跨实例幂等、Dockerfile 配置契约（防止该配置回归再次静默发生）。
- 离线全量 446 项（42 跳过，+5）、Smoke、严格全局评测 8/8 通过。
- `scripts/production_acceptance.ps1` 通过：`readiness=ready`、16 项能力、`runtime_health=ready`、核心数据 `ready`、可选 roads/water `unavailable`（`core_ready_optional_partial` 如实报告）、**`async_duplicate_idempotent=true`**。
- 真实 GIS 分析在容器内 COMPLETED：洪山区 DEM 区域统计（有效像元 576,016、均值 26.533、NoData 67.41%）。
- **容器重启恢复通过**：`docker restart` 后 healthy，`GET /runs/{id}` 返回完整 COMPLETED 快照，会话历史可见；重启后重跑 production_acceptance 再次通过。
- 真实模型 live 在容器内通过：planner=openai、deepseek-v4-flash、1662 tokens、3046ms、中文回答完整。
- Console 由生产容器托管（含 M79.1 lineage 前端，`openRunDetail` 就位）。
- 遗留：`D:/dataset/agent` 数据卷无 roads/water（可选层缺口如实报告）；实时模型 token 消耗未纳入 CI。

## M79.2 全局规划（更新）

1. **动态结果区收敛**：Console 按 `result.result_type` 动态组合证据/地图/轨迹/统计面板，错误状态按 `error_category` 显示结构化徽标而非解析字符串；消除固定面板的空白与误导。
2. **比较子运行持久化（支撑项）**：比较接口子运行开启 artifact 导出，使比较行的详情导航跨重启可用。
3. **真实模型基线扩展**（可选边界）：建设筛选、道路/水体约束与跨区域比较 live baseline。
4. **部署可靠性**（部分已完成）：Docker Linux engine 已恢复，当前版本镜像构建、readiness、production acceptance、重启恢复与多 worker 一致性已实测通过（M79.1.5）；后续随版本推进复验。

## M79.2：动态结果区收敛（已完成）

### 实现内容

- **前端**（`web/index.html`）
  - 结构化错误分类徽标：`errorCategoryLabels` 映射（provider/planning/tool/timeout/invalid_input/execution/cancelled/rejected/clarification → 中文标签），`errorCategoryBadge(category)` 在错误块内渲染分类徽章（按分类配色 CSS），`renderRun` 从 `data.error_category || data.result.error_category` 取值；成功结果不渲染错误徽标。
  - 结果区收敛：各统计面板的「等待…」误导性占位改为「本次结果未包含 XX 面板所需数据。」；比较面板初始/重置后显示可操作提示（「设置坡度阈值后点击「对比」生成结果。」），`resetConversationView` 恢复提示而非清空。
- **后端**（`agent/service.py`）：`compare_buildability` 子运行开启 `export_artifact=True`，比较行的详情导航跨重启可用（含失败子运行同样落盘，状态如实保留）。

### 验收证据（轻量验证纪律）

- 新增 `tests/test_m79_result_zone.py`（5 项前端契约）：错误徽标/分类标签覆盖服务端 taxonomy、result_type 驱动面板、无「等待」占位残留、比较面板提示。
- `tests/test_m79_lineage_navigation.py` 新增比较子运行持久化测试（memory 后端走通 + 重启后 artifact 回退导航）。
- 相关测试 26 项通过（M79 两个测试文件 + M67 前端契约 + M78 HTTP 契约）。
- 新增 `scripts/console_error_badge_smoke.js`：tool/rejected 徽标渲染、成功结果无徽标、比较提示持久；浏览器 smoke（error badge/session/health/overview）全部通过。
- 生产容器重建后 readiness 与比较接口实测（见下）。

### M79.2 复盘（七维全局矩阵）

- **产品能力**：错误从字符串升级为结构化分类徽标，前端可按 `error_category` 分支；面板空态不再误导为「等待」。
- **架构**：错误分类契约（M78.4 产物）首次被前端消费；比较子运行与主运行同样落盘，lineage 完整性提升。
- **数据质量**：比较子运行 artifact 含失败状态与步骤摘要，不伪造成功。
- **真实模型**：live 路径不受影响；错误徽标对 openai planner 的失败分类同样生效（数据来自服务端契约）。
- **部署可靠性**：生产容器重建后复验；比较详情导航跨重启可用（artifact 回退）。
- **前端体验**：错误徽章按分类配色，面板占位文案可操作；浏览器 smoke 5 类通过。
- **测试**：+6 项（前端契约 5 + 后端比较持久化 1）+ 1 个浏览器 smoke；沿用轻量验证（相关测试而非全量）。

**遗留风险**
- `resultViewRegistry` 仍按工具推断部分面板（无结果类型注册时），后续可收敛为纯结果类型驱动。
- 比较子运行 artifact 会进入 `/runs` 历史列表（内存模式），会话隔离仍靠 `comparison-*` 前缀区分。
- 真实模型 live 基线扩展与 Docker 复验随版本推进。

## M79.3 全局规划（下一阶段）

1. **真实模型基线扩展**（可选边界）：在稳定错误契约上扩展建设筛选、道路/水体约束与跨区域比较 live baseline，分别记录模型计划、工具门控、后端执行和答案证据。
2. **部署可靠性**：当前版本镜像重建 + readiness + production acceptance + 容器内 live 复验（数据卷边界如实报告）。

## M79.3：真实模型 live 基线扩展与部署复验（已完成）

### 实现内容

- **`evaluation/live_baseline.py`**：DEFAULT_LIVE_CASES 扩至 5 case——新增 `buildability`（建设筛选）、`constrained_buildability`（道路/水体约束）、`region_comparison`（跨区域比较）；`run_live_baseline` 支持 `service_factory` 分派比较 case；比较证据聚合行级 token/延迟/候选统计；`_capability_tools` 覆盖两个建设能力的期望工具。
- **`agent/service.py`**：`compare_buildability` 行增加 `planner_metrics`/`actual_tools`/`failed_steps`，使 live 基线可聚合子运行 token/延迟并记录失败分层。
- **`scripts/live_baseline.py`**：支持 `--case-ids` 子集选择，构造 `AgentService` 提供比较场景。
- **`tests/test_m79_live_baseline.py`**（+7 项离线）：建设/约束 kind 计划质量、比较 case 的 service 分派与聚合、service_unavailable 降级、admin 前缀解析回归。

### 实测发现并修复的 3 个真实模型问题

1. **admin 前缀贪婪匹配**（`agent/request_model.py`）：`_ADMIN_PREFIXES` 缺「筛选/过滤/挑选/筛出/选出」等动词，`parse_spatial_request('筛选洪山区…')` 把 admin_name 解析为「筛选洪山区」→ rule 计划器 range_query 查不到行政区 → `$.admin_name must be a string` 失败。修复：补全动词前缀（含「筛选」家族），回归测试覆盖建设筛选与含水体约束两条请求。
2. **buildability result_type prompt 契约缺失**（`agent/llm_planner.py`）：live 模型对建设筛选输出 `spatial_analysis_plan`/`construction_screening` 而非契约的 `buildability_result`/`constrained_buildability_result`（spatial_overview 有明确契约所以通过）。修复：system prompt 显式声明两个建设能力的输出类型必须值 + health preflight 步骤 MUST 依赖（对齐门控会拒绝缺失 health 的计划）。
3. **vector_summary 参数名不匹配**（`agent/llm_planner.py`）：live 模型按通用惯例给 `get_zonal_vector_summary` 传 `max_files`，但该工具 schema 属性是 `max_features` → `$ has unknown fields: max_files`（spatial-overview 三次 live 失败根因，rule 版因传 `max_features` 而幸免）。修复：prompt 显式声明 vector_summary 接受 `max_features (not max_files)`。

### 验收证据（轻量验证纪律）

- 相关测试 51 项通过（M79 三个测试文件 + M76 baseline + M62 intent/prompt + M67 + M78），未跑全量。
- **Live baseline 5/5 通过**（宿主机 GIS env + wuhan-gis analysis-ready 数据卷 + deepseek-v4-flash，报告存 `D:\tmp\wuhan-gis\m79-live-baseline.json` 不入库）：
  - capability-clarification：NEEDS_CLARIFICATION（1,951 tokens）
  - spatial-overview：COMPLETED 8 步（3,514 tokens）
  - buildability-screening：COMPLETED `buildability_result`（3,005 tokens）
  - constrained-buildability：COMPLETED `constrained_buildability_result`（2,856 tokens）
  - region-comparison：COMPLETED 洪山 22,800 / 江夏 58,419 候选像元（8,049 tokens）
  - 合计 19,375 tokens、0 provider 错误、0 重试、pass_rate 1.0。
- 浏览器 smoke 4 类通过（health/error badge/session/overview，overview 8 工具步骤 + 地图三色渲染）。
- 生产容器重建后 production acceptance 通过（readiness ready、16 能力、幂等 true、`core_ready_optional_partial` 如实）。
- **容器内 live 复验**：镜像已含全部修复（prompt 契约/前缀解析验证通过）；完整数据挂载下建设筛选 COMPLETED（`buildability_result`）+ 区域比较洪山 22,800/江夏 58,419 与宿主机一致（跨环境结果一致性强）。
- **容器数据卷边界如实报告**：生产数据卷 `D:/dataset/agent` 无 analysis-ready 对齐派生层 → 建设类工具被像元级对齐门控如实阻止（`grid_mismatch`），不伪造结果；这是数据准备边界而非代码缺陷（宿主机 wuhan-gis 有对齐层）。

### M79.3 复盘（七维全局矩阵）

- **产品能力**：建设筛选、道路/水体约束、跨区域比较三条真实模型链路全部可验证；live 基线成为版本质量闸门。
- **架构**：live baseline 统一 runtime 单请求 + service 比较两种执行面，token/延迟证据走同一脱敏管道；比较行携带 planner_metrics 不破坏结果契约。
- **数据质量**：容器内无对齐层时建设工具如实 gate（grid_mismatch），不伪造候选像元；宿主机对齐层结果跨环境一致。
- **真实模型**：deepseek-v4-flash 三个真实契约缺陷被 live 实测暴露并修复（参数名、result_type、健康前置）；5/5 case 稳定通过。
- **部署可靠性**：镜像重建 + production acceptance + 容器内 live 复验通过；数据卷边界如实分层报告。
- **前端体验**：无前端改动；浏览器 smoke 4 类通过（现有契约保持）。
- **测试**：+7 项离线（M79.3）+2 项 prompt 契约（M62）+3 项 admin 解析回归；沿用轻量验证（51 项相关而非全量）。

**遗留风险**
- 容器生产数据卷无 roads/water 与 analysis-ready 派生层，建设类 live 在容器默认挂载下会如实 gate；若要在生产容器直接演示建设筛选需准备对齐派生层数据卷。
- live baseline 每次运行消耗真实 token（本阶段 19,375），不纳入 CI；报告存仓库外。
- 区域比较仅覆盖 2 区域 × 1 阈值；更多区域/阈值组合留作后续扩展。

## M79.4 全局规划（面试演示闭环收口）

M79 全局规划 4 项（lineage 导航、动态结果区、真实模型基线、部署可靠性）已全部完成。下一阶段按七维复盘收敛遗留短板，按依赖顺序单线程执行：

1. **生产容器完整数据卷**（最高优先级，面试演示直接短板）：把宿主机已有的 analysis-ready 对齐派生层（`D:\tmp\wuhan-gis\analysis-ready`）与 roads/water（`wuhan-osm.gpkg`）引入生产挂载与数据配置，使容器内建设筛选/约束筛选/区域比较**默认可演示**，而不是 gate 报错（`grid_mismatch` / 可选层缺失）。
2. **AgentService 状态收敛**（M78 架构债）：把 runtime 缓存 / 异步作业字典 / SQLite 双模式收敛为独立状态模块；补作业级 wall-clock 超时与周期 reaper。
3. **多区域 × 多阈值比较矩阵**（真实模型扩展）：live baseline 区域比较扩到 3+ 区域 × 2+ 阈值，验证候选比例随阈值单调变化。
4. **前端纯结果类型驱动**（收尾）：`resultViewRegistry` 去掉工具推断兜底，完全按 `result_type` 注册面板。

## M79.4.1：生产容器完整数据卷（已完成）

### 实现内容

- **数据**（仓库外）：把宿主机已有的 analysis-ready 对齐派生层（`dem_aligned.tif`、`land_use_aligned.tif`、`analysis-ready-report.json`）与 `wuhan-osm.gpkg`（roads/water 共用）复制到生产数据根 `D:\dataset\agent`，并用 `scripts/dataset_manifest.py` 重新生成 manifest（路径相对 `/data`：`analysis-ready/dem_aligned.tif`、`wuhan-osm.gpkg` 等），校验 mismatch=0。
- **配置**（`config/datasets.container.example.json`）：dem/land_use 从原始瓦片 glob 改为 analysis-ready 派生层路径；新增 roads/water（指向 `wuhan-osm.gpkg`）；新增 `analysis_ready`（`/data/analysis-ready/analysis-ready-report.json`，required）与 `manifest`（`/data/analysis-ready/analysis.manifest.json`，required）绝对路径段。
- **测试**（`tests/test_m79_production_reliability.py` +1 项）：容器配置模板契约测试——必须含 roads/water、analysis-ready 派生层路径、analysis_ready.required、`/data/analysis-ready` 报告路径，防止配置回归。

### 验收证据（轻量验证纪律）

- 宿主机 health：`readiness=ready`、`analysis=ready`、`grid=aligned`、`manifest=ready`、5 数据集全 ready。
- 生产容器重建后：`/health/ready` ready、`data_readiness=ready`、`analysis_ready=ready`、`buildability_screening` 与 `constrained_buildability_screening` 均 `available=true, capability_status=ready`。
- **容器内实测（rule planner，真实数据）**：
  - 建设筛选 COMPLETED：洪山区 22,800 候选像元（valid 576,040）——不再 `grid_mismatch` gate。
  - 约束筛选 COMPLETED：候选 200 几何样本 → 满足道路约束 180 → 水体排除 14（roads/water 真实参与）。
  - 区域比较 COMPLETED：洪山 22,800（ratio 0.0396）/ 江夏 58,419（ratio 0.0260），与宿主机 live baseline 一致。
- **production acceptance 数据卷状态升级**：`data_volume_status` 从 `core_ready_optional_partial` → **`ready`**，`optional_data_health` 从 `unavailable` → **`ready`**，`optional_missing_datasets` 为空。
- 相关测试 48+32 项通过（1 live 门控跳过符合预期）；浏览器 smoke health/overview 通过。

### 复盘（七维矩阵，第 1 项）

- **产品能力**：面试演示短板消除——生产容器默认挂载即可演示建设筛选/约束筛选/区域比较，不再出现 gate 报错。
- **架构**：容器配置模板成为完整数据契约（core + optional + analysis-ready + manifest），防回归测试锁定。
- **数据质量**：对齐派生层 + roads/water 进入生产数据根；manifest 重新生成并校验（mismatch 0）。
- **真实模型**：live 路径不受影响（容器内 rule 验证 + 宿主机 live 基线一致）。
- **部署可靠性**：production acceptance 数据卷状态正式升为全 `ready`；容器重建后 healthy。
- **前端体验**：无前端改动；浏览器 smoke 通过。
- **测试**：+1 项配置契约；沿用轻量验证（相关 80 项而非全量）。

**遗留**：真实模型 live baseline 尚未在容器内完整数据卷上复跑（buildability/constrained live 需真实 token，留到第 3 项比较矩阵一并验证）。

## M79.4.2：AgentService 状态收敛 + 作业级 wall-clock 超时与 reaper（已完成）

### 实现内容

- **`agent/service_state.py`（新增）**：收敛 `AgentService` 的三块内存状态面（runtime 缓存、内存会话、内存异步作业）与 SQLite 双模式 store 引用为单一 `ServiceState`；增加：
  - 作业级 **wall-clock 超时**：`SPATIAL_AGENT_ASYNC_TIMEOUT_SECONDS`（默认 300s），`expired_run_ids()` 检测 QUEUED/RUNNING/CANCEL_REQUESTED 超龄作业。
  - **周期 reaper**：`start_reaper()`/`stop_reaper()`，daemon 线程按 `SPATIAL_AGENT_REAPER_INTERVAL_SECONDS`（默认 5s）扫描超龄作业 → `expire_job()` 标记 `TIMED_OUT` + `request_cancel()`（协作式让 worker 在 checkpoint 停止）。
- **`agent/service.py`**：改为持有 `ServiceState`，外部方法契约（run/run_async/get_run/compare 等签名）不变；内部状态访问通过只读属性委托，`_runtime()` 委托 `ServiceState.runtime()`（保留 planner/backend 校验）。
- **`agent/sqlite_store.py`**：新增 `list_active_async_jobs()`（reaper 扫描）与 `finish_async_job_by_run_id()`（未 claim 作业 owner_pid=NULL 时也能标记终态）。
- **`serve_api.py` / `production_api.py`**：HTTP 入口显式 `service.start_reaper()`（测试创建 service 不自动启动 reaper，避免 daemon 线程干扰临时目录清理）。
- **`tests/test_m79_reaper.py`（+7 项）**：超时 env 解析、内存作业过期检测、reaper 周期标记、新鲜作业不受影响、facade 校验保留、SQLite 已 claim/未 claim 作业超时标记。

### 验收证据（轻量验证纪律）

- 相关测试 89 项通过（reaper 7 + M79 三文件 + M10 API + M42/M60/M61/M67 异步 + M68 会话 + M78 HTTP 契约），未跑全量。
- 生产容器重建后 healthy；reaper 在生产入口显式启用。
- 状态收敛后外部行为不变：幂等、跨实例可见、会话生命周期、比较子运行、HTTP 契约全部保持（既有测试证明）。

### 复盘（七维矩阵，第 2 项）

- **产品能力**：异步作业不再无限挂起——wall-clock 超时 + reaper 提供最终一致终态。
- **架构**：三块内存状态 + SQLite 双模式收敛为单一 `ServiceState`，散落的 `if state_store is None` 分支集中；M78 架构债（作业级超时/周期 reaper）闭合。
- **数据质量**：无影响（状态层不触碰数据）。
- **真实模型**：无影响（live 路径复用同一 runtime 缓存）。
- **部署可靠性**：生产入口显式启用 reaper；未 claim 作业也能被标记终态（owner 无关更新）。
- **前端体验**：无前端改动。
- **测试**：+7 项（reaper 专项）；沿用轻量验证。

**遗留**：`AgentService` 方法体仍通过属性委托访问 `ServiceState`（未全部改为方法调用），属渐进收敛；后续可继续把 read/write 路径收进 `ServiceState` 方法。

## M79.4.3：多区域 × 多阈值比较矩阵（已完成）

### 实现内容

- **`evaluation/live_baseline.py`**：新增 `comparison_matrix` case kind——多区域（3+）× 多阈值（3），对每区域调 `service.compare_buildability(admin_name, thresholds)`（一次覆盖全部阈值），`_matrix_evidence` 聚合 token/延迟并**断言 candidate_ratio 随阈值单调不减**（坡度上限放宽只能增加候选）。
- **`tests/test_m79_live_baseline.py`**（+3 项）：矩阵证据聚合、非单调失败（error_class=monotonicity）、service 分派。

### 验收证据

- Live baseline 扩至 **6 case 全部通过**（pass_rate 1.0，47,102 tokens，0 错误 0 重试）：
  - comparison-matrix：洪山 0.0371→0.0402→0.0405 / 江夏 0.0250→0.0263→0.0264 / 武昌 0.0261→0.0299→0.0303，**三个区域均单调**，monotonic=True。
- 容器内 rule 复验同构数据（thresholds [10,20,30] 三区域单调一致）。
- 相关测试 51 项通过；浏览器 smoke 5 类全过。

## M79.4.4：前端纯结果类型驱动（已完成）

### 实现内容

- **`web/index.html`**：`resultViewRegistry` 补全全部 16 个 catalog result_types（新增 buildability_result/constrained_buildability_result/buildability_comparison/spatial_analysis_result/zonal_vector_summary_result/vector_result/spatial_relation_result/spatial_result 等显式注册）；`updateResultPanels` 移除「未注册类型按工具推断」兜底（`registeredViews === undefined` 分支、hasRasterTool/hasCompositeTool/hasHealthTool 推断全部删除），改为**纯结果类型驱动**（`views.has(...)` 决定面板）；建设/比较面板由结果类型而非工具决定。
- **`tests/test_m79_result_zone.py`**：更新面板契约断言（纯结果类型驱动 marker + 移除工具推断 marker）+ 新增「registry 覆盖全部 catalog result_types」测试（防新结果类型漏注册）。
- **`scripts/console_lineage_smoke.js`**：修正过时断言——比较按钮本身为每阈值创建子运行（M79.2 起子运行持久化进 /runs，run_count 比较后增长是预期），改为断言「点击详情入口不额外产生运行」（记录点击前 count）。

### 验收证据

- 相关测试 51 项通过；浏览器 smoke 5 类全过（health/error badge/session/overview/lineage）。
- production acceptance 全绿（数据卷 ready、幂等 true）。
- 前端契约：registry 覆盖全部 catalog 类型；无工具推断兜底残留。

### 复盘（七维矩阵，第 3+4 项）

- **产品能力**：比较矩阵提供跨区域×跨阈值的完整敏感性视图；前端面板完全由结果契约驱动，消除工具推断歧义。
- **架构**：result_type 成为前端面板的唯一事实源；registry 与 capability catalog 双向校验（测试锁定覆盖）。
- **数据质量**：矩阵单调性在真实数据与 live 模型下均成立（3 区域 × 3 阈值）。
- **真实模型**：comparison-matrix live 30,546 tokens，9 次真实 buildability 子运行全部 COMPLETED 且单调。
- **部署可靠性**：容器重建后 production acceptance 全绿。
- **前端体验**：面板决策收敛到注册表，新结果类型漏注册会被测试捕获。
- **测试**：+3 项（矩阵）+1 项（registry 覆盖）；修正 1 个过时 smoke 断言。

**遗留**：比较矩阵断言单调性基于每个区域独立行；若未来加入权重/约束参数（road_distance_m 等），单调性断言需按参数维度重新定义。M79.4 四项全部完成，面试演示闭环收口。

## M79.4 全局复盘（七维矩阵）

- **产品能力**：面试演示闭环收口——生产容器默认数据卷即可演示建设筛选/约束筛选/区域比较/比较矩阵；异步作业有 wall-clock 超时与 reaper 兜底，不会无限挂起。
- **架构**：`ServiceState` 收敛 runtime 缓存/内存会话/内存异步作业/SQLite 双模式；前端面板完全由 `resultViewRegistry` 结果类型契约驱动，去掉工具推断兜底；容器配置模板成为完整数据契约。
- **数据质量**：analysis-ready 对齐派生层 + roads/water 进入生产数据根，manifest 重生成 mismatch=0；比较矩阵单调性在真实数据与 live 模型下均成立（3 区域 × 3 阈值全单调）。
- **真实模型**：live baseline 扩至 6 case 全部通过（47,102 tokens，0 错误 0 重试），含 comparison_matrix 9 次真实 buildability 子运行；容器内 rule 复验与宿主机 live 证据一致。
- **部署可靠性**：生产容器数据卷状态 `ready`；reaper 由 HTTP 入口显式启用；production acceptance 全绿、幂等 true；容器 healthy。
- **前端体验**：registry 覆盖全部 16 个 catalog 结果类型；浏览器 smoke 5 类全过（health/error badge/session/overview/lineage）。
- **测试**：+10 项新测试（reaper 7 + 矩阵 3 + registry 覆盖 + 容器配置契约），修正 1 个过时 smoke 断言；沿用轻量验证（相关 51 项而非全量）。

**M79.4 遗留缺口（供 M79.5 规划）**
1. 生产容器内只有 rule planner 证据；真实模型 live baseline 尚未在容器完整数据卷上复跑（宿主机 live 证据 + 容器 rule 证据已分别成立，但"生产容器 + 完整数据卷 + 真实模型"三位一体证据缺失）。
2. 比较矩阵只覆盖坡度阈值单一参数维度；约束参数（road_distance_m 等）的敏感性尚无矩阵证据。
3. `AgentService` 方法体仍通过属性委托访问 `ServiceState`（渐进架构债，非功能缺口）。

## M79.5 全局规划（生产容器真实模型证据 + 约束敏感性矩阵）

按七维复盘收敛 M79.4 遗留缺口，按依赖顺序单线程执行：

1. **生产容器内真实模型完整复跑**（M79.4 遗留 1，最高优先级）：在 production 容器（完整数据卷 `/data:ro` + 容器配置）内直接执行 `scripts/live_baseline.py`，用真实 deepseek-v4-flash 跑全量 6 case（含 comparison_matrix），产出"生产容器 + 完整数据卷 + 真实模型"三位一体的 live 证据，与宿主机 live baseline 结果对照。容器内已具备条件（openai key/model/wire/base 已注入、live 脚本随镜像 COPY、外网可达）；需在容器内设置 live 门控变量并验证报告落盘。
2. **约束参数维度比较矩阵**（M79.4 遗留 2）：把比较矩阵从单一坡度阈值维度扩展到约束参数敏感性（road_distance_m 单调性：道路距离放宽 → 满足道路约束候选数单调不减），服务层新增约束比较入口，live baseline 增加约束矩阵 case，前端复用比较面板展示。
3. **AgentService 方法体收敛**（M79.4 遗留 3，纯架构债）：把 service.py 中仍通过属性委托的读/写路径收进 `ServiceState` 方法；仅在主线功能稳定后作为收尾项执行，不引入行为变化。

## M79.5.1：生产容器内真实模型完整复跑（已完成）

### 实现内容

- 无代码改动：直接在 production 容器（完整数据卷 `/data:ro` + 容器配置）内执行 `scripts/live_baseline.py --allow-network --backend local`，用真实 deepseek-v4-flash 跑全量 6 case；独立 state db（`/tmp/live-baseline-container.db`）避免与生产 uvicorn 争用 SQLite；报告落盘到挂载卷 `outputs/live-baseline-container.json`。
- 容器内已验证具备 live 前置条件（OPENAI_API_KEY/MODEL/WIRE/BASE 已注入、live 脚本随镜像 COPY、外网可达 api.deepseek.com）。

### 验收证据

- 容器内 6/6 全部通过（47,207 tokens，0 错误 0 重试，pass_rate 1.0）：
  - 澄清 NEEDS_CLARIFICATION（2,216 tokens）、空间总览 COMPLETED（8 工具全覆盖）、建设筛选 COMPLETED、约束筛选 COMPLETED。
  - 区域比较：洪山 22,800 / 江夏 58,419 候选像元，与宿主机 live 基线完全一致。
  - 比较矩阵：洪山 0.0371→0.0402→0.0405、江夏 0.0250→0.0263→0.0264、武昌 0.0261→0.0299→0.0303，三区域全单调。
- 宿主机 live baseline（47,102 tokens）与容器内（47,207 tokens）证据一致，"生产容器 + 完整数据卷 + 真实模型"三位一体成立。

### 复盘（七维矩阵，第 1 项）

- **产品能力**：面试演示可在生产容器上直接演示真实模型全链路（含比较矩阵）。
- **架构**：live baseline 复用统一 runtime 边界，容器内与宿主机同一套代码路径。
- **数据质量**：容器完整数据卷（analysis-ready + roads/water）下结果与宿主机一致。
- **真实模型**：容器内真实模型 6/6；比较矩阵单调性与宿主机一致。
- **部署可靠性**：容器内网络/密钥注入/报告挂载全部验证；独立 state db 避免与生产争用。
- **前端体验**：无前端改动。
- **测试**：沿用轻量验证；容器内报告为本次新增证据（仓库外挂载卷）。

## M79.5.2：约束参数维度比较矩阵（已完成）

### 实现内容

- **`agent/scenario.py`**：新增 `ConstrainedBuildabilityComparisonScenario`（admin_name + slope_limit_degrees + road_distances 1-6 个非负值，自动排序去重）。
- **`agent/service.py`**：新增 `compare_constrained_buildability(admin_name, road_distances, slope_limit_degrees, planner, backend, spatial_context)`——对同一区域遍历 road_distance_m 跑约束筛选，提取 `constraint_summary.eligible_features`，输出 `monotonic_eligible_features`（道路距离放宽 → 满足道路约束候选数单调不减，这是几何必然：距离放宽只增不减候选，水体排除与距离无关）。
- **`evaluation/live_baseline.py`**：新增 `constrained_matrix` case kind（多区域 × 多 road_distance），`_run_constrained_matrix_case` + `_constrained_matrix_evidence` 聚合 token/延迟并断言 eligible_features 单调不减。
- **HTTP**：`agent/api_contract.py` 新增 `constrained_comparison_kwargs`；`serve_api.py` 与 `production_api.py` 新增 `POST /constrained-comparisons` 路由。
- **前端**：比较面板新增「道路距离对比」控件组（`constrainedCompareButton`），渲染道路距离/候选几何样本/满足道路约束/水体排除表格 + 单调性徽标，复用 `comparisonDetailCell` 详情导航。
- **`scripts/console_constrained_smoke.js`（新增）**：CDP 浏览器 smoke——真实点击「道路距离对比」断言 3 行表格 + 单调徽标 ok。
- **测试**：`test_m57_scenario.py` +4（场景归一化/非法输入/服务层场景）；`test_m79_live_baseline.py` +4（矩阵证据单调、非单调失败、case via service、requires service）；`test_m45_console_browser.py` +1（约束控件契约）。

### 验收证据

- 相关测试 92 项通过（含 M79 全套 + scenario + console 契约 + HTTP 契约 + service split + lineage）。
- 容器重建后 healthy；rule planner 约束矩阵：洪山 200m→125、500m→161、1000m→180，`monotonic_eligible_features=True`，water_excluded 恒定 14。
- 容器内真实模型 constrained_matrix live：洪山 125→161→180、江夏 166→189→189，6 个子运行全 COMPLETED，单调 True，21,415 tokens。
- 浏览器 smoke：`constrained smoke PASS: rows=3 monotonicBadge=true`。

### 复盘（七维矩阵，第 2 项）

- **产品能力**：约束敏感性分析成为可演示能力——道路距离参数变化下候选数如何单调变化。
- **架构**：约束比较走统一 scenario 校验 + service 方法 + 双入口路由 + 前端复用比较面板，无新状态面。
- **数据质量**：eligible/water_excluded 来自真实 roads/water 数据卷；单调性在 rule 与 live 下均成立。
- **真实模型**：constrained_matrix live 6/6 子运行 COMPLETED 且单调，与 rule 证据一致。
- **部署可靠性**：`POST /constrained-comparisons` 在 dev 与 production 双入口契约一致。
- **前端体验**：复用比较面板布局，新增单调性徽标与道路距离维度列。
- **测试**：+9 项离线 + 1 浏览器 smoke；沿用轻量验证。

**遗留**：约束矩阵目前固定 exclude_water=True；若未来把水体排除作为可切换参数，单调性断言需按参数组合重新定义（与坡度矩阵同样的维度扩展空间）。

## M79.5.3：AgentService 方法体收敛（已完成）

### 实现内容

- **`agent/service_state.py`**：新增 9 个薄方法把 SQLite 读写路径收进 `ServiceState`——`save_run`/`get_run`/`create_async_job`/`claim_async_job`（含 recover 分支）/`finish_async_job`/`ensure_run_snapshot`/`list_runs`（含 session 过滤）/`store_metrics`；复用既有 `recover_async_jobs`/`async_job`/`clear_session_runs`。
- **`agent/service.py`**：`self._state_store.xxx` 散落调用全部改为 `self._state.xxx`（25 处），`if self._state_store is not None` 分支统一改为 `self._state.persistent`；保留 `_state_store` property 作为兼容访问器（测试与 `_async_status` 仍引用）与 `_async_status(self._state_store, ...)`（persistent 分支内语义不变）。

### 验收证据

- 相关测试 58 项通过（reaper 7 + async reliability + observability + session lifecycle + memory sessions + async config + integration + sqlite matrix + production reliability + service split + API）。
- 全量相关 92 项通过；行为零变化（纯方法调用迁移）。

### 复盘（七维矩阵，第 3 项）

- **产品能力**：无用户可见变化（纯内部重构）。
- **架构**：facade 不再直接触碰 SQLite store，所有持久化读写路径集中在 `ServiceState`；`persistent` 成为唯一模式判断，M78 架构债完全闭合。
- **数据质量/真实模型/部署/前端**：无影响（行为不变，相关测试证明）。
- **测试**：沿用轻量验证（58 项收敛面相关测试）。

## M79.5 全局复盘（七维矩阵）

- **产品能力**：生产容器可直接演示真实模型全链路（含比较矩阵与约束敏感性）；约束矩阵新增道路距离维度，面试演示覆盖"坡度阈值 × 区域 × 约束参数"三层敏感性。
- **架构**：约束比较走统一 scenario + service + 双入口路由 + 前端复用面板；ServiceState 收敛全部持久化读写路径，facade 只剩 `persistent` 模式判断。
- **数据质量**：约束单调性在真实 roads/water 数据卷与真实模型下均成立（洪山 125→161→180、江夏 166→189→189）。
- **真实模型**：容器内 6/6 全量复跑 + constrained_matrix 6/6 子运行全单调，与宿主机/rule 证据一致。
- **部署可靠性**：容器重建后 healthy；`/constrained-comparisons` 双入口契约一致；live 独立 state db 不争用生产 SQLite。
- **前端体验**：约束对比面板 + 单调性徽标；浏览器 smoke 通过。
- **测试**：+10 项离线（scenario 4 + live baseline 4 + console 1 + 服务层收敛验证）+ 1 浏览器 smoke；相关 92 项通过，沿用轻量验证。

**遗留**：约束矩阵 exclude_water 固定为 True（参数组合扩展留待后续）；M79.4 遗留 3 项（容器内真实模型复跑、约束参数维度、ServiceState 方法体收敛）全部闭合。

## M80 全局规划（通往完整 Agent 系统的差距清单）

以当前项目状态（400+ 测试、真实模型 live、生产容器、完整前端）为基线，列出距离"完整 Agent 系统"的差距并按面试作品集价值排序。当前最大并发度为 1，阶段任务按依赖顺序单线程执行；规划写入本段，具体执行按阶段拆分并在每阶段完成后七维复盘。

### A. Agent 核心能力（当前最薄弱，优先级最高）

1. **执行中自适应重规划**（最高价值）：当前 Planner 一次生成完整 DAG 后由 Runtime 顺序执行，是"单轮规划"；失败重试已有，但缺少"执行中观察步骤结果 → 动态调整后续步骤"的循环（如某数据不可用时改写后续工具参数或替换步骤）。这是最能体现 Agent 工程深度的能力。
2. **长期记忆系统**：目前只有 session 内澄清上下文；缺少跨会话偏好/历史结论引用与受控 retrieval（会话边界内引用既往运行，不越过会话隐私边界）。
3. **工具动态扩展**：工具集为静态注册；增加受控的"按需发现/注册"演示（仍须经过 ToolRegistry 与 schema 校验，不绕过统一边界）。
4. **多 Agent 协作演示**：可选；planner/executor/critic 角色分离的受控协作，作为架构展示而非必需。

### B. 生产级工程

5. **并发配额与成本治理**：并发上限、限流、优先级队列；真实模型 token 预算熔断（如单次运行/会话 token 上限，超限降级为 rule 或拒绝）。
6. **标准可观测性**：结构化运行日志、指标聚合；可选接入 OpenTelemetry 风格的 span 链路（不引入重依赖）。
7. **配置分层与密钥管理**：dev/staging/prod 配置分层；密钥从 `.env.production` 抽出为注入方案说明（本地不落地新密钥）。
8. **远程数据源抽象**（可选）：SpatialBackend 扩展 PostGIS/对象存储适配器演示，证明 backend 可替换性。

### C. 产品与交互

9. **流式输出**：SSE 流式步骤进度/结果增量渲染（当前为同步或轮询取完整结果）。
10. **工作流可视化编辑**（可选）：模板的 DAG 可视化与约束编辑。
11. **多用户与鉴权**（低优先）：本作品集项目可不做；如需演示则加 API key 认证层。

### D. 评测闭环

12. **CI 常态化评测**：脱敏回放进 CI（已具备），live baseline 保持手动 opt-in（成本考虑）；增加定期 live 报告归档对比。
13. **答案质量评判**：LLM-as-judge 对中文答案质量做受控评测（与结构化契约评测并行，不替代）。
14. **对抗性/长尾用例库**：扩充澄清、拒绝、超时、取消、数据退化等边界用例。

### 建议执行顺序（按作品集价值）

**M80 主线建议：A1（自适应重规划）→ A2（记忆）→ B6（可观测性）→ D13（答案评判）**，每项一个阶段，单线程推进；A3/A4、B8、C10 作为可选加分项，B5/B7/D12/D14 按需穿插；C11 明确不做。具体从哪一项开始由用户确认后写入阶段规划再执行。

## M80.1：执行中自适应重规划（进行中）

### 目标与边界

当前 `AgentRuntime.run()` 一次规划后顺序执行：步骤失败 → fail-fast + 剩余步骤 BLOCKED（`retry_failed` 只重跑失败步骤，不重规划）。A1 让运行时在**单次 run 内部**观察步骤失败/门控结果，触发受控的剩余步骤重规划，且不破坏统一边界：

- **触发条件**：步骤 ToolError 耗尽重试后仍失败（`_execute_step` 抛错），或 preflight 门控失败；且本轮重规划次数未达上限（`SPATIAL_AGENT_REPLAN_LIMIT`，默认 1）。
- **重规划输入**：已执行步骤结果摘要 + 失败步骤工具/参数/错误分类（受控摘要，不传原始 provider 文本）。
- **重规划输出**：planner 基于上述反馈生成**剩余步骤的替代计划**；新步骤合并回原计划（原已完成步骤保留，失败步骤标记 FAILED，剩余步骤被替换/追加），继续执行。
- **边界保障**：重规划新步骤仍过 `_validate_plan`（工具注册、依赖向前、步数上限）与 preflight 门控；planner 仍只能选注册工具；`replan_events` 记录受控证据（触发步骤、失败分类、新步骤数、耗时），不含原始错误文本/URL/key。
- **离线可测**：`_RecordedModelClient` 响应队列（`pop(0)`）天然支持录制多条 planner 响应 → 单次 run 内"第一条计划 + 失败 + 第二条重规划"可在离线夹具中复现，不访问网络。

### 实现计划（单线程）

1. **`agent/replanning.py`（新增）**：`ReplanningPolicy`（触发判定、剩余步数/重规划上限、失败摘要构造、计划合并）。
2. **`agent/runtime.py`**：执行循环捕获步骤失败 → 构造反馈 → 调 `self._planner.plan(request, context=反馈)` 重规划 → 合并 → 继续执行；`AgentRunResult` 新增 `replan_events` 字段。
3. **`agent/models.py`**：`AgentRunResult.replan_events: List[Dict]`（默认空）；序列化兼容。
4. **`evaluation/model_evaluation.py`**：`_RecordedModelClient` 队列已支持多响应；新增重规划夹具路径与质量断言（重规划后 COMPLETED、工具仍注册、replan_events 存在）。
5. **`agent/rule_planning.py`**：RuleBasedPlanner 在带反馈 context 时给出确定性重规划（如：失败步骤替换为降级工具/参数修正），保证 rule 路径也可离线验证。
6. **测试**：`tests/test_m80_replanning.py`（新增）——失败后重规划 COMPLETED、超限不重规划、重规划步骤过校验、rule 与 recorded-LLM 两条路径、replan_events 契约。
7. **验收**：相关测试 + 浏览器/前端无改动确认 + 容器重建回归 + live baseline 可选复跑。

## M80.1：执行中自适应重规划（已完成）

### 实现内容

- **`agent/replanning.py`（新增）**：
  - `ReplanningPolicy`：触发判定（仅步骤 FAILED 且未超预算）、预算 `SPATIAL_AGENT_REPLAN_LIMIT`（默认 1）、受控反馈 payload（已执行步骤摘要 + 失败步骤工具/参数/错误分类 + 可用工具 + 结果类型，不含原始错误文本/URL/key）。
  - `failure_category()`：稳定小分类（tool_gate / tool_validation / reference / backend_execution / unknown）。
  - `merge_replanned_plan()`：原计划保留到失败步骤为止（失败步骤之后的旧步骤被替换计划接管），重规划步骤追加并做 id 去冲突 + 依赖重写（引用保留原步骤则指向真实 id，引用被丢弃步骤则移除）。
  - `rule_replan_plan()`：确定性降级——constrained 失败→plain buildability；buildability（联合像元）失败→坡度+土地利用拆分；其他→健康摘要，保证 rule 路径离线可验证。
  - `build_replan_event()`：受控证据（失败步骤/工具/分类/新步骤数/耗时），不含原始错误。
- **`agent/runtime.py`**：执行循环从 for 改为 while，步骤失败（非取消/超时）时调 `_try_replan`：rule 路径走 `rule_replan_plan`，模型路径走 `self._planner.plan(request, context=_replan_context(feedback))`；合并后仅对 merged 计划做 `_validate_plan`（重规划步骤可合法依赖保留的原步骤）；重建 `result.steps` 与 merged 对齐；`replan_events` 记录每轮重规划。重规划失败或预算耗尽时回退 fail-fast（原行为不变）。
- **`agent/models.py`**：`AgentRunResult.replan_events: List[Dict]`（默认空）。
- **`agent/artifact_store.py` / `agent/sqlite_store.py`**：持久化往返保留 `replan_events`。
- **`web/index.html`**：运行链接区新增重规划提示（`replan-note`：重规划次数 + 失败步骤 + 新增步数）。
- **测试**：`tests/test_m80_replanning.py`（+15 项）——策略判定/预算/分类/合并重写/rule 三条降级路径/rule 运行时降级/recorded-LLM 双响应重规划/预算耗尽 fail-fast/持久化往返。

### 验收证据

- 相关测试 15/15 通过；运行时/评测/服务/前端契约回归 45 项通过。
- **全量离线 498 项通过（42 跳过）**；严格全局评测 8/8 通过。
- 修复 2 个**既有过期基线断言**（与本阶段无关但在全量中暴露）：`test_m67_console_evidence` 断言已移除的 `hasToolResult`（M79.4.4 遗留）；`test_m66_data_volume` 仍断言容器目录只有 3 个核心数据集与 `extracted/` glob（M79.4.1 遗留，已改为 analysis-ready + roads/water 契约）。
- 容器重建后 healthy；正常 rule 运行 COMPLETED（7 步）；replanning 模块容器内导入与分类验证通过。
- 浏览器/前端：replan 提示仅在 `replan_events` 存在时显示，正常运行无变化（smoke 语义不变）。

### 复盘（七维矩阵，M80.1）

- **产品能力**：执行中自适应重规划成为真实能力——步骤失败后由规划器基于执行反馈重排剩余步骤（模型路径）或确定性降级（rule 路径），而非直接 fail-fast。
- **架构**：重规划仍是 Planner→Runtime→ToolRegistry 统一边界内的能力；新计划必须过 `_validate_plan` 与 preflight；`replan_events` 是受控证据，不引入新状态面（存于既有结果契约）。
- **数据质量**：无数据层改动；约束/建设降级链在真实工具 schema 下由测试验证。
- **真实模型**：recorded-LLM 双响应离线复现"首计划失败→模型重规划→完成"；live 未跑（本阶段以离线契约为主，live 复跑留作可选）。
- **部署可靠性**：容器重建后 healthy，正常路径零变化；重规划预算可经 env 调优。
- **前端体验**：仅新增受控提示（有重规划才显示），正常界面无变化。
- **测试**：+15 项（含 recorded-LLM 与 rule 双路径）；修复 2 个既有过期断言，全量 498 项转绿。

**遗留**：live 模型重规划未在真实 provider 上复跑（需真实 token，留作可选验收）；重规划预算默认 1（可经 `SPATIAL_AGENT_REPLAN_LIMIT` 调大）；`rule_replan_plan` 的降级链目前覆盖 constrained/buildability/fallback 三类，更多工具的降级策略留作后续。

## M80.2：长期记忆（进行中）

### 目标与边界

当前记忆只有 session 内 pending clarification + last completed request（`ConversationStore`），无跨会话历史。M80.2 新增**跨会话可检索的结论记忆（fact memory）**：每次 COMPLETED 运行沉淀一条结构化结论摘要，支持按区域/结果类型/关键词检索，并作为受控上下文注入后续 planner 调用。

- **记忆条目**：`{run_id, session_id, result_type, admin_names[], summary(截断 200 字), facts{结构化指标键值}, created_at}`。来源为 result contract 已有字段（result_type/answer/admin_name/statistics），**不复制原始错误、URL、key、逐文件路径**。
- **写入时机**：`AgentRuntime.run()` COMPLETED 后（与 `save_completed` 同位置）；`ServiceState` 持有记忆存储引用。
- **检索**：按 session 检索（仅本会话历史）+ 全局检索（跨会话，受控注入——默认仅注入**同 session 的既往结论**，全局检索仅通过显式 API/评测使用，避免跨会话隐私泄漏）。
- **注入**：`ContextBuilder` 新增可选 `memory_sections`——planner 上下文追加「既往结论」小节（受预算截断，`memory` 标识为可信元数据而非指令）。
- **持久化**：SQLite 新表 `memory_facts`（内存模式用内存 dict，行为一致）；`SPATIAL_AGENT_MEMORY_ENABLED`（默认 1）可关闭。
- **契约**：`GET /memory?session_id=...`（受控检索）；运行结果带 `memory_evidence`（本次沉淀的记忆条目数 + 注入的检索数，受控摘要）。

### 实现计划（单线程）

1. **`agent/memory.py`（新增）**：`FactMemory`——`remember(result, ...)` 提取结构化结论、`recall(session_id, query, limit)` 检索、`list_facts`、受控 evidence 构造；内存/SQLite 双模式（仿 `ConversationStore`）。
2. **`agent/sqlite_store.py`**：新增 `memory_facts` 表 + CRUD（`insert_memory_fact` / `list_memory_facts` / `list_memory_facts_by_session`）。
3. **`agent/context_engineering.py`**：`ContextBuilder.build` 新增 `memory_sections` 参数，注入「既往结论」小节（预算内）。
4. **`agent/runtime.py`**：COMPLETED 后 `self._memory.remember(result)`；planner 调用前注入同 session 记忆。
5. **`agent/service_state.py` / `agent/service.py`**：持有 `FactMemory`；新增 `list_memory(session_id, ...)`；`format_result` 带 `memory_evidence`。
6. **HTTP**：`serve_api.py` / `production_api.py` 新增 `GET /memory`；`api_contract` 参数校验。
7. **前端**：结果证据区新增「长期记忆」卡片（本次记忆沉淀 + 注入历史数），受控展示。
8. **测试**：`tests/test_m80_memory.py`（新增）——remember 提取、session/全局检索、注入上下文、SQLite 往返、开关关闭、契约/HTTP。

### 验收标准

- 相关测试 + 全量离线回归；容器重建后 `GET /memory` 与记忆注入在真实数据下工作；前端记忆卡片 smoke；live baseline 可选复跑。

## M80.2：长期记忆（已完成）

### 实现内容

- **`agent/memory.py`（新增）**：`FactMemory`——`remember()` 从 COMPLETED 运行提取结构化结论（result_type + admin_names + 截断摘要 + allowlist 标量 facts）；`recall()`（session 作用域，关键词过滤，最新优先）/ `recall_global()`（仅显式契约用）；`context_section()`（受控注入：只带 result_type/admin_names/短摘要，不含原始错误/URL/key）；`evidence()`（本次记忆沉淀数）；内存/SQLite 双模式；`SPATIAL_AGENT_MEMORY_ENABLED`（默认 1）可关闭。
- **`agent/sqlite_store.py`**：新增 `memory_facts` 表（run_id 主键 + session 索引）+ `insert_memory_fact` / `list_memory_facts`（session 或全局）/ `delete_memory_facts`。
- **`agent/context_engineering.py`**：`ContextBuilder.build` 新增 `memory_section`，注入「memory」小节（预算内，超预算时最后被省略）。
- **`agent/runtime.py`**：COMPLETED 后 `_remember(result)` 沉淀记忆；规划前注入同 session 的 `memory.context_section`。
- **`agent/runtime_factory.py` / `agent/service_state.py`**：`build_runtime` 透传 `memory`；`ServiceState` 持有 `FactMemory`（SQLite 模式绑定 ConversationStore）。
- **`agent/service.py`**：新增 `list_memory(session_id, query, limit, global_scope)`；`run` 响应带 `memory_evidence`。
- **HTTP**：`serve_api.py` + `production_api.py` 新增 `GET /memory?session_id=&query=&limit=&global=`。
- **前端**：结果证据区新增「长期记忆」卡片（沉淀条数 + 注入说明；关闭时显示提示）。
- **测试**：`tests/test_m80_memory.py`（+11 项）——fact 提取 allowlist、仅 COMPLETED 记忆、session/全局检索、关键词过滤、上下文受控注入、开关关闭、SQLite 往返+清理、service 记忆、HTTP `/memory`；`test_m45_console_browser` +1（记忆卡片契约）。

### 验收证据

- 专项 11/11 通过；相关回归 67 项通过。
- **全量离线 510 项通过（42 跳过）**；严格全局评测 8/8 通过。
- 修复 1 个本阶段接口变更引起的测试替身（`test_m60` 的 `_build_retry_runtime` 未接收新 `memory` 参数）；发现并修复 `service.py` 缺少 `Optional` 导入（容器启动崩溃，重建后 healthy）。
- 容器内真实链路：两次运行 session_facts 1→2；`GET /memory?session_id=demo-memory` 返回 2 条结论（洪山区空间总览，facts 含 valid_pixel_count 576040 / mean 26.532 / nodata 0.674 等，摘要为中文结论）。
- 前端记忆卡片契约测试通过。

### 复盘（七维矩阵，M80.2）

- **产品能力**：长期记忆成为可演示能力——同会话后续请求自动获得既往结论上下文，跨会话检索有显式契约。
- **架构**：记忆是独立模块（内存/SQLite 双模式），挂在 Runtime 写、ContextBuilder 注入、Service 读的既有边界上；注入严格 session 作用域，不引入跨会话隐私泄漏。
- **数据质量**：facts 走 allowlist 标量（候选数/比例/均值/NoData 等），来源为真实步骤结果；不存原始错误/路径/key。
- **真实模型**：记忆注入进入 planner context（LLM 路径同样受益）；live 复跑留作可选。
- **部署可靠性**：SQLite `memory_facts` 持久化 + 索引；容器重建后 `/memory` 与记忆链路工作正常。
- **前端体验**：证据区新增记忆卡片，受控展示沉淀/注入信息。
- **测试**：+12 项（记忆 11 + 前端契约 1）；修复 1 个测试替身；全量 510 项转绿。

**遗留**：记忆检索为关键词过滤（无向量/语义检索）；全局检索仅显式 API 使用，未接入任何自动注入；`memory_evidence` 目前只含沉淀条数，未含"本次注入了哪几条"明细（避免泄露跨会话）。这些留作后续扩展。

## M80.3：标准可观测性（进行中）

### 目标与边界

现有观测面已较全（`/metrics` 聚合、async observability、trace_summary、SQLite 持久化）。M80.3 补齐**结构化运行日志 + 轻量 span 链路**（OpenTelemetry 风格但不引入依赖），让每次运行的执行轨迹以机器可读的 JSON-lines 输出，可被标准日志采集/追踪系统消费。

- **日志输出**：结构化 JSON-lines（每事件一行 JSON），默认 stdout，`SPATIAL_AGENT_OBSERVABILITY_LOG` 可指向文件；`SPATIAL_AGENT_OBSERVABILITY=0` 可关闭。
- **span 模型**（OpenTelemetry 概念映射，纯 Python 实现）：
  - run 级 span：`trace_id`（= run_id）、`span_id`、`name`（planner kind + result_type）、`status`（COMPLETED/FAILED/…）、`duration_ms`、`attributes`（session_id/backend/error_category/replan_count/memory_fact_count）。
  - step 级 span：`parent_span_id`（= run span）、`name`（工具名）、`status`、`duration_ms`、`attributes`（attempts/latency/error_category/result_type）。
  - 事件字段**受控**：不含原始错误文本、URL、key、逐文件路径、provider 响应。
- **挂载点**：`AgentRuntime.run()` 结束处发 run 级事件 + 每个 step 完成/失败处发 step 级事件（复用既有 `_execute_step` 的 StepRun 状态）；`AgentRuntime` 构造可注入 `ObservabilityEmitter`（默认 stdout emitter，测试可注入收集器）。
- **契约**：事件 schema 版本 `spatial-agent.observability.v1`；`GET /observability/health`（可选）返回日志开关与事件计数（进程内），供前端/验收确认。
- **不引入**：不新增 otel 依赖、不改造既有 metrics 接口、不写敏感字段。

### 实现计划（单线程）

1. **`agent/observability.py`（新增）**：`ObservabilityEmitter`（emit_run / emit_step，JSON-lines 序列化，字段 allowlist，开关 env）；`CollectingEmitter`（测试用内存收集）。
2. **`agent/runtime.py`**：`__init__` 接受 `observability`；`run()` 结束处 emit run 事件；`_execute_step` 成功/失败处 emit step 事件。
3. **`agent/runtime_factory.py` / `agent/service_state.py`**：透传 emitter（HTTP 服务默认 stdout emitter）。
4. **`serve_api.py` / `production_api.py`**：可选 `GET /observability/health`（开关 + 进程内事件计数）。
5. **测试**：`tests/test_m80_observability.py`（新增）——事件字段受控（无敏感）、JSON 可解析、span 父子关系、开关关闭无输出、HTTP health。
6. **验收**：相关测试 + 全量离线回归 + 容器重建后观察结构化日志输出 + 前端无改动确认。

### 验收标准

- 专项测试通过；全量离线转绿；容器日志中出现 JSON-lines run/step 事件且无敏感字段；`GET /observability/health` 返回开关状态。

## M80.3：标准可观测性（已完成）

### 实现内容

- **`agent/observability.py`（新增）**：
  - `ObservabilityEmitter`：JSON-lines 结构化事件（schema `spatial-agent.observability.v1`），OpenTelemetry 风格字段（trace_id=run_id、span_id、parent_span_id、name、status、duration_ms、timestamp），纯标准库实现。
  - run 级事件 attributes：session_id/result_type/error_category/replan_count/memory_fact_count；step 级：attempts/error_category（`failure_category` 分类）。
  - **受控字段**：仅 allowlist 标量，不写原始错误文本/URL/key/路径；`_attribute_ok` 拒绝超长字符串。
  - **输出策略**：默认只计数不写任何流（保护 CLI stdout 纯 JSON 契约）；`SPATIAL_AGENT_OBSERVABILITY_LOG=<path>` 写文件、`SPATIAL_AGENT_OBSERVABILITY_STDOUT=1` 显式写 stdout、`SPATIAL_AGENT_OBSERVABILITY=0` 关闭。
  - `CollectingEmitter`：测试用内存收集（验证线格式）。
- **`agent/runtime.py`**：`__init__` 接受 `observability`；run() 开始时登记 run span_id，结尾 emit run 事件（用同一 span_id 作为 run 事件 span，step 事件以它为 parent）；`_execute_step` 成功/失败/preflight 门控处 emit step 事件。
- **`agent/runtime_factory.py` / `agent/service_state.py`**：`build_runtime` 透传 emitter；`ServiceState` 持有 `ObservabilityEmitter`。
- **HTTP**：`serve_api.py` + `production_api.py` 新增 `GET /observability/health`（开关 + 进程内事件计数）。
- **`Dockerfile`**：`SPATIAL_AGENT_OBSERVABILITY_LOG=/app/outputs/observability.log`（挂载卷可查看结构化日志）。
- **测试**：`tests/test_m80_observability.py`（+5 项）——开关、run 事件无敏感字段、step 父子 span、禁用无输出、runtime 全链路事件。

### 验收证据

- 专项 5/5 通过；相关回归 78 项通过。
- **全量离线 515 项通过（42 跳过）**；严格全局评测 8/8 通过。
- **CI 修复（重要）**：M80.3 初版 emitter 默认写 stdout，污染了 `scripts/smoke_check.py` 的纯 JSON 输出（CI 命令 `python scripts/smoke_check.py` 全失败，GitHub 持续告警）。修复为「默认只计数、不写任何流；显式 log 文件或 STDOUT=1 才输出」——`smoke_check.py` 退出码 0、输出保持纯 JSON，CI 命令本地复验绿。Dockerfile 配置日志文件路径，容器内仍可观测。

### 复盘（七维矩阵，M80.3）

- **产品能力**：执行轨迹以标准 JSON-lines + span 模型输出，可被日志采集/追踪系统消费。
- **架构**：observability 是独立模块（纯标准库），挂在 Runtime 既有边界（run/step 生命周期），不引入 otel 依赖、不改 metrics 接口。
- **数据质量**：事件字段受控（allowlist 标量 + 分类），无敏感字段泄漏。
- **真实模型**：planner 名称进入 run 事件 name，LLM 路径同样被观测。
- **部署可靠性**：日志文件挂载卷可查；CI 命令恢复纯 JSON 契约（这是本阶段修复的关键回归）。
- **前端体验**：无前端改动（observability 是后端/运维侧能力）。
- **测试**：+5 项；全量 515 项转绿；CI 命令复验通过。

**遗留**：observability 事件目前只进日志/内存计数，未接外部追踪后端（Jaeger/OTLP）；`GET /observability/health` 无鉴权（demo 项目可接受）。

## CI 修复（M80.3 附随）

GitHub CI（`python scripts/smoke_check.py`，windows-latest + Python 3.11）从 M79.1 起持续失败。根因两类，均已修复并验证：

1. **测试默认 `backend="local"` 依赖本地数据集**：`test_m79_lineage_navigation` 的两个测试（comparison/region 子运行 run_id 契约）用 `AgentService()` 默认 backend="local"，CI 干净环境无 `D:\dataset\agent` → `admin_areas dataset has no files`。修复：显式 `backend="memory"`（测的是 run_id/lineage 契约，与 GIS 无关）。
2. **`runtime_capability_snapshot` 降级路径契约不完整**：config 存在但数据缺失（CI 是 example 配置指向本地绝对路径）时走降级返回，缺 `data_evidence`/`runtime_evidence`/`updated_at`，导致 `test_m59` 失败。修复：降级路径改用 `runtime_capability_catalog({}, environment=...)` 统一构造（空健康快照，契约字段完整），并补 `updated_at`。
3. **observability stdout 污染**（M80.3 引入）：emitter 默认写 stdout 污染 smoke_check 纯 JSON 输出 → 改为默认只计数、显式 log 文件或 STDOUT=1 才输出。

**验证**：`SPATIAL_AGENT_DATASET_CONFIG` 指向不存在路径（模拟 CI 无数据）→ 全量 515 项通过；本地有数据环境同样 515 项通过；`python scripts/smoke_check.py` 退出码 0；严格全局评测 8/8。

## M80.4：LLM-as-judge 答案评判（进行中）

### 目标与边界

当前 `evaluate_plan_quality` 的 `chinese_answer` 只检查中文存在性（是否含中文字符），无质量评判。M80.4 新增**答案质量评判器**：默认用确定性启发式（离线、可测），可选用真实模型做 LLM-as-judge（opt-in、脱敏），与结构化契约评测并行，**不替代**结构化评测。

- **评判维度**（4 维，每维 0-5 分 + passed 判定）：
  - `completeness`：答案是否覆盖请求的核心要素（区域名、指标、结论）。
  - `groundedness`：答案中的数字/结论是否与证据步骤（step results）一致（如候选像元数匹配）。
  - `clarity`：中文可读性（无乱码、结构清晰、长度合理）。
  - `explanatory`：是否说明数据来源/方法/限制（演示筛选非规划许可等 disclaimer）。
- **启发式评判**（默认）：确定性规则，从 answer + steps 提取数字并交叉核对、检查中文字符/乱码模式/免责声明关键词——**不访问网络、不耗 token**，可进 CI。
- **LLM-as-judge**（可选）：`SPATIAL_AGENT_JUDGE_LLM=1` 时用 deepseek（复用 `OpenAIPlannerClient`）对答案按 4 维打分，prompt 只含答案与受控证据摘要（无原始 provider 数据），结果脱敏（只保留分数与一句话理由，不复制原文）。
- **挂载**：`evaluation/model_evaluation.py` 的 `evaluate_plan_quality` 附加 `answer_judge` 维度（启发式默认跑）；`evaluation/live_baseline.py` 可选加 judge 汇总。
- **测试**：启发式评判器纯函数测试（好答案高分/坏答案低分/数字不符降 groundedness/乱码降 clarity）；judge 结果契约测试。

### 实现计划（单线程）

1. **`evaluation/answer_judge.py`（新增）**：`heuristic_answer_judge(answer, steps, request)` 确定性评判 + `llm_answer_judge(answer, steps, request, client)` 可选模型评判 + 脱敏结果构造。
2. **`evaluation/model_evaluation.py`**：`evaluate_plan_quality` 附加 `answer_judge`（启发式，默认）；live baseline 报告含 judge 汇总。
3. **测试**：`tests/test_m80_answer_judge.py`（新增）——4 维启发式判定、数字一致性、乱码检测、judge 结果契约、LLM 路径（recorded client）。
4. **验收**：相关测试 + 全量离线回归 + CI 绿；live judge 可选复跑。

### 验收标准

- 专项测试通过；全量离线转绿；CI 绿；judge 结果不改变既有 passed 语义（只附加维度）。

## M80.4：LLM-as-judge 答案评判（已完成）

### 实现内容

- **`evaluation/answer_judge.py`（新增）**：
  - `heuristic_answer_judge()`：确定性 4 维评判（completeness/groundedness/clarity/explanatory，各 0-5 + passed），**离线、无 token、CI 安全**。
    - completeness：答案是否覆盖请求核心要素（区域名/数据集/指标词）。
    - groundedness：答案数字与证据步骤（statistics/constraint_summary）数量级一致性（0.1-10 倍内 5 分，10-100 倍 3 分，更离谱 1 分）。
    - clarity：中文存在性 + 乱码检测（U+FFFD/转义序列）+ 长度。
    - explanatory：是否含免责声明（演示/不代表规划许可）与方法/数据说明。
  - `llm_answer_judge()`：可选 LLM-as-judge（`SPATIAL_AGENT_JUDGE_LLM=1`），复用 `OpenAIPlannerClient`，prompt 只含答案 + 受控证据摘要；结果脱敏（分数 + 一句话理由，不复制原文）；模型调用失败时回退启发式。
  - `answer_judge_report()`：公共入口（默认启发式，开启 + 有 client 时 LLM）。
- **`evaluation/model_evaluation.py`**：`evaluate_plan_quality` 附加 `answer_judge` 维度（启发式默认跑）——**附加语义**，不改变既有 passed 判定。
- **测试**：`tests/test_m80_answer_judge.py`（+11 项）——好答案四维高分、空答案 0 分、数字矛盾降 groundedness、乱码降 clarity、请求要素匹配、免责声明检测、默认启发式、LLM 脱敏回退、recorded client 打分、分数钳制、evaluate_plan_quality 附加维度。

### 验收证据

- 专项 11/11 通过；评测相关回归 54 项通过。
- **全量离线 526 项通过（42 跳过）**；严格全局评测 8/8 通过。
- **live LLM-as-judge 验证**：真实 deepseek（opencode 网关）对示例答案评分——completeness 4 / groundedness 5 / clarity 5 / explanatory 4，passed=true（脱敏：分数 + 一句话理由）。
- CI 命令 smoke_check 退出码 0（judge 为纯函数，不引入 stdout/环境依赖）。

### 复盘（七维矩阵，M80.4）

- **产品能力**：答案质量从"是否有中文"升级为四维可量化评判，且可切换真实模型 judge。
- **架构**：judge 是独立评估模块（纯函数 + 可选 client），挂在既有评测管线（evaluate_plan_quality 附加维度），不侵入 runtime 主路径。
- **数据质量**：groundedness 用证据数字交叉核对，答案与真实统计不一致会被扣分。
- **真实模型**：LLM-as-judge 可选路径用真实 deepseek 验证通过；失败自动回退启发式，不破坏评测。
- **部署可靠性**：启发式默认离线可进 CI；LLM 路径 opt-in 不消耗 CI token。
- **前端体验**：无前端改动（评测侧能力）。
- **测试**：+11 项；全量 526 项转绿。

**遗留**：judge 分数尚未展示到前端/报告可视化（当前在评测 JSON 中）；LLM-as-judge 未接入 live baseline 汇总（可后续加 judge case）。M80 主线 A1/A2/B6/D13 全部完成。

## M80 全局复盘（七维矩阵）

- **产品能力**：Agent 具备执行中自适应重规划（观察失败→重排剩余步骤）、跨会话长期记忆（fact memory + 同会话注入）、标准可观测性（JSON-lines + span 链路）、答案质量评判（4 维启发式 + 可选 LLM judge）——四项核心 Agent 能力补齐。
- **架构**：四项均为独立模块（replanning/memory/observability/answer_judge），挂在 Runtime/评测既有边界上，不引入重依赖（纯标准库），不破坏既有契约（judge 附加维度、memory 注入受控、replan 回退 fail-fast）。
- **数据质量**：groundedness 用证据数字交叉核对答案；记忆 facts allowlist 标量；observability 事件受控字段。
- **真实模型**：A1 有 recorded-LLM 离线双响应重规划 + 容器 live 验证；D13 有真实 deepseek judge 验证（四维评分）；live 全链路（容器内 6/6 + 约束矩阵）此前已建立。
- **部署可靠性**：**CI 修复**（测试默认 local backend 依赖本地数据 + 快照降级契约 + observability stdout 污染三类根因），CI 从持续失败转为持续绿；容器重建 healthy；observability 日志文件挂载卷。
- **前端体验**：重规划提示徽标 + 长期记忆卡片（受控展示）；observability/judge 为后端评测侧能力，无前端侵入。
- **测试**：+42 项（replan 15 + memory 12 + observability 5 + judge 11 + 前端契约等）；全量 526 项通过；严格评测 8/8；CI 绿。

**M80 遗留缺口（供 M81 规划）**
1. **A3 工具动态扩展**（M80 可选加分项未做）：受控的"按需发现/注册"工具演示。
2. **B5 并发配额与成本治理**：真实模型 token 预算熔断（单次/会话 token 上限，超限降级或拒绝）。
3. **C9 流式输出**：SSE 流式步骤进度/结果增量渲染（当前同步/轮询）。
4. **D12 CI 常态化评测**：脱敏回放已进 CI（smoke 跑全量）；live 报告归档对比未自动化。
5. judge 分数前端可视化；LLM-as-judge 接入 live baseline 汇总。

## M81 全局规划（候选方向，待用户确认）

按七维复盘收敛 M80 遗留，按依赖顺序单线程执行。建议主线（按作品集价值）：

1. **B5 成本治理与并发配额**（真实模型可控性）：单次运行/会话 token 预算熔断 + 并发上限，超限降级为 rule 或拒绝——面试可讲"真实模型成本可控"。
2. **A3 工具动态扩展**（受控）：按需发现/注册工具的受控演示（仍过 ToolRegistry/schema 校验）。
3. **C9 流式输出**（体验）：SSE 流式步骤/结果增量渲染。
4. **D13 收尾**：judge 分数前端可视化 + live baseline judge 汇总。

具体从哪一项开始由用户确认后写入阶段规划再执行。

## M81.1：成本治理与并发配额（进行中）

### 目标与边界

真实模型调用消耗 token 且并发不可控。M81.1 补三层治理（全部 env 可配、默认关闭不改变现有行为）：

1. **会话级 token 预算**：`SPATIAL_AGENT_TOKEN_BUDGET`（默认 0=不限）——同一 session 累计 planner token 超限后，该会话后续 run 在规划前拒绝（`TOKEN_BUDGET_EXCEEDED`，错误类别 `budget`），不访问 provider。
2. **单次运行 token 上限**：`SPATIAL_AGENT_RUN_TOKEN_CAP`（默认 0=不限）——单次 run 的 planner 总 token 超限时终止运行并标记 `budget_exceeded`（结果保留已完成步骤证据）。
3. **并发配额**：`SPATIAL_AGENT_MAX_CONCURRENT`（默认 0=不限）——同步 `run()` 的并发信号量；超过配额返回 `CONCURRENCY_LIMITED`（HTTP 429 语义），不排队不阻塞。

- **计量**：`ServiceState` 新增 `TokenBudget`（会话累计表 + 单次运行 cap 检查），从 `result.planner_metrics.usage.total_tokens` 累加（rule planner 无 usage 则 0）。
- **挂载**：`run()` 入口检查会话预算；`run()` 完成累加会话预算 + 检查单次 cap；`run_async` 提交前同样检查。
- **契约**：`error_category=budget` / `concurrency_limited` 进入既有错误分类；`/metrics` 增加 `budget` 摘要（会话数、已耗 token、上限）。
- **测试**：预算未超正常、超限拒绝、单次 cap 终止、并发配额、rule 路径不受影响、env 解析。

### 实现计划（单线程）

1. **`agent/cost_governance.py`（新增）**：`TokenBudget`（会话累计 + 单次 cap + 并发信号量），env 解析（0=不限）。
2. **`agent/service_state.py`**：持有 `TokenBudget`；`run()`/`run_async()` 前置检查 + 完成后累加。
3. **`agent/service.py`**：run 流程接入预算检查；错误分类扩展 budget/concurrency_limited。
4. **`agent/service_format.py`**：error_category 扩展。
5. **HTTP**：429 映射（concurrency_limited）+ `/metrics` budget 摘要。
6. **测试**：`tests/test_m81_cost_governance.py`（新增）。
7. **验收**：相关测试 + 全量回归 + CI 绿；容器内验证预算生效。

### 验收标准

- 专项测试通过；全量离线转绿；CI 绿；预算/并发默认关闭时行为零变化（既有测试证明）。

## M81.1：成本治理与并发配额（已完成）

### 实现内容

- **`agent/cost_governance.py`（新增）**：`TokenBudget` 三层治理（全部 env 可配，默认 0=不限，行为零变化）：
  - 会话级预算 `SPATIAL_AGENT_TOKEN_BUDGET`：同一 session 累计 planner token 超限后 `check_budget` 抛 `BudgetExceeded`，run/run_async 在规划前拒绝，不访问 provider。
  - 单次运行 cap `SPATIAL_AGENT_RUN_TOKEN_CAP`：run 完成后 `check_run_cap` 超限标记 `budget_exceeded`（保留已完成步骤证据）。
  - 并发配额 `SPATIAL_AGENT_MAX_CONCURRENT`：`BoundedSemaphore` 门控同步 run()，超限抛 `ConcurrencyLimited`（不排队）。
  - `extract_tokens()`：从 planner_metrics.usage.total_tokens 提取（rule planner 无 usage → 0）；`summary()` 供 /metrics。
- **`agent/service.py`**：run() 入口 `acquire_concurrency`（try/finally 释放）+ `check_budget`；run 完成 `charge` + `check_run_cap`；run_async 提交前 `check_budget`；`_run_governed` 抽出 run 主体（保持原 payload 构造/artifact/geojson/memory_evidence 全流程）；metrics 增加 `cost_governance` 摘要。
- **`agent/service_state.py`**：持有 `TokenBudget`。
- **`agent/api_contract.py`**：`BudgetExceeded`/`ConcurrencyLimited` → HTTP 429（error_code `rate_limited`）；`failure_category_for_error` → `budget` / `concurrency_limited`。
- **测试**：`tests/test_m81_cost_governance.py`（+11 项）——env 解析默认关/非法值、预算累计与超限、单次 cap、并发信号量、token 提取、summary、service 零 token 计费、预算拒绝、HTTP 429 映射。

### 验收证据

- 专项 11/11 通过；相关回归 72 项通过。
- **全量离线 537 项通过（42 跳过）**；严格全局评测 8/8 通过；`python scripts/smoke_check.py` 退出码 0。
- 默认关闭（env 未设）时行为零变化——既有 526 项测试全部保持通过（无回归）。
- 并发/预算错误映射 HTTP 429 + `budget`/`concurrency_limited` 分类进入既有错误契约。

### 复盘（七维矩阵，M81.1）

- **产品能力**：真实模型成本可控——会话 token 熔断、单次运行上限、并发配额，面试可讲"真实模型治理"。
- **架构**：`cost_governance` 是独立模块，挂在 Service 边界（run 入口/完成），不侵入 Runtime/Planner；默认关闭零变化。
- **数据质量**：无数据层影响（治理不触碰数据）。
- **真实模型**：token 从 planner_metrics.usage 提取（真实 provider 计量），rule 路径 0 token 不受影响。
- **部署可靠性**：HTTP 429 + 错误分类贯通双入口；/metrics 暴露预算摘要。
- **前端体验**：无前端改动（治理是服务端能力；429 由既有 error 展示）。
- **测试**：+11 项；全量 537 项转绿。

**遗留**：预算未持久化（重启后会话 ledger 重置，内存模式）；LLM-as-judge/live 未接入预算联动（live 路径的 planner token 已计入会话 ledger，天然受控）；并发配额只限同步 run（异步已有 worker 池）。

## M81.2：工具动态扩展（进行中）

### 目标与边界

工具集当前静态注册（`ToolRegistry.from_json`），运行时不可新增。M81.2 增加**受控的工具动态注册**：运行时按需注册新工具，仍经过 ToolRegistry schema 校验与统一分发，不绕过任何既有边界。

- **`ToolRegistry.register_tool(name, definition, handler)`**：
  - 校验：name 非空/合法标识符/未重复；definition 必含 `input_schema`（object 类型）；handler 必须 callable。
  - 分发：`invoke` 优先 adapter（既有工具路径不变）；adapter 抛 `does not implement` 时查动态 handler；handler 返回必须 dict。
  - 查询：`dynamic_tools()` 列出已注册动态工具（name + 摘要），供能力/评测消费。
- **演示工具**：`estimate_area`——基于行政区矢量要素（range_query 结果）估算区域面积（纯计算、无副作用、无真实数据依赖），演示"Agent 按需获得新能力"。
- **挂载**：`AgentService.register_tool(name, definition, handler)` 委托到 runtime registry；`GET /tools/dynamic`（列动态工具）+ `POST /tools`（受控注册 demo）。
- **边界保障**：注册不改既有工具行为；动态工具同样过 `_validate`；`registry.names` 动态反映新增工具（planner allowed_tools 天然感知）；不落持久化（进程内注册，重启回归静态集）。
- **测试**：注册校验（非法名/重复/缺 schema/非 callable）、分发（adapter 优先 + handler 回退 + 返回校验）、动态 names、服务层注册 + HTTP 契约、演示 estimate_area。

### 实现计划（单线程）

1. **`agent/tools.py`**：`ToolRegistry.register_tool` + `dynamic_tools` + invoke handler 回退。
2. **`agent/service.py`**：`register_tool` 委托 + `list_dynamic_tools`。
3. **HTTP**：`serve_api.py` + `production_api.py` 的 `GET /tools/dynamic` + `POST /tools`；`api_contract` 参数校验。
4. **演示 handler**：`estimate_area`（挂在 service 层，调用 range_query 结果计算）。
5. **测试**：`tests/test_m81_dynamic_tools.py`（新增）。
6. **验收**：相关测试 + 全量回归 + CI 绿 + 容器内演示注册/调用。

### 验收标准

- 专项测试通过；全量离线转绿；CI 绿；注册不改既有工具行为（既有工具测试证明）。

## M81.2：工具动态扩展（已完成）

### 实现内容

- **`agent/tools.py`**：`ToolRegistry.register_tool(name, definition, handler)`——受控注册：
  - 校验：name 必须匹配 `^[a-z][a-z0-9_]*$`、未与既有工具重复、definition 必含 object 类型 `input_schema`、handler 必须 callable。
  - 分发：`invoke` 优先动态 handler（与 static adapter 路径并列）；handler 返回值必须 dict；`_validate` schema 校验对动态工具同样生效。
  - `dynamic_tools()`：返回受控摘要（name + description）。
  - `names` 动态反映新增工具（planner allowed_tools 天然感知）。
- **`agent/service.py`**：`register_tool`（注册到所有 live runtime，未构建时惰性建默认 runtime）+ `list_dynamic_tools`；`estimate_area_handler` 演示工具（平面 shoelace 面积估算，纯计算无副作用，带演示 disclaimer）。
- **HTTP**：`serve_api.py` + `production_api.py` 的 `GET /tools/dynamic` + `POST /tools`（注册 estimate_area 演示）。
- **测试**：`tests/test_m81_dynamic_tools.py`（+10 项）——注册校验（非法名/重复/坏 definition/非 callable）、动态 handler 分发 + schema 校验、静态工具不受影响、dynamic_tools 摘要、service 注册 + estimate_area 调用/坏输入、HTTP 注册/列表。

### 验收证据

- 专项 10/10 通过；相关回归 79 项通过。
- **全量离线 547 项通过（42 跳过）**；严格全局评测 8/8 通过；`python scripts/smoke_check.py` 退出码 0。
- 既有静态工具行为零变化（既有工具测试全部保持通过）。

### 复盘（七维矩阵，M81.2）

- **产品能力**：Agent 可按需获得新能力（受控注册动态工具），演示"工具集不是写死的"。
- **架构**：动态注册在 ToolRegistry 内部完成，仍走统一 `_validate` 分发；不绕过任何既有边界；静态工具路径不变。
- **数据质量**：无数据层影响（estimate_area 纯计算）。
- **真实模型**：planner allowed_tools 动态感知新工具（LLM 路径可选用动态工具）。
- **部署可靠性**：双入口契约一致；进程内注册（重启回归静态集，符合演示边界）。
- **前端体验**：无前端改动（`GET /tools/dynamic` 可被能力面板消费，后续可选）。
- **测试**：+10 项；全量 547 项转绿。

**遗留**：动态工具不持久化（重启重置）；`POST /tools` 固定绑定 estimate_area handler（未支持任意 handler 上传，避免任意代码执行风险——当前是受控演示）；前端未消费 `/tools/dynamic`。

## M81.3：模板蓝图驱动的确定性 Planner（已完成）

### 目标与边界

M81.3 继续收敛“通用 Agent Runtime，而不是按具体问题堆规则”的核心目标。M68 已有工作流模板目录和计划校验，但模板主要承担 allowlist/约束/证据校验；RuleBasedPlanner 仍在 `rule_planning.py` 中用多个 `_build_*` 方法手写稳定 DAG。M81.3 将可声明的固定工作流推进为“模板蓝图 -> 可校验 TaskPlan”的路径，Planner 只负责把 RequestFacts 绑定到模板约束。

### 实现内容

- **`agent/workflow_templates.py`**：
  - 模板目录新增 `goal_template`、`step_blueprint`、`output_template`。
  - 新增 `compile_workflow_plan(template, constraints, evidence=...)`，把模板蓝图渲染为完整 plan，并复用既有 `validate_workflow_plan` 校验工具 allowlist、结果类型、依赖 DAG、约束和 evidence。
  - 支持受控占位符：`{"$constraint": "name"}` 绑定结构化约束，`{"$result_ref": {"step": "...", "path": "..."}}` 生成 Runtime 已支持的步骤结果引用。
  - 模板校验提前拒绝坏蓝图：未知字段、重复 step id、未知依赖、自依赖、循环依赖、工具不在模板 allowlist。
- **`agent/rule_planning.py`**：
  - 新增 `_template_plan`，将编译后的 JSON plan 转为 `TaskPlan`。
  - 行政区边界查询、栅格元数据、空间总览、道路/水体约束建设筛选改由模板编译生成。
  - Planner 内部从自然语言抽取出的 evidence 只作为软偏好，会按模板支持项过滤；外部 workflow 选择仍保持严格 evidence 校验。
  - 栅格数据集选择收敛为 `_raster_dataset`，显式支持 `dem`、`land_use` 和 `slope`。
- **测试**：
  - `tests/test_m68_workflow_templates.py` 新增模板编译、占位符渲染和坏蓝图拒绝测试。
  - `tests/test_m77_request_model.py` 新增 RuleBasedPlanner 与模板编译器输出一致性测试。
  - M69 workflow runtime 回归验证：外部选择的模板不允许 planner 计划时，仍优先返回“tool is not allowed by template”。

### 验收证据

- M68/M69/M77 专项 **32 项通过**。
- `python scripts/smoke_check.py` 通过；其中内嵌离线全量 **550 项通过，42 项跳过**，服务 smoke 通过。
- `git diff --check` 通过，仅有既有 Windows LF/CRLF 提示。
- 新增 `scripts/test_profile.py`、`tests/test_m81_test_profiles.py` 和 `docs/test-strategy.md`，把阶段验收从完整矩阵收敛为可执行 profile：`quick`、`stage`、`gis-core`、`live-short`、`docker`。
- M81.3 后补充收敛，M81.4.1 再次收窄默认门禁：`quick` 不再整模块跑 M68/M69/M77，只保留 3 个核心契约 tripwire；服务 smoke 独立为 `smoke` profile；`gis-core` 改为真实 GIS 抽样用例。完整 unittest/GIS/live 仍保留为按风险触发的专项矩阵。
- 真实环境抽样验收：GIS Python 全量 550 项通过、9 项跳过；analysis-ready 配置下 `live-short` 两个代表 case 2/2 通过，token 合计约 6,939，未发生 provider 错误或重试。

### 复盘（七维矩阵，M81.3）

- **产品能力**：稳定工作流可以从模板直接生成可执行计划，便于后续前端/HTTP 暴露“可解释的工作流”而不是隐藏在 planner 分支里。
- **架构**：RequestFacts、CapabilityRouter、WorkflowTemplate、TaskPlan 和 Runtime 的责任边界更清晰；RuleBasedPlanner 开始退化为模板绑定器。
- **数据质量**：无新增数据依赖；模板生成仍走既有 ToolRegistry 和后端数据健康门控。
- **真实模型**：LLMPlanner 尚未统一消费模板蓝图，下一阶段需要把 prompt 中的硬编码工具编排替换为模板/能力目录上下文。
- **部署可靠性**：模板蓝图在执行前复用同一计划校验，不新增部署状态；默认离线/CI 不依赖真实模型或私有数据。
- **前端体验**：前端暂未直接展示蓝图 DAG；但已有 `/workflows` 可继续消费模板目录，下一步可做工作流计划预览。
- **测试证据**：新增模板编译与 planner 一致性回归；Smoke 内嵌全量转绿；新增 profile 化测试入口，日常开发不再默认跑完整 live/矩阵。

## M81.4 全局规划（下一阶段）

1. **LLM Planner 与模板契约统一**：让 LLMPlanner 的上下文显式包含可用 workflow template 蓝图/约束/result type，使真实模型优先选择模板化计划，而不是依赖 prompt 中的手写工具步骤说明。
2. **Plan source 与可观测性**：在 `TaskPlan` 或运行 evidence 中记录 plan 来源（template/llm/direct/replan）、template_id、约束和裁剪后的模板证据，方便前端和评测解释“为什么调用这些工具”。
3. **前端计划预览**：基于模板蓝图和最终 `result.lineage` 显示计划 DAG、工具状态和结果引用，减少页面按工具名推断。
4. **评测与 CI**：增加脱敏 LLM 回放/离线 planner 案例，验证模型输出与模板 allowlist/result type/DAG 一致；默认 CI 仍不访问网络。
5. **保留边界**：暂不扩展新 GIS 数据功能，除非它服务于模板化 planner、Runtime 可观测或跨入口验收。

## M81.4：模板上下文与计划来源证据（已完成）

### 实现内容

- **模板上下文接口**：`agent/workflow_templates.py` 新增 `workflow_template_context_summary()`，为 Planner 提供受控模板摘要，不暴露完整原始目录实现细节。
- **上下文工程**：`ContextBuilder` 增加 `workflow_templates` section，预算裁剪优先保留模板契约；安全裁剪深度从 3 放宽到 5，避免核心数组被裁成不可匹配占位。
- **LLM Planner**：system prompt 明确说明可信上下文可能包含 `workflow_templates`，模型应优先按模板 DAG、result type、参数名、依赖和 result reference 生成普通 `TaskPlan`。
- **计划证据**：`AgentRuntime` 新增 `plan_evidence`，记录 planner kind、source、输出类型、步骤数、工具序列、模板上下文状态、workflow 约束和匹配模板；该证据已接入 `AgentRunResult`、SQLite、artifact、`result.planning` 和 Console。
- **前端证据**：Console 运行时证据卡显示“计划来源”，和上下文工程、运行血缘、几何、数据质量、发布证据一起展示。

### 验收证据

- M68/M77/M2 目标测试 **53 项通过**。
- `python scripts/test_profile.py --profile quick` 通过。
- `python scripts/test_profile.py --profile stage` 通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。

### 复盘（七维矩阵，M81.4）

- **产品能力**：用户和前端能看到“为什么调用这些工具”的计划来源证据。
- **架构**：模板目录通过一个小接口供 Planner 使用，Runtime 统一归档证据；Planner 仍只输出 `TaskPlan`。
- **数据质量**：无新增真实数据依赖；数据门控仍由既有工具和后端负责。
- **真实模型**：LLMPlanner 已具备模板上下文入口，但仍需下一阶段用脱敏回放和可选 live 验证真实模型稳定遵守模板。
- **部署可靠性**：新增字段可通过 SQLite 和 artifact 恢复；默认 CI/quick/stage 不访问真实模型或私有数据。
- **前端体验**：证据区显示计划来源，减少页面按工具名猜测执行意图。
- **测试证据**：新增模板摘要、上下文注入、LLM 上下文、plan evidence、SQLite 恢复和 Console 字符串测试；默认 quick 已收窄为 3 个核心 tripwire，服务 smoke 作为独立 profile 或 stage 的一部分运行。

## M81.4.1：测试入口再精简（已完成）

### 实现内容

- `scripts/test_profile.py`：`quick` 从“5 个核心样例 + 服务 smoke”收窄为 3 个核心契约 tripwire；新增独立 `smoke` profile；`stage` 改为组合 `quick + smoke + strict global evaluation`。
- `scripts/smoke_check.py`：默认只运行服务 smoke，完整 `unittest discover` 改为显式 `--with-unit-tests`，避免绕过 profile 分层。
- `gis-core` 抽样从 4 个真实 GIS 用例降为 3 个，保留行政区、Rasterio metadata 和 analysis-ready 门控，移除较重的坡度像素计算抽样。
- README、测试策略、恢复文档和中文问题日志已同步，明确完整矩阵只在风险触发时运行。

### 验收证据

- `python -m unittest tests.test_m81_test_profiles tests.test_m11_smoke_check -v`：6 项通过。
- `python scripts/test_profile.py --profile quick`：3 项核心 tripwire 通过。
- `python scripts/test_profile.py --profile smoke`：服务 smoke 通过，不嵌套完整 unittest。
- `python scripts/test_profile.py --profile stage`：quick、smoke、严格全局离线评测均通过。
- `git diff --check` 通过，仅有既有 Windows LF/CRLF 提示。

### 复盘（七维矩阵，M81.4.1）

- **产品能力**：没有新增 GIS 功能，但让开发者能更快验证核心 Agent 契约，降低测试摩擦。
- **架构**：测试入口职责更清晰，quick、smoke、stage、gis-core、live-short、docker 分层互不混淆。
- **数据质量**：真实数据验收仍保留在 `gis-core` 和 `live-short`，默认开发路径不依赖本地 GIS 数据。
- **真实模型**：live 仍为显式可选，不进入默认或 stage。
- **部署可靠性**：Docker acceptance 仍独立，避免和本地单测混跑。
- **前端体验**：无前端改动。
- **测试证据**：默认门禁从“单测 + smoke”缩短为 3 个核心 tripwire；阶段门禁仍能覆盖服务 smoke 和全局离线评测。

## M81.5：模板计划证据离线验收（已完成）

### 实现内容

- **脱敏模型回放**：`evaluation/model_evaluation.py` 新增 `workflow_template_match` 质量维度，评估真实模型计划是否匹配 workflow template 的 result type、工具 allowlist、max steps、DAG 和 result references。
- **模板匹配分层**：评测报告区分 `matched_template_ids` 和 `exact_template_ids`。前者证明输出类型、工具边界和步数属于模板族；后者证明 step blueprint、依赖和 result reference 形状完全一致。
- **严格 fixture**：`m67_spatial_overview_model.json` 增加 `expected_template_id: spatial_overview`，要求空间总览脱敏模型回放精确匹配 8 步模板蓝图。
- **HTTP/Console 验收**：新增 `tests/test_m81_plan_evidence_acceptance.py`，通过开发 HTTP server 执行行政区边界请求，验证顶层 `plan_evidence`、`result.planning` 和 artifact 中的模板计划证据一致；静态验收 Console 使用 `result.planning` 并显示 exact template。
- **默认门禁保持精简**：新增验收不进入 `quick`，阶段验证继续使用 `stage` 和目标测试。

### 验收证据

- `python -m unittest tests.test_m67_model_evaluation tests.test_m81_plan_evidence_acceptance -v`：11 项通过。
- `python scripts/test_profile.py --profile stage`：quick、smoke、严格全局离线评测均通过。
- 严格全局离线评测包含默认脱敏模型 fixture，已验证 `workflow_template_match` 通过。

### 复盘（七维矩阵，M81.5）

- **产品能力**：计划来源不只是页面展示字段，而是能被离线评测、HTTP 响应和 artifact 共同验证。
- **架构**：RuleBasedPlanner 与 LLMPlanner 继续共享 `TaskPlan`；模板契约验收在评测层复用公开模板摘要，不依赖 Runtime 私有 helper。
- **数据质量**：无新增真实 GIS 数据依赖；真实数据仍留在 `gis-core` / `live-short` 分层验收。
- **真实模型**：默认不访问网络，但用脱敏回放证明真实模型计划必须遵守模板 allowlist、result type、DAG 和 result references。
- **部署可靠性**：artifact 持久化包含 `plan_evidence`，跨进程或前端恢复时有同一证据来源。
- **前端体验**：Console 显示“计划来源”和 exact template，不再只能看到“完成了几步”。
- **测试证据**：新增目标测试覆盖回放、HTTP、artifact 和 Console 静态契约；默认 quick 没有膨胀。

## M81.6 全局规划（下一阶段）

1. **复杂 composer 模板化评估**：优先分析 `spatial_analysis`，决定是否补 `step_blueprint` 或拆成可组合子模板，减少复杂路径手写 DAG。
2. **计划预览与可解释 DAG**：让 HTTP/Console 能在执行前或执行中展示模板 DAG、依赖和参数来源，而不是只在完成后显示 plan evidence。
3. **跨入口一致性 Harness**：把 CLI、HTTP、artifact、历史恢复和 Console 的 result envelope 做更系统的一致性验收，覆盖复杂空间请求。
4. **可选真实验收**：仅在模板化复杂路径后再运行 `gis-core` 或 `live-short`，验证真实武汉数据和真实模型没有偏离离线契约。
5. **测试边界**：继续保持 `quick` 只跑 3 个核心 tripwire；新增验证进入目标测试或 `stage`，不恢复默认全量。

## M81.6：复杂空间分析蓝图化与跨入口一致性（已完成）

### 实现内容

- **`spatial_analysis` 蓝图化**：`agent/workflow_templates.py` 为组合式空间分析补充 9 步 `step_blueprint`，覆盖数据健康、行政区解析、高程、坡度、土地利用、道路、水体和道路/水体约束建设筛选。
- **Planner 接入**：`RuleBasedPlanComposer._build_composed` 对完整综合空间分析请求改用 `compile_workflow_plan("spatial_analysis", ...)` 生成 `TaskPlan`；局部组合请求仍保留旧 composer 兜底，避免过度调用未请求工具。
- **Context 压缩**：`workflow_template_context_summary(..., compact=True)` 为 Runtime Planner 上下文提供紧凑模板摘要，保留 id、goal、allowed tools、result types、required constraints、evidence、max steps 和 blueprint step/dependency/arg keys；评测默认摘要仍保留 `arg_shape`。
- **计划证据恢复**：新增蓝图后 `spatial_analysis` 复杂请求的 `plan_evidence.matched_template_ids` 与 `exact_template_ids` 均命中 `spatial_analysis`，且 `template_context_available=true`。
- **跨入口 Harness**：`tests/test_m81_plan_evidence_acceptance.py` 增加复杂请求一致性验收，比较直接服务调用、HTTP POST、HTTP run detail、session history 和 artifact 的 result envelope、计划证据、步骤序列、trace 与 artifact 可用性。

### 验收证据

- `python -m unittest tests.test_m81_plan_evidence_acceptance tests.test_m68_workflow_templates tests.test_m77_request_model -v`：33 项通过。
- `python scripts/test_profile.py --profile stage`：quick、smoke、严格全局离线评测均通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。

### 复盘（七维矩阵，M81.6）

- **产品能力**：用户的复杂综合请求不再只是 composer 手写 DAG，已能映射到可解释模板蓝图。
- **架构**：模板目录继续作为深模块接口，Planner 只绑定 RequestFacts 到模板约束；局部组合仍通过兜底实现，避免把 optional step 复杂度提前暴露到模板接口。
- **数据质量**：未新增真实数据依赖；真实武汉数据验收仍由 `gis-core` / `live-short` 分层处理。
- **真实模型**：LLMPlanner 上下文现在能看到更紧凑的复杂模板 DAG，默认仍不访问网络。
- **部署可靠性**：复杂请求的 HTTP、artifact、history 与直接服务调用共享一致 result envelope 和 plan evidence。
- **前端体验**：Console 已可显示复杂请求的 exact template 计划来源，后续可基于该蓝图做执行前计划预览。
- **测试证据**：新增复杂请求跨入口 Harness，默认 quick 未膨胀。

## M81.6.1：阶段测试例再精简（已完成）

### 实现内容

- **小型 stage acceptance**：新增 `evaluation/cases/stage-acceptance.json`，只保留通用问答、复杂空间分析模板、未注册空间问题澄清 3 个代表场景。
- **重型门禁显式化**：`scripts/test_profile.py --profile stage` 改为 `quick + stage_acceptance_examples`；旧式 `quick + smoke + strict global evaluation + 脱敏模型评测/回放` 改为显式 `full-stage`。
- **评测开关**：`scripts/evaluate_global.py` 新增 `--no-model-replay`，让小型 stage 可以同时跳过模型计划评测和多轮回放。
- **文档同步**：README、`docs/test-strategy.md`、`docs/demo-checklist.md`、恢复文档和中文问题日志同步更新，完整矩阵仍保留为按风险触发入口。

### 验收证据

- `python -m unittest tests.test_m81_test_profiles tests.test_m11_smoke_check -v`：profile/smoke 契约通过。
- `python scripts/test_profile.py --profile stage`：quick + 3 个离线 acceptance 场景通过。
- `python scripts/test_profile.py --profile full-stage --dry-run`：重型门禁保持可发现但不作为默认阶段入口。

### 复盘（七维矩阵，M81.6.1）

- **产品能力**：不新增 GIS 功能，降低 demo 开发和验收摩擦。
- **架构**：测试 profile 成为显式执行契约，stage 与 full-stage 分离，避免入口职责再次混杂。
- **数据质量**：默认 stage 仍只用内存后端；真实数据留在 `gis-core` / `live-short`。
- **真实模型**：普通 stage 不运行脱敏模型回放；模型质量验证保留在 `full-stage` 或目标测试。
- **部署可靠性**：Docker acceptance 仍独立，不进入普通 stage。
- **前端体验**：无前端改动。
- **测试证据**：普通阶段门禁从多层评测收敛为 3 个代表 acceptance 场景，完整回归仍可按风险显式运行。

## M81.7 全局规划（下一阶段）

1. **计划预览接口**：增加只规划不执行或轻量预览接口，输出模板 DAG、依赖、参数来源、预计 evidence 和安全门控，不触发 GIS 重计算。
2. **前端 DAG 展示**：Console 根据预览/执行结果渲染统一 DAG，而不是仅在证据卡显示模板名。
3. **LLM 模板遵守回放扩展**：增加 `spatial_analysis` 脱敏模型计划 fixture，验证真实模型也能精确遵守复杂蓝图。
4. **可选真实验收**：模板预览和 LLM 回放稳定后，再运行 `live-short` 或新增单个 live case；默认 CI 仍离线。

## M81.7：计划预览与 DAG 展示（已完成）

### 实现内容

- `AgentRuntime.preview()` 复用同一上下文构建、Planner、工作流校验和计划证据逻辑，只规划不执行 ToolRegistry，不保存运行结果，也不导出 artifact。
- Service、开发 HTTP 和生产 FastAPI 均提供 `POST /runs/preview`，共享 payload 归一化；预览结果包含 `TaskPlan`、DAG 节点/边、上下文证据、计划证据、规划指标和执行安全门控。
- Console 增加显式“预览计划”入口和 DAG 面板；前端只渲染 Runtime 返回的结构化计划，不自行决定工具顺序或区域参数。
- 预览结果与已执行运行使用不同边界：没有 `run_id`、工具步骤结果或 artifact 引用，避免用户把计划误认为事实结果。

### 验收证据

- `tests.test_m81_plan_evidence_acceptance`：5 项通过，覆盖复杂 9 步 DAG、预览无执行/无 artifact、开发 HTTP 路由和 Console 静态契约。
- Python 模块导入/编译通过；内嵌 Console JavaScript 抽取后 `node --check` 通过；`git diff --check` 通过。
- 预览接口不进入默认 `quick`，不调用真实模型、真实 GIS 或私有数据；真实 LLM/GIS 仍通过显式 profile 验证。

### 复盘（七维矩阵）

- **产品能力**：用户可以在执行前理解目标、工具节点和依赖，复杂空间问题不再只有执行后的黑盒轨迹。
- **架构**：预览位于 Runtime/Service seam，HTTP 和 Console 只消费结构化结果；计划与执行结果保持清晰边界。
- **数据质量**：预览不会触发 GIS 重计算，真实数据证据仍只在执行阶段产生。
- **真实模型**：rule planner 已完成离线预览契约；`spatial_analysis` 脱敏 LLM 回放和 live 验收保留为后续风险触发项。
- **部署可靠性**：开发 HTTP 与生产 FastAPI 共享 preview payload contract；预览没有持久化副作用。
- **前端体验**：增加显式预览动作和紧凑 DAG 展示，执行结果仍由动态结果区负责。
- **测试证据**：专项测试保持 5 项，不扩大 quick；阶段门禁继续使用精简 profile。

### M81.8 阶段规划（已执行）

1. **跨入口预览一致性**：补 CLI/Service、开发 HTTP、生产 FastAPI 和 Console 对同一 preview envelope 的一致性 Harness，明确规划状态、DAG、证据和错误分类。
2. **模型计划质量**：增加 `spatial_analysis` 脱敏 LLM fixture，验证复杂蓝图的工具 allowlist、步骤依赖、结果引用和输出类型；仅在必要时运行真实 live case。
3. **预览与执行关联**：设计受控 preview fingerprint 或 plan version，使用户能识别执行是否使用了刚刚预览的计划，同时不把预览伪装成运行记录。
4. **整体产品闭环复盘**：检查开放式问题、澄清、动态结果、地图证据、恢复、部署和测试七维是否仍由同一 Runtime 契约贯通，再决定是否进入新的 GIS 能力扩展。

## M81.8：跨入口预览一致性与复杂模型回放（已完成）

### 实现内容

- 新增 `m81_spatial_analysis_model.json` 脱敏模型 fixture，使用正常 `LLMPlanner -> TaskPlan parser -> AgentRuntime -> ToolRegistry` 链路回放复杂综合空间分析。
- fixture 验证 `spatial_analysis` 的 9 步工具序列、依赖关系、`$from` 结果引用、约束绑定、输出类型和中文答案；要求模板 exact match，而不是只比较工具集合。
- 新增 preview 跨入口 Harness：直接 `AgentService.preview()` 与开发 HTTP `POST /runs/preview` 逐字段比较状态、计划、DAG、上下文证据、计划证据、安全门控和空间上下文。
- 生产 FastAPI 保持同一 `preview_kwargs` 和 `/runs/preview` 路由；当前开发环境缺少 `fastapi`，因此用源码契约验证，不把可选依赖伪装成运行时通过。

### 验收证据

- M81.8 目标及相关回归 **41 项通过**；`python scripts/test_profile.py --profile stage` 通过。
- `spatial_analysis` 脱敏 fixture exact template match 通过，9 个工具步骤和 2990 个脱敏 token 指标被验证。
- Python 编译和 `git diff --check` 通过；本轮没有访问真实模型、提交私有 key 或读取真实 GIS 数据。

### 复盘（七维矩阵）

- **产品能力**：复杂开放式空间问题同时具备执行前计划证据和模型计划质量证据。
- **架构**：preview 仍由 Runtime/Service 深模块提供，入口层不重复编排；生产路由与开发路由共享参数契约。
- **数据质量**：模型回放使用 Demo adapter，不把脱敏计划误报为真实武汉数据结论；真实数据证据继续由 GIS profile 负责。
- **真实模型**：真实模型输出的离线代表样例已能精确遵守 `spatial_analysis` 蓝图；live 仍受 provider、key 和网络条件控制。
- **部署可靠性**：FastAPI 路由存在且共享 contract，但当前宿主缺少 `fastapi`，运行时 production acceptance 仍是部署环境验收项。
- **前端体验**：Console 已消费统一 preview 结构，复杂计划可以在执行前查看节点和依赖。
- **测试证据**：新增目标测试不进入默认 quick；stage 保持精简，生产可选依赖缺失被明确记录而非隐藏。

## M81.9：计划身份与真实模型质量验收（已完成）

### 实现内容

- 新增 `agent/plan_identity.py`，基于请求、解析后的请求、工作流、Planner 类型和结构化 TaskPlan 生成 credential-free 的 `sha256` fingerprint，版本为 `spatial-agent.plan-identity.v1`。
- preview 返回 `plan_identity`；执行请求可通过 `preview_fingerprint` 显式要求计划一致，Runtime 在任何 ToolRegistry dispatch 前校验，不一致直接失败且不执行工具；同步/异步 API 参数均保留该字段。
- 修正 LLM Planner 对复合空间请求的模板优先级，真实 DeepSeek 现在能精确匹配 `spatial_analysis` 9 步蓝图。

### 验收证据

- fingerprint 一致/不一致两条执行路径和相关 Runtime/HTTP/异步测试通过；目标回归 38 项通过，Python 编译和 `git diff --check` 通过。
- 真实直连 DeepSeek Chat Completions：DEM 元数据请求 `COMPLETED`、`raster_metadata_result`、3412 tokens；修复后的洪山区复合 preview `PLANNED`、9 步、matched/exact 均为 `spatial_analysis`；修复后的实际执行 `COMPLETED`、9/9 步完成、`spatial_analysis_result`。
- 真实调用使用临时环境变量，未写入 key、配置文件或仓库；默认 CI/stage 仍不访问网络。

### 复盘（七维矩阵）

- **产品能力**：用户可以把执行明确绑定到刚刚预览的计划，复杂模型结果不再只以“执行成功”判断质量。
- **架构**：plan identity 位于 Runtime/Service seam，入口仅传递 fingerprint；异步快照复用同一字段，未新增页面编排逻辑。
- **数据质量**：本轮真实模型执行使用内存 Demo backend，验证的是计划质量，不把它宣称为武汉真实 GIS 证据。
- **真实模型**：真实 DeepSeek 已完成最小元数据和复杂复合请求验证；网关与官方直连仍按 provider 分开记录。
- **部署可靠性**：生产 FastAPI 路由代码存在，但当前宿主没有 `fastapi`，运行时 acceptance 尚未完成。
- **前端体验**：preview identity 已在结构化响应中可用，后续可在执行结果显示是否复用了预览计划。
- **测试证据**：新增验证保持在专项/目标测试，不扩大默认 quick/stage。

### M81.10 全局规划

1. 在安装 `requirements-prod.txt` 的隔离环境或生产容器中补 FastAPI 最小 acceptance，覆盖 `/runs/preview`、`/runs`、readiness 和错误响应，仍不进入默认 CI。
2. 将 `plan_identity` 接入 Console 执行结果和 artifact/lineage，显示预览与执行的匹配状态，不暴露原始上下文。
3. 对真实 GIS backend 运行一个带 `preview_fingerprint` 的 live-short 样例，分别记录模型计划、数据门控、后端和几何证据。
4. 完成产品、架构、数据、模型、部署、体验、测试七维全局复盘，决定下一阶段是扩展通用 RequestFacts/能力发现，还是进入新的可替换工具/后端能力。

## M81.10：生产 FastAPI 与预览绑定验收（已完成）

### 实现内容

- `scripts/production_acceptance.ps1` 扩展为生产入口契约门禁，覆盖 liveness、readiness、runtime capabilities、核心/可选数据卷、`/runs/preview`、带 `preview_fingerprint` 的 `/runs`、错误响应 envelope、异步提交/幂等/轮询。
- Console 现在在计划预览和结果证据中显示 `spatial-agent.plan-identity.v1`、短 fingerprint 和“预览匹配”状态；预览后执行同一请求会自动携带 `preview_fingerprint`。
- 生产容器使用当前代码重建，并明确使用 `--env-file .env.production` 让数据卷变量参与 Compose 插值；私有 key 和本地配置仍由 `.dockerignore` / `.gitignore` 排除。

### 验收证据

- 生产容器 acceptance 通过：`readiness=ready`、`runtime_health=ready`、核心/可选数据均 `ready`、`preview_status=PLANNED`、`sync_preview_fingerprint_match=true`、错误响应 `400/invalid_request`、异步幂等完成。
- 真实本地 GIS backend 样例通过：`/runs/preview` 2 步，执行 `COMPLETED`，`admin_area_result`，fingerprint 匹配，artifact 与 GeoJSON 均导出。
- 当前 DeepSeek-compatible 中转配置 smoke 通过：`deepseek-v4-flash`、Chat Completions、`status=COMPLETED`、`raster_metadata_result`、1 个工具步骤、3546 tokens、无重试。
- Console inline JavaScript 语法检查通过；M81 plan evidence 目标测试 8 项通过。阶段收口复跑 `quick`、`stage`、production acceptance 和 `git diff --check` 通过后提交版本。

### 复盘（七维矩阵）

- **产品能力**：用户可以先看计划 DAG，再执行并确认实际运行是否复用了预览计划。
- **架构**：预览、执行、artifact、Console 和生产 API 共享同一 plan identity，不在页面侧重复编排。
- **数据质量**：生产验收先验证真实武汉数据卷可见性和 readiness，避免把空数据卷下的服务健康误认为 GIS 可用。
- **真实模型**：中转大模型链路可用；默认 quick/stage 仍离线，真实模型只作为显式 live/smoke 证据。
- **部署可靠性**：Docker production acceptance 覆盖数据卷、同步/异步 API 和错误 envelope；Compose 插值陷阱已记录。
- **前端体验**：计划身份和匹配状态进入结果证据区，用户能区分“只预览”“已执行但未绑定”“执行与预览一致”。
- **测试证据**：生产验收和专项测试增强，但默认 quick 保持 3 个核心 tripwire，不扩大日常反馈面。

## M82 全局规划（下一阶段）

1. **开放式 RequestFacts 与能力发现**：把更多空间问法抽取为统一实体、约束、证据偏好和输出意图，减少 prompt 或 rule composer 中的专用表达判断。
2. **模板与工具可替换性**：继续把稳定 DAG 从代码 composer 下沉到 `WorkflowTemplate`，并为动态工具注册增加能力目录发现、版本和安全边界证据。
3. **跨入口 Harness**：用同一复杂请求覆盖 CLI、开发 HTTP、生产 FastAPI、Console、artifact 和 session recovery 的 result envelope、trace、lineage、plan identity 一致性。
4. **真实数据降级矩阵**：补空数据卷、缺道路/水体、栅格未对齐、GeoJSON 截断、后端不可用的代表性生产/本地 GIS 验收。
5. **真实模型质量基线**：保留精简 live smoke，增加脱敏回放与 live 差异报告，重点检查模板 exact、澄清质量、token/延迟和 provider 错误分类。

## M82.1：能力发现上下文与计划证据（已完成）

### 实现内容

- 新增 `spatial-agent.capability-discovery.v1`，`CapabilityRouter.discover()` 在保持 `select()` 兼容的同时输出 JSON-safe 的信号、任务、约束、候选能力和选中能力。
- `AgentRuntime` 构建 Planner 上下文时只解析一次 RequestFacts，并把 `capability_discovery` 作为受信上下文注入；`plan_evidence` 同步暴露 `selected_capability_id`、候选能力、候选数量和匹配信号。
- `ContextBuilder` 的预算裁剪顺序调整为优先保留稳定 `workflow_templates`，能力发现摘要保持紧凑，避免新增上下文挤掉模板契约。
- Console 运行证据区显示“能力发现”，用户能看到 Runtime 选择的能力和候选能力列表。

### 验收证据

- M77/M81 目标测试 27 项通过，覆盖能力发现 JSON-safe、Runtime 上下文注入、计划证据透出、Console 静态证据和复杂请求跨入口契约。
- 本轮暂未运行真实 GIS、Docker production acceptance 或 live 模型；默认 quick/stage 仍保持离线边界，后续阶段再按风险显式运行。

### 下一阶段规划

1. 将能力发现从“候选能力列表”推进为 Planner 可消费的能力目录摘要：工具 schema、数据门控、后端支持状态、版本与安全边界。
2. 继续模板化稳定 DAG，优先处理仍留在 composer 中且已具备稳定工具序列的组合能力。
3. 补跨入口 Harness，确认 capability discovery、workflow template、plan identity、trace 和 artifact 在 CLI/HTTP/生产/Console/session recovery 中一致。

## M82.2：Planner 能力目录摘要（已完成）

### 实现内容

- 新增 `spatial-agent.capability-catalog-context.v1`，从现有 `capability_catalog` 生成候选能力范围内的紧凑 Planner 上下文，包含数据集、工具、result type、环境支持、数据门控、缺失数据、geometry 语义和 analysis-ready 摘要。
- `ToolRegistry.definition_summary()` 提供只读工具参数摘要：required args、参数类型、enum、上下限、side effect、approval 和输出必填字段；仍不暴露可执行 handler 或绕过 Registry。
- `AgentRuntime` 接收 `backend_name`，Runtime factory 将 memory/local 传入；Planner 上下文和 `plan_evidence` 现在能说明能力目录是否可用、当前后端、能力 id 和工具 schema 数量。
- `LLMPlanner` prompt 明确：`capability_catalog` 用于能力/数据/后端/参数边界判断，`workflow_templates` 仍是更强的执行 DAG 契约。
- 默认 `ContextBuilder` 预算从 8,000 提高到 12,000 字符；显式小预算测试仍覆盖裁剪行为。目录摘要只展开候选能力，不填充无关能力，避免再次挤掉模板契约。

### 验收证据

- M59/M77/M81 目标测试 37 项通过（1 项因缺少 FastAPI 依赖跳过），覆盖能力目录摘要、工具 schema 摘要、Runtime 上下文注入、计划证据和 LLM prompt。
- 本轮仍未运行真实 GIS、Docker production acceptance 或 live 模型；这些保持为后续显式验收路径。

### 下一阶段规划

1. 补跨入口 Harness，验证 `capability_discovery`、`capability_catalog`、`workflow_templates`、`plan_identity`、trace、artifact 和 session recovery 在 CLI/HTTP/生产/Console 中一致。
2. 再评估需要下沉到 `WorkflowTemplate` 的剩余稳定 DAG，避免继续在 composer 或 prompt 中堆分支。
3. 在 Harness 稳定后再安排真实数据降级矩阵和真实模型质量基线。

## M82.3：CLI/HTTP/artifact/session 跨入口 Harness（已完成）

### 实现内容

- `run_demo.py` 改为复用 `AgentService.run()` 输出统一 payload，CLI 现在与 HTTP/Service 共享 `result` envelope、中文答案、`trace_summary`、`provenance`、`plan_evidence` 和可选 artifact 引用；`build_runtime` re-export 保持兼容。
- CLI 新增 `--export-artifact`、`--artifact-root` 和 `--export-geojson` 参数，支持在命令行验收中导出同一结构化 artifact。
- M81 跨入口 Harness 扩展为 direct service、CLI、开发 HTTP、run detail、artifact fallback recovery、session history 和 Console 静态证据的统一断言，重点覆盖 `capability_discovery`、`capability_catalog`、`workflow_templates` 和 `plan_identity`。
- Console 运行证据区新增“能力目录”行，显示后端、选中能力目录 id 和工具 schema 摘要数量。
- Runtime 的 Planner 能力目录详情从“多个候选能力”收紧为“选中能力详情”；候选排序仍由 `capability_discovery` 提供，避免复杂请求再次挤掉模板契约。

### 验收证据

- M81/M9/M78 目标测试 18 项通过（1 项本地 GIS 依赖跳过），覆盖 CLI follow-up 兼容、CLI/HTTP/artifact 契约一致、Service split 边界不回退。
- M59/M77/M81 回归 38 项通过（1 项 FastAPI 依赖跳过），确认能力目录摘要、上下文注入、复杂模板 exact 和跨入口契约仍稳定。
- 本轮尚未运行 Docker production acceptance、真实 GIS 或 live LLM；下一阶段按显式验收路径处理。

### 下一阶段规划

1. 补生产 FastAPI/可选 Docker 的同字段 contract gate，确认 M82 新增证据在生产入口与开发 HTTP 一致。
2. 开始真实数据降级矩阵：空数据卷、缺道路/水体、栅格未对齐、后端不可用、GeoJSON 截断。
3. 再做真实模型质量基线，将 live 结果与脱敏/模板 exact 证据对齐。

## M82.4：生产入口 M82 证据门禁（已完成）

### 实现内容

- `scripts/production_acceptance.ps1` 新增 `Assert-PlanningEvidence`，生产同步运行现在检查 `capability_discovery`、`capability_catalog`、选中能力、候选能力、能力目录 id、能力目录后端和 plan identity 在 `plan_evidence` 与 `result.planning` 中一致。
- 生产同步运行启用 `export_artifact=true`，验收脚本通过 `/artifacts/runs/{name}` 读取 artifact，并确认 artifact 中的 `plan_evidence` 保留选中能力与能力目录证据。
- 验收输出新增 `sync_selected_capability`、`sync_capability_catalog_environment` 和 `sync_artifact_available`，便于 Docker production acceptance 报告直接暴露 M82 证据状态。
- `tests/test_m66_data_volume.py` 增加静态契约测试，防止生产验收脚本回退为只检查 readiness / preview fingerprint。

### 验收证据

- M66/M63/M81 目标测试 16 项通过（2 项因 live Docker / FastAPI 依赖跳过）。
- `production_acceptance.ps1` 通过 PowerShell parser 语法解析；`quick`、`stage`、Python 编译和 `git diff --check` 通过（仅 Windows LF/CRLF 提示）。
- 本阶段没有启动 Docker production acceptance，也没有访问真实 GIS 或 live LLM；脚本门禁已就绪，运行证据留到显式 Docker/GIS 阶段。

### 下一阶段规划

1. 进入真实数据降级矩阵：设计可离线/可选 GIS 的 fixture 和 acceptance，覆盖空数据卷、缺道路/水体、栅格未对齐、后端不可用、GeoJSON 截断。
2. 将降级矩阵结果接入 result envelope / answer / trace 的一致性 Harness，证明“明确降级”不是只在工具错误字符串里出现。
3. 再安排真实 LLM 质量基线，重点验证 open-ended Planner 在能力目录、模板 exact 和降级场景中的行为。

## M82.5：结构化降级矩阵（已完成）

### 实现内容

- result_contract.py 新增 spatial-agent.degradation.v1，在 result.degradation 和 result.data.degradations 中输出有界降级矩阵：status、item_count 和 {code, severity, message, source} 项。
- 降级矩阵由后端统一派生，覆盖运行未完成、需要澄清、几何缺失/截断、工具步骤错误、工具结果中的 statistics.error / summary.error、数据健康 degraded/unavailable、data_readiness=not_ready、analysis-ready、source binding 和 output manifest 限制。
- ArtifactStore 在最终刷新 artifact 时写入 result 和顶层 degradation，artifact fallback recovery 能继续返回同一套降级矩阵。
- Console 证据区优先读取 result.degradation；旧响应没有结构化矩阵时才保留浏览器端兼容推断，避免前端成为降级判断源头。
- production_acceptance.ps1 新增 Assert-DegradationEvidence，生产同步响应和 artifact 都要带同一 schema 的降级证据，并在报告中输出 sync_degradation_status。

### 验收证据

- M76/M76.2.4/M81/M66 目标测试 26 项通过（1 项 live Docker acceptance 跳过）。
- production_acceptance.ps1 通过 PowerShell parser 语法解析。
- 抽样复杂内存后端综合空间分析返回 status=COMPLETED 但 result.degradation.status=degraded，包含内存演示后端、DEM 像元、土地利用像元、道路/水体几何和约束建设筛选限制，artifact 同步保留该矩阵。
- 本阶段未启动 Docker production acceptance、真实 GIS 或 live LLM；默认验证继续保持离线。

### 下一阶段规划

1. 从全局 Agent Runtime 角度重新盘点产品能力、架构边界、数据质量、真实模型、部署可靠性、前端体验和测试证据，避免只围绕单个降级样例继续堆分支。
2. 规划 M83 时优先补“结果类型与前端动态工作区”的通用 contract：让不同 result.type 决定可视化、表格、地图、证据和 artifact 展示，而不是页面硬编码局部场景。
3. 在 M83 后再安排可选 GIS/Docker/live 验收，把真实武汉数据和真实大模型作为 acceptance，不进入默认 quick/stage。

## M83：后端驱动的动态工作区契约（已完成）

### 实现内容

- result_contract.py 新增 spatial-agent.workspace.v1，在 result.workspace 中输出 result_type、registered_type、primary_panel、common_panels、panels 和 map 证据。
- 后端维护 result type 到工作区 panel 的映射，覆盖能力目录中的全部 result_types；地图面板由后端根据 GeoJSON 几何或栅格 bounds 证据决定。
- Console 删除前端 result-type registry，不再通过工具名推断 raster/health/composite/buildability/map 面板；前端只把 workspace panel 名映射到 DOM 区域，工具结果只负责填充已选中的 panel。
- renderRun 去掉后置 monkey patch，所有结果面板填充集中在同一渲染流程；raster metadata 现在能在栅格面板中显示文件数、尺寸、波段、像元大小、CRS 和样本文件。
- production_acceptance.ps1 新增 Assert-WorkspaceEvidence，生产同步响应和 artifact 都要保留同一 workspace schema，并输出 sync_workspace_panels。

### 验收证据

- M46/M79/M81/M76 目标测试 29 项通过。
- M66 生产静态门禁 6 项通过（1 项 live Docker acceptance 跳过），production_acceptance.ps1 PowerShell parser 通过。
- quick 和 stage profile 均通过；Python 编译通过；git diff --check 仅有 Windows LF/CRLF 提示。
- 本阶段未运行 Docker production acceptance、真实 GIS 或 live LLM；真实入口保持为后续显式验收路径。

### 下一阶段规划

1. 继续从全局 Agent Runtime 视角规划 M84，不围绕单个页面细节扩展。
2. 建议下一阶段做 result artifact/view model 的更深 contract：把 panel 内部的 metrics/table/chart/map payload 也逐步结构化，减少前端继续扫描 steps 填内容。
3. 在 view model 稳定后，再跑一次 Docker/GIS/live 的小型 acceptance，验证真实数据和真实模型路径仍能输出 workspace、degradation、planning、lineage 四类证据。

## M84：后端结果视图模型契约（已完成）

### 实现内容

- `result_contract.py` 新增 `spatial-agent.views.v1`，在 `result.views.panels` 中输出由后端决定的面板内容 view model。
- 栅格面板新增 `raster_metadata` 与 `raster_statistics` view，包含有界 metrics、标题、来源 step、样本说明、分布与覆盖率摘要；地图 view 支持 GeoJSON 与栅格 bounds 两种模式。
- 空间总览面板新增 `spatial_overview` view，统一输出工具步骤数、数据来源数、空间要素数、空间证据状态与说明。
- Console 新增 `resultViewPanels()` 与 `renderMetricGrid()`，栅格和空间总览面板优先消费 `result.views.panels`，不再扫描 `steps` 自行推断面板内部指标；栅格 bounds 预览也改用后端 map view。
- M46/M79 合约测试扩展为所有能力目录 result type 都必须带 `spatial-agent.views.v1`，并断言前端已移除栅格/总览的局部 step scan。

### 验收证据

- M46/M79 目标测试 15 项通过。
- M46/M79/M81/M76/M66 相关回归 37 项通过（1 项 live Docker acceptance 跳过）。
- Python 编译、quick profile、stage profile 和 `git diff --check` 均通过；`git diff --check` 仅输出 Windows LF/CRLF 提示。
- 本阶段未运行 Docker production acceptance、真实 GIS 或 live LLM；默认 quick/stage 继续保持离线边界。

### 下一阶段规划

1. 从全局 Agent Runtime 视角规划 M85，优先补齐剩余复杂面板的 backend view model，包括 health、composite、buildability、vector/table/chart，而不是继续在前端按工具结果写分支。
2. 将 `views` 纳入 artifact、HTTP run detail、session recovery 和 production acceptance 的结构化证据，确保 CLI/API/Console 看到同一套展示数据。
3. 在 `workspace/degradation/planning/lineage/views` 五类 result envelope 证据稳定后，再安排一个小型真实 GIS + live LLM + Docker acceptance，验证真实模型和真实数据路径没有回退。

## M85：复杂结果面板 View Model 收敛（已完成）

### 实现内容

- `result.views.panels` 扩展 `dataset_health`、`spatial_composite` 和 `buildability_screening` 三类 view model，把健康检查、综合分析和建设筛选的 metrics、rows、categories、coverage、note 都收敛到后端 result contract。
- Console 的 `healthStats`、`compositeStats` 和 `buildabilityStats` 改为消费 `resultViewPanels(data)`，删除按工具名扫描 `steps` 的页面端业务聚合；前端只负责渲染后端 view payload。
- `production_acceptance.ps1` 新增 `Assert-ViewEvidence`，检查同步响应和 artifact 都包含 `spatial-agent.views.v1`，并验证 view panel 不越过 workspace 声明。
- M46/M79/M66 静态契约测试覆盖复杂面板 view model、前端去工具名扫描和生产验收 views schema。

### 验收证据

- M46/M79 目标测试 16 项通过。
- M46/M79/M81/M76/M66 相关回归 38 项通过（1 项 live Docker acceptance 跳过），覆盖 result envelope、Console 静态契约、artifact/recovery、production acceptance 静态门禁。
- Python 编译、quick profile、stage profile、production acceptance PowerShell parser 和 `git diff --check` 均通过；diff check 仅有 Windows LF/CRLF 提示。
- 阶段默认验证保持离线；真实 Docker/GIS/live LLM 仍作为后续显式 acceptance。

### 下一阶段规划

1. 从全局 Agent Runtime 视角规划 M86，不再围绕页面局部追加指标；优先补 `views` 在 artifact/run detail/session recovery 的跨入口一致性 Harness，并检查 CLI/HTTP/Console 对同一复杂请求的 view panels 是否一致。
2. 评估 vector/table/chart 通用 view contract，避免为每种 GIS 结果写新的 DOM 专用分支。
3. 在 result envelope 五类证据稳定后，安排小型真实 GIS + live LLM + Docker acceptance，验证真实模型、真实数据和生产入口都保留 planning/lineage/degradation/workspace/views。

## M86：Views 跨入口一致性恢复（已完成）

### 实现内容

- M81 跨入口 Harness 的 `_normalized_contract()` 纳入 `result.views.schema_version`、view panel 集合和 panel kind，直接比较 direct service、HTTP `/runs`、HTTP run detail、CLI 和 artifact fallback recovery。
- HTTP/artifact 断言扩展为 `artifact.result.views == run.result.views`，CLI artifact 也必须保留同一套 views envelope。
- 修复 `AgentService.get_run()` 的 artifact fallback 恢复路径：当 artifact 已包含最终 `result.views` 时，恢复详情保留该结构化展示契约，避免因缺少完整 `steps` 重新 build 出空 view panels。

### 验收证据

- M81 目标 Harness 9 项通过，覆盖 preview、complex contract、CLI/HTTP/artifact、run detail 和 artifact fallback recovery。
- 阶段默认验证仍保持离线；完整相关回归和 profile 验收在提交前执行。

### 下一阶段规划

1. 从全局 Agent Runtime 视角规划 M87，优先设计 vector/table/chart 通用 view contract，而不是为单个 GIS 工具继续写页面分支。
2. 将 artifact viewer 和任何后续展示入口统一迁移到 `result.views`，让 artifact 既是审计记录，也是可复现展示 payload。
3. 在通用 view contract 稳定后，安排小型真实 GIS + live LLM + Docker acceptance，验证真实入口仍保持 planning/lineage/degradation/workspace/views 一致。

## M87：Artifact Viewer 消费 Result Views（已完成）

### 实现内容

- `agent/artifact_viewer.py` 新增 `Result Views` 区块，直接读取 artifact 中的 `result.views.panels`，渲染 schema、panel 名、kind、metrics 和 note。
- Artifact viewer 继续保持自包含、无前端依赖、HTML escape 安全边界；没有 views 的旧 artifact 仍按原有 Plan / Tool Steps / Answer / Trace 展示。
- `tests/test_m17_artifact_viewer.py` 新增 views 渲染测试，确认 artifact HTML 能展示 `spatial-agent.views.v1`、panel kind 和 metric 内容。

### 验收证据

- M17 artifact viewer 目标测试 3 项通过。
- `agent/artifact_viewer.py` Python 语法编译通过。

### 下一阶段规划

1. 从全局 Agent Runtime 视角规划 M88，优先设计 vector/table/chart 通用 view contract，补齐非栅格/非建设类结果的可复现展示 payload。
2. 将通用 view contract 纳入跨入口 Harness，确保 Console、artifact viewer、CLI/HTTP artifact 对同一 result type 使用同一 view model。
3. 在 vector/table/chart contract 稳定后，再安排小型真实 GIS + live LLM + Docker acceptance。

## M88：矢量结果 View Contract（已完成）

### 实现内容

- `result_contract.py` 在 `spatial-agent.views.v1` 下新增 `vector` panel，覆盖 `range_query`、`get_zonal_vector_summary` 和 `spatial_join` 三类输出。
- `vector_query`、`zonal_vector_summary` 和 `spatial_relation` view model 只暴露有界 metrics、rows、分类 table 和 result_ref，不内联原始几何，保持 artifact/GeoJSON 作为详细要素出口。
- `zonal_vector_summary_result`、`zonal_vector_result`、`vector_result`、`spatial_relation_result` 和 `spatial_result` 都由后端 workspace/view contract 驱动结构化结果展示。
- Console 的结构化结果区优先消费 `resultViewPanels(data).vector`，渲染 metric grid、rows 和 `renderViewTable(view.table)`；没有 vector view 时才保留 JSON fallback。

### 验收证据

- M46/M79 目标测试 17 项通过。
- M17/M46/M79/M81/M76/M66 相关回归 42 项通过（1 项 live Docker acceptance 跳过），覆盖 artifact viewer、result envelope、Console 静态契约、跨入口 consistency、lineage/degradation 和生产静态门禁。
- Python 编译、quick profile、stage profile 和 production acceptance PowerShell parser 均通过。
- 阶段默认验证保持离线；真实 Docker/GIS/live LLM 仍作为后续显式 acceptance。

### 下一阶段规划

1. 从全局 Agent Runtime 视角规划 M89，继续把 table/chart 通用展示 payload 下沉到 `result.views`，不要回到页面端按工具名拼内容。
2. 补齐 artifact viewer 对 table payload 的结构化渲染，让 artifact 成为可复现展示面，而不是只显示 metric 摘要。
3. 在通用 view contract 稳定后，安排小型真实 GIS + live LLM + Docker acceptance，验证真实模型、真实数据和生产入口都保留 planning/lineage/degradation/workspace/views。

## M89：Artifact Viewer 渲染 Rows/Table View（已完成）

### 实现内容

- `agent/artifact_viewer.py` 的 `Result Views` 区块通用渲染 view `rows` 和 `table` payload，不再只显示 metrics/note。
- rows/table 渲染保持自包含、dependency-free，并继续做 HTML escape、行列数量裁剪和长文本裁剪。
- 新增 M17 测试覆盖矢量分类 table、rows 和 HTML escape，确保 artifact 展示能力跟上 Console 的 `result.views` payload。

### 验收证据

- M17 artifact viewer 目标测试 4 项通过。
- M17/M46/M79/M81 相关回归 30 项通过，覆盖 artifact viewer、result envelope、Console 静态契约和跨入口一致性 Harness。
- Python 编译、quick profile、stage profile、production acceptance PowerShell parser 和 `git diff --check` 均通过；diff check 仅有 Windows LF/CRLF 提示。
- 阶段默认验证保持离线；真实 Docker/GIS/live LLM 仍作为后续显式 acceptance。

### 下一阶段规划

1. 从全局 Agent Runtime 展示短板重新规划 M90：在 chart view contract、真实 GIS/live LLM/Docker 小型 acceptance、前端结果区体验之间排序。
2. 保持原则：新增展示能力先扩展 backend `result.views` 和跨入口证据，再让 Console/artifact 渲染；不回到页面端按工具名推断业务语义。
3. 默认 quick/stage 继续离线；真实 GIS、Docker 和 live LLM 只作为显式 acceptance 路径。

## M90：Comparison Chart View Contract（已完成）

### 实现内容

- `result_contract.py` 新增 `build_comparison_views()`，为比较型结果生成 `spatial-agent.views.v1` 的 `chart` panel，包含 metrics、bar chart series、encodings、table 和 note。
- `AgentService.compare_buildability()`、`compare_buildability_regions()`、`compare_constrained_buildability()` 均返回顶层 `views.panels.chart`；结果对比不再只靠前端扫描 rows 构造图表。
- Console 的比较面板优先消费 `resultViewPanels(data).chart` 和 `renderChartView(view)`；旧 `results` 表格保留为兼容 fallback。
- `agent/artifact_viewer.py` 同步渲染 `comparison_chart` series，并继续支持 rows/table、HTML escape 和数量裁剪。

### 验收证据

- M46/M57/M79/M17 目标测试 29 项通过。
- M17/M46/M57/M79/M81/M76/M66 相关回归 51 项通过（1 项 live Docker acceptance 跳过），覆盖 result contract、service comparison、Console 静态契约、artifact viewer、跨入口 consistency、lineage/degradation 和生产静态门禁。
- Python 编译、quick profile、stage profile、production acceptance PowerShell parser 和 `git diff --check` 均通过；diff check 仅有 Windows LF/CRLF 提示。
- 阶段默认验证保持离线；真实 Docker/GIS/live LLM 仍作为后续显式 acceptance。

### 下一阶段规划

1. 从全局 Agent Runtime 角度规划 M91：优先做小型真实 GIS + live LLM + Docker acceptance，验证真实入口仍保持 planning/lineage/degradation/workspace/views 一致。
2. MCP 暂不进入核心 Runtime seam；后续如工具来源继续增长，应作为 `MCPToolProvider` adapter 接入 ToolRegistry，而不是替代 ToolRegistry/CapabilityCatalog/WorkflowTemplate。
3. 若真实 acceptance 暂时受环境阻塞，则先补显式 ToolProvider adapter 设计文档和接口测试，不能回到单工具堆规则。

## M91：真实入口小型 Acceptance 与 View 验收修复（已完成）

### 实现内容

- `scripts/production_acceptance.ps1` 的 `Assert-ViewEvidence` 过滤空 view panel 名，避免把合法空 `views.panels` 误判为“未由 workspace 声明的 panel”。
- 验收摘要中的 `sync_view_panels` 同样过滤空属性名，保留真实契约：非空 view panel 必须出现在 `result.workspace.panels` 中。
- `tests/test_m66_data_volume.py` 增加静态门禁，防止生产验收脚本回退到未过滤空 panel 名的实现。

### 验收证据

- `tests.test_m66_data_volume` 6 项通过（1 项 live Docker acceptance 按环境门控跳过）。
- production acceptance PowerShell parser 通过。
- Docker production acceptance 通过：liveness ok、readiness ready、runtime/data/core/optional health 均 ready、核心/可选缺失数据集为空、同步运行 `COMPLETED`、artifact 可用、异步运行 `COMPLETED`、重复提交幂等为 true。
- 真实本地 GIS 生产抽样通过：`查询洪山区行政区边界` 返回 `admin_area_result`，GeoJSON/map view 可用，`feature_count=1`。
- 真实 LLM 生产抽样通过：`planner=openai` 的 `查询DEM栅格元数据` 返回 `raster_metadata_result`，1 个工具步骤，`workspace.panels=[raster,map]`，`views.panels=[raster,map]`。

### 下一阶段规划

1. 从项目整体规划 M92：工具数量增长后，优先深化 ToolRegistry/ToolProvider 接口，而不是把 MCP 放进核心 Runtime seam。
2. 设计 `ToolProvider` 抽象：内置工具先作为 `NativeToolProvider`，未来 `MCPToolProvider` 只负责把外部工具转成 ToolRegistry 可校验定义。
3. 验收重点放在 schema 校验、参数校验、权限/数据依赖、统一 dispatch、trace、degradation、workspace/views 和 artifact 一致性，避免工具来源变多后重新分散业务契约。

## M92：ToolProvider 可替换工具来源 Seam（已完成）

### 实现内容

- 新增 `agent/tool_provider.py`，定义最小 `ToolProvider` 接口和进程内 `NativeToolProvider`；provider 只负责定义目录和 provider-specific invocation。
- `ToolRegistry` 新增 `from_provider()`、`provider_info()`，并将 `from_json()` 迁移到 Native provider；旧的 definitions/adapter 构造方式保持兼容。
- Registry 仍是唯一执行 seam：provider 调用前必须通过工具 schema 和参数校验，动态工具、统一错误归一和结果导出仍由 Registry 控制。
- Capability context 与 plan evidence 记录有界 `tool_provider` 身份和工具数量，不暴露 handler、连接信息或密钥；MCP 不作为核心依赖。
- 更新历史回归测试以匹配当前 `result.views`、`result.geometry` 和 `preview_fingerprint` 契约，避免旧前端标记和过时的几何排除断言阻塞全量验证。

### 当前验收证据

- ToolProvider 专项测试 5 项通过，覆盖 Native provider、非 native provider、schema 校验先于 provider 调用、能力上下文和 plan evidence。
- M59 capability catalog、M77 context engineering、M81 dynamic tools 相关回归 29 项通过；M30/M35/M66/M67/M79 相关回归 18 项通过。
- quick、stage 通过；离线全量 591 项通过、42 项按环境跳过；M69 多进程幂等测试单独连续复跑 5 次通过。
- Python 编译、`git diff --check` 和私有配置 ignore 检查通过；GIS profile 的 3 项在当前普通 Python 环境全部按依赖条件跳过，不能宣称真实 GIS 验收。
- Docker production acceptance 被宿主机 Docker Linux engine 阻塞，不能引用 M91 旧容器作为 M92 当前代码证据。

### 后续规划

1. Docker 环境恢复后，用当前版本重建并执行 production acceptance，确认 provider 证据在 HTTP/artifact/recovery 入口不丢失。
2. 从全局 Runtime 角度进入 M93：补 provider 健康、权限/数据依赖、超时/错误分类和跨入口观测契约。
3. 只有出现真实外部工具来源时才实现 `MCPToolProvider`；不为了使用 MCP 而改变 ToolRegistry、CapabilityCatalog、WorkflowTemplate 和 Result contract 的核心 seam。

## M93：Provider 治理与跨入口故障证据（已完成）

### 实现内容

- `NativeToolProvider` 增加健康检查；`ToolRegistry.provider_health()` 统一输出有界 provider 健康状态、检查项和 reason code，不执行业务工具，也不暴露异常原文。
- `ToolRegistry.governance_summary()` 和工具 schema 摘要支持权限、数据依赖、审批要求和 side effect 信息；当前 12 个内置工具已声明空间数据读取权限与数据依赖。
- 新增 `ToolProviderError` 及 `ToolError` 的 category/code/retryable 元数据。provider 错误经过 Registry 后，在 `StepRun`、SQLite、artifact、result envelope 和 observability 中保持稳定分类。
- Planner 上下文与 `plan_evidence` 记录 provider 健康和治理摘要；治理细节只展开选中工具 schema，避免重复占用上下文预算。
- ContextBuilder 默认预算从 12,000 调整为 16,000 字符，并将能力发现优先裁剪、能力目录次之、工作流模板最后裁剪，保证复杂请求仍保留能力目录和模板契约。

### 验收证据

- M93 专项 6 项、M92 provider 回归 5 项、M81 跨入口计划证据 9 项通过。
- 离线全量 597 项通过、42 项按环境跳过；quick、stage、Python 编译和 `git diff --check` 通过。
- 真实 GIS profile 在当前普通 Python 环境下按依赖条件跳过；Docker Linux engine 仍不可用，因此尚未用当前代码重建生产容器，不能复用 M91 容器证据。

### 下一阶段规划

1. 从全局 Runtime 盘点真实 provider adapter 的需求，先补 provider health 的 HTTP/runtime capability 暴露和生产 acceptance 检查。
2. 加强工具权限、数据依赖和 per-tool timeout 的实际执行门控，保证治理元数据不是只读展示。
3. 若仍没有真实外部工具来源，继续使用 fake provider/录制回放验证 MCP seam，不引入 MCP 运行时依赖。

## M94：Runtime Provider 治理执行闭环（已完成）

### 实现内容

- `/capabilities/runtime` 和 `runtime_capability_snapshot()` 现在输出 provider 身份、健康检查和治理摘要；能力快照不会执行业务工具，manifest 或 provider 异常只返回有界 reason code。
- `ToolRegistry` 新增 `governance_for()`、`timeout_seconds()` 和 `data_dependencies()`，Runtime 通过这一条 Registry seam 消费权限、审批、数据依赖和 per-tool timeout，不再复制 provider 规则。
- Runtime 在工具 dispatch 前执行权限与审批门控；可选严格依赖证据模式要求先获得数据健康报告；不可用数据返回稳定的 `policy/data_unavailable` 错误分类。
- 工具 Registry 对声明的 per-tool timeout 实际施加有界等待；run-level timeout 仍保持原有协作式步骤边界语义，避免工具级 timeout 改变取消/超时状态机。
- 12 个内置工具 schema 声明了有界 timeout；runtime factory 支持 `SPATIAL_AGENT_PERMISSIONS`、`SPATIAL_AGENT_APPROVED_TOOLS` 和 `SPATIAL_AGENT_REQUIRE_DEPENDENCY_EVIDENCE` 配置。
- 生产 acceptance 检查 provider health/governance schema、provider tool count 和 runtime capability 中的 provider 证据。

### 验收证据

- M94 专项 8 项、M92/M93 provider 回归 11 项、M37 cancellation、M60 runtime capability、M81 跨入口 contract 共 22 项通过。
- stage profile 通过；离线全量 605 项通过、42 项按环境跳过；之前由 timeout 接入暴露的 cancellation/step-boundary 回归已修复并通过。
- Python 编译、工具 schema JSON、PowerShell acceptance 静态契约和 `git diff --check` 通过。
- 当前普通 Python 环境仍未执行真实 GIS profile；Docker Linux engine 仍不可用，因此不能宣称当前 M94 版本的 Docker production acceptance。

### 下一阶段规划

1. 从项目全局评估 RequestFacts、能力目录、工作流模板、工具治理与结果契约的重复字段，建立统一的“计划前约束 -> 执行时门控 -> 结果证据”一致性矩阵。
2. 完善治理配置的 HTTP/生产入口暴露与安全默认值，并将门控、timeout、provider health 纳入 trace、artifact 和跨入口 normalization Harness。
3. 仅当出现真实远程 GIS、数据库或第三方工具来源时，按同一 Registry contract 实现 MCPToolProvider；在此前继续保持 MCP 为可替换 adapter，而不是核心依赖。

## M95：RequestFacts 与执行治理证据收敛（已完成）

### 已完成

- `SpatialRequest` 已明确为 `RequestFacts`，并输出版本化 `spatial-agent.request-facts.v1`；保留旧名称兼容已有 Planner/CapabilityRouter。
- Runtime 在规划前只抽取一次 RequestFacts，安全 projection 已贯通 preview、`AgentRunResult`、result envelope、SQLite recovery 和 artifact，避免各入口重新解析自然语言。
- `ToolRegistry.governance_for()` 作为治理读取唯一 seam；`spatial-agent.execution-policy.v1` 已进入 plan evidence，实际 StepRun 的权限、数据依赖、审批和 timeout 快照进入 result evidence、artifact、SQLite recovery；step observability 增加安全错误码。

### 当前证据

- M95 专项 3 项通过；M81 跨入口 normalization 已覆盖 direct/HTTP/CLI/artifact/recovery 的 RequestFacts、execution policy 和 StepRun governance 一致性。
- quick、stage 和离线全量通过：608 项通过、42 项按环境跳过；Python 编译、PowerShell acceptance 解析和 `git diff --check` 通过。
- 生产 acceptance 已加入 RequestFacts 与 execution policy schema/artifact 门禁；本轮未执行真实 GIS、Docker production acceptance 或 live LLM，不能将其跳过状态宣称为当前版本的真实环境证据。

### 全局重规划入口

M95 已把请求理解、工具治理、计划证据和执行结果连接为同一条可恢复链路。下一阶段必须从完整 Agent Runtime 的全局缺口出发，优先评估真实环境验收、失败后的可控修复、跨入口契约演进和工具来源扩展的先后关系；没有真实远程工具来源时不实现 MCP 运行时依赖。

## M96：Provider 合同验证与可替换适配器回放（已完成）

### 全局目标

在不引入 MCP 核心依赖的前提下，证明工具来源可以替换，但工具定义、权限、参数校验、timeout、错误和结果证据不能被 provider 绕过。MCP 继续只是未来真实远程工具来源的候选适配器。

### 实现内容

- `agent.tool_provider.validate_tool_definitions()` 在 `ToolRegistry` 接入 seam 校验 provider 工具目录：名称、目录 key、输入/输出 object schema、治理字段类型和正数有限 timeout。
- 新增 `spatial-agent.tool-provider-contract.v1`；provider health、runtime capability 和 Planner plan evidence 暴露有界的定义合同状态，不暴露 provider handler、连接信息或密钥。
- 生产 acceptance 增加 provider definition contract 的 schema 和 `valid` 状态门禁；动态工具和旧 `ToolRegistry(definitions, adapter)` 兼容路径保持不变。
- 新增非 Native provider 回放，验证外部 provider 仍经过同一 Registry dispatch、权限门控、治理快照和结构化计划证据。

### 验收证据

- M96 专项 4 项、M92/M93/M94/M95 相关回归 26 项通过；quick、stage、Python 编译、PowerShell acceptance 解析和 `git diff --check` 通过。
- 真实 GIS 核心 profile 在 `spatial-agent-gis` 环境通过 3 项；Docker Linux engine 当前仍不可用，本阶段未宣称 Docker production acceptance。
- 离线全量 612 项通过、42 项按环境跳过；真实 LLM 仍按可选 live 门控，不进入默认 CI。

### 全局复盘与下一阶段入口

- 产品：工具来源可替换性现在有可解释的合同证据，面试演示可以区分“协议接入”和“Runtime 治理”。
- 架构：ToolRegistry 继续是唯一执行 seam，provider 只提供定义和 provider-specific invocation。
- 数据/模型：provider 合同不改变数据健康和 TaskPlan 契约；真实模型仍使用同一 schema 和门控。
- 部署/体验/测试：runtime capability 与 acceptance 可发现 provider 合同失败；非 Native 回放覆盖 adapter 变更风险，前端无需新增硬编码面板。

下一阶段应优先处理真实部署证据与失败后的可控修复/重规划组合验收，再评估是否存在值得实现的真实外部工具来源；在没有该来源前不实现 MCP 运行时依赖。

## M97：运行级失败证据与恢复链路一致性（已完成）

### 实现内容

- 新增 `agent/failure_contract.py` 和 `spatial-agent.failure.v1`，统一输出无敏感原文的 `status/category/code/phase/retryable`。
- Runtime 在规划澄清、拒绝、取消、超时、工具/provider 失败和重规划耗尽时生成运行级 failure evidence；旧 `error` 字符串继续兼容。
- `result_contract.py`、HTTP/service formatting、artifact、SQLite recovery 和生产 acceptance 贯通相同 failure 证据；旧 payload 可安全补齐默认 code/phase。
- 生产 acceptance 增加预览指纹不匹配的失败样例，验证同步失败运行和 artifact 均能被机器读取。

### 当前证据

- M97 专项 4 项通过；离线全量 616 项通过、42 项按环境跳过；M96 provider 回放、M33 失败状态、M37 取消超时、M42 SQLite 和成本治理回归通过。
- quick、stage、GIS core、Python 编译、PowerShell 解析和 `git diff --check` 均通过；Docker Linux engine 仍不可用，真实生产 acceptance 不能在当前宿主环境宣称。

### 全局重规划入口

M97 已把失败的机器契约接入完整运行链路。下一阶段从全局七维矩阵决定优先做 Docker/真实模型验收，还是更深的计划修复与动态能力扩展；没有真实外部工具来源时不引入 MCP 运行时依赖。

## M98：失败证据的异步、Trace 与 Console 闭环（已完成）

### 实现内容

- observability run event 在原有错误分类之外增加有界 `error_code`、`failure_phase` 和 `failure_retryable`，仍不输出原始 provider 错误、URL 或密钥。
- 异步 worker 异常写入 SQLite 后，轮询/重启恢复结果继续返回同一 `spatial-agent.failure.v1`；增加异常 worker 回归验证。
- Console 消费 result envelope 或顶层 failure evidence，显示阶段、错误码和可重试性；用通用 badge 方式展示，不按具体 GIS 结果类型硬编码。

### 验收证据

- M98 专项 3 项、M80 observability 回归 6 项、Console 回归 2 项通过；M97 及全量回归保持通过。
- 离线全量 620 项通过、42 项按环境跳过；quick、stage、GIS core、Python 编译、PowerShell 解析和 `git diff --check` 均通过。Docker Linux engine 仍不可用，未宣称 Docker production acceptance。

### 全局复盘与下一阶段入口

M95–M98 已形成“请求事实 -> 计划/工具治理 -> 执行 -> 成功/失败证据 -> trace/前端/恢复”的核心 Runtime 闭环。下一阶段从七维矩阵优先安排当前代码的真实 Docker/LLM/GIS 入口验收；若宿主环境仍阻塞，则推进模型计划修复和开放式能力组合的脱敏回放，不引入没有真实工具来源支撑的 MCP 依赖。

## M99：自适应重规划结果契约收敛（已完成）

### 实现内容

- 新增 `spatial-agent.replanning.v1`，将顶层 `replan_events` 归一为受限的 `result.replanning` 证据，统一表达失败步骤、失败工具、失败分类、替代步骤和有限耗时信息。
- `result.lineage.replanning` 增加可导航的重规划摘要，HTTP、artifact recovery 和其他运行详情入口可以读取同一份计数与引用语义。
- 可读执行轨迹增加自适应重规划说明；Console 优先消费 `result.replanning.events`，旧顶层字段仅保留兼容回退。
- 新增契约、边界、trace 和 Console 消费测试，禁止原始异常文本穿过结果契约，并限制事件和替代步骤数量。

### 当前验收证据

- M99 专项与重规划、结果契约、跨入口计划证据、artifact viewer、Console 回归共 36 项通过；离线全量 624 项通过、42 项按环境跳过。
- quick、stage、smoke、Python 编译、PowerShell 解析、`git diff --check` 和真实 GIS core 31 项通过；真实模型 planner smoke 与显式绑定武汉分析就绪配置的 live GIS 总览通过。
- Docker Linux engine 当前仍无法连接 `dockerDesktopLinuxEngine` named pipe，尚未用当前版本重建并执行 production acceptance；不能引用旧容器作为 M99 证据。

### 下一步全局规划

1. 完成 quick、stage、离线全量和静态门禁，确认新增结果字段不破坏旧 artifact 与历史运行恢复。
2. Docker engine 恢复后，用当前版本执行 readiness、同步/异步、失败恢复、真实 GIS 和可选 live LLM acceptance。
3. 若宿主环境继续阻塞，则补充脱敏模型回放的开放式能力组合与失败重规划矩阵；没有真实外部工具来源时不引入 MCP 运行时依赖。

## M100：真实 GIS Live Profile 数据配置前置校验（已完成）

### 实现内容

- `scripts/test_profile.py` 的 `live-short` 本地 GIS 模式现在要求显式提供 `--dataset-config` 或 `SPATIAL_AGENT_DATASET_CONFIG`。
- 缺少正式数据配置时，profile 在启动模型/空间工具前直接失败并给出明确提示，不再静默回退到示例数据。
- 增加 profile 回归测试，并在中文问题日志中记录配置缺失与真实数据不可用的区分方法。

### 当前验收证据

- M100 profile 回归 8 项通过；离线全量 625 项通过、42 项按环境跳过；quick 通过。
- M99 的真实 GIS core、真实模型 planner smoke 和显式绑定武汉分析就绪配置的 live GIS 总览继续通过。
- Docker Linux engine 仍无法连接 `dockerDesktopLinuxEngine` named pipe，当前版本 production acceptance 仍待宿主环境恢复。

### 下一阶段全局规划

1. M101 先从全局七维矩阵复验 Docker/HTTP/SQLite/artifact/Console 的当前版本部署证据。
2. Docker 恢复前继续维护脱敏模型回放、开放式能力组合和失败重规划矩阵，不增加单区域规则。
3. MCP 仍保持未来真实远程工具来源的 adapter；没有实际外部工具来源时不引入运行时依赖。

## M101：生产验收契约跟随结果证据演进（已完成）

### 实现内容

- `scripts/production_acceptance.ps1` 新增 `Assert-ReplanningEvidence`，校验 `result.replanning` 的版本、事件边界、可用性/数量一致性和 `result.lineage.replanning` 计数。
- 生产同步运行和 artifact 均执行重规划证据门禁，避免结果契约新增字段后 Docker acceptance 仍然漏检。
- 静态 PowerShell 契约测试覆盖新增函数和调用标记；不改变默认离线测试和 MCP 架构决策。

### 当前验收证据

- full-stage、strict offline evaluation、smoke、PowerShell 解析和全量 625 项测试通过，42 项按环境跳过。
- M101 相关生产脚本/结果契约回归 10 项通过。
- Docker Linux engine 仍无法连接 `dockerDesktopLinuxEngine` named pipe，因此尚未执行当前版本的容器 production acceptance；不能引用旧容器结果。

### 下一阶段全局规划

1. M102 在 Docker engine 恢复后重建当前版本，执行 readiness、真实数据卷、同步/异步、artifact、失败和重规划证据 acceptance。
2. 同时复验生产 Console 的动态 workspace、views、trace 和地图证据，确认 HTTP/artifact/recovery 一致。
3. 如果宿主环境继续阻塞，补充脱敏重规划/开放式能力组合的跨入口回放；仍不引入没有真实外部工具来源支撑的 MCP。

## M102：重规划证据的历史 artifact 恢复兼容（已完成）

### 实现内容

- `result_contract.py` 增加重规划事件读取 seam：兼容当前顶层 `replan_events` 与旧/外部 artifact 的嵌套 `result.replanning.events`。
- 恢复后的 `result.replanning` 和 `result.lineage.replanning` 继续经过统一有界校验，不让历史 payload 绕过结果契约。
- 新增 artifact round-trip 与 legacy nested result 回归，并记录中文问题预防规则。

### 当前验收证据

- M102 相关回归 30 项通过；离线全量 627 项通过、42 项按环境跳过；GIS core 31 项通过。
- Docker Linux engine 仍无法连接 `dockerDesktopLinuxEngine` named pipe，尚未执行当前版本的容器 production acceptance；不能引用旧容器结果。

### 下一阶段全局规划

1. M103 在 Docker engine 恢复后重建当前版本，完成 readiness、真实数据卷、同步/异步、artifact、失败和重规划证据 acceptance。
2. 同时复验 Console 动态 workspace、views、trace 和地图证据，确认 HTTP/artifact/recovery 一致。
3. 若宿主环境继续阻塞，继续扩展脱敏模型回放和跨入口恢复矩阵；MCP 仍只在出现真实外部工具来源时实现 adapter。

## M103：当前版本跨入口与真实环境验收（已完成）

### 实现与验收内容

- 完成离线、GIS core、真实模型 + 本地武汉 GIS、HTTP 同步/异步、artifact 和运行时能力快照的当前版本验收。
- 离线全量 627 项通过、42 项按环境跳过；quick、stage、smoke、Python 编译和 `git diff --check` 通过。
- GIS core 抽样 3/3 通过；显式绑定 analysis-ready 数据配置的 `live-short` 2/2 通过，空间总览和约束建设筛选均返回预期结果类型，0 次重试，安全记录 token 总量 11,546。
- 本地 HTTP 已验证 result envelope、workspace/views、artifact 和异步轮询；统一以 `result.type` 和 `result.views` 为结果入口，顶层字段仅作为兼容证据。

### 环境限制

- Docker Linux engine 当前仍无法连接 `dockerDesktopLinuxEngine` named pipe，未执行当前版本的 FastAPI/Docker production acceptance，也未引用旧容器证据。
- 隔离 Chrome CDP headless 进程在本机退出码 13，动态 Console smoke 未计入通过；已有静态前端契约和浏览器回归在离线全量中通过。

### 下一阶段全局规划

1. Docker 恢复后重建当前镜像，完成 readiness、真实数据卷、同步/异步、SQLite 恢复、artifact、失败/重规划和 FastAPI acceptance。
2. 建立 dev HTTP、production FastAPI、CLI、artifact、recovery 的统一结果契约矩阵。
3. 从整体 Runtime 角度深化开放式请求理解、澄清、多工具编排、真实模型回放、数据 provenance 和动态 Console 证据。
4. 继续保持 ToolRegistry 为唯一执行 seam；只有出现真实远程工具来源时才实现 `MCPToolProvider` adapter。

## M104：CI 核心 Runtime 回归门禁（已完成）

### 实现内容

- GitHub Actions 从单独运行 `smoke_check.py` 扩展为服务 smoke、stage 契约 profile 和完整离线 unittest 回归。
- CI 明确不访问真实模型、私有配置、原始 GIS 数据或 Docker；真实 GIS、真实模型和 Docker 继续通过显式阶段 profile 执行。
- README 补充 CI 与阶段验收的边界，避免把离线 CI 误认为真实部署或真实数据证据。

### 当前验收证据

- 与 CI 等价的本地 smoke、stage 和离线全量 627 项通过、42 项按环境跳过。
- Python 编译、`git diff --check` 和已有 HTTP/Runtime/Console 静态契约继续通过。
- Docker Linux engine 和隔离 Chrome CDP 的宿主限制保持原样记录；本阶段没有伪造 FastAPI production 或动态浏览器通过证据。

### 下一阶段全局规划

1. Docker 恢复后重建当前镜像，完成 liveness/readiness、FastAPI、真实数据卷、SQLite 多 worker、artifact 和重启恢复矩阵。
2. 以 RequestFacts、CapabilityCatalog 和 WorkflowTemplate 为公共扩展点，做跨区域、跨任务的开放式请求回放与受控澄清。
3. 用脱敏回放和可选真实模型验证结构化计划、失败/重规划、token/延迟与工具治理证据。
4. 在可控浏览器 CDP 环境恢复后完成动态 workspace、views、trace、地图和会话清空验收；MCP 仍只在出现真实外部工具来源时实现 adapter。

## M105：开放式区域请求脱敏回放（已完成）

### 实现内容

- 在现有模型回放套件中增加 `open_region_query`，使用“查询江夏区行政区边界”验证区域是 RequestFacts 参数，而不是硬编码的洪山区分支。
- 回放计划仍经过 LLMPlanner 的 TaskPlan 校验、ToolRegistry dispatch、结果类型校验和中文答案组合。
- 增加 RequestFacts 跨区域一致性测试，确认请求事实、计划参数和 result envelope 使用同一行政区值。

### 当前验收证据

- 脱敏回放 3/3 通过；空间意图/澄清、跨入口计划证据和 RequestFacts 相关回归通过。
- full-stage、严格离线评测和离线全量 628 项通过、42 项按环境跳过；没有访问真实模型、私有配置或原始数据。
- Docker Linux engine 和隔离 Chrome CDP 的宿主限制仍保持未验证状态，不用离线回放替代生产部署或动态浏览器证据。

### 下一阶段全局规划

1. Docker 恢复后完成 FastAPI/readiness、SQLite 多 worker、artifact/recovery 和 dev/production 结果契约矩阵。
2. 增加一个非固定“总览/建设筛选”表达的开放式空间请求 live/replay 基线，让澄清继续由能力目录驱动。
3. 继续验证真实数据 provenance、对齐/覆盖和可选数据降级，区分数据证据与模型规划证据。
4. 恢复可控 CDP 后完成动态 workspace、views、地图、轨迹和会话清空验收；没有真实外部工具来源时不实现 MCP 运行时依赖。

## M106：非固定表达真实模型与本地 GIS 基线（已完成）

### 验收内容

- 通过 CLI/HTTP 共用的 `AgentService` 执行“查询江夏区道路与水体分布”，没有使用空间总览或建设筛选固定模板。
- 真实模型生成并完成 5 个工具步骤，结果类型为 `zonal_vector_summary_result`，workspace/views 均为 `vector`；真实数据摘要包含道路 10,051 个、水体 1,189 个，0 次重试。
- 确认 `AgentRuntime` 内部 `AgentRunResult` 与 Service/HTTP/CLI 外部 result envelope 的职责边界，并记录验收入口规则。

### 环境限制与下一阶段

- Docker Linux engine 仍无法连接 named pipe，Chrome CDP headless 仍以退出码 13 失败；FastAPI/Docker 和动态浏览器验收未宣称通过。
- M107 将从全局角度推进生产入口矩阵、更多开放式表达与未注册能力澄清、真实数据证据边界和动态 Console 验收；MCP 仍只在出现真实远程工具来源时实现 adapter。

## M107：修复 Windows CI stage 编码边界（已完成）

### 实现与验收

- 保留 stage 契约 profile；修复 `scripts/test_profile.py` 子进程的 UTF-8 环境和 stdout/stderr 显式解码，并在 CI job 级固定 Python UTF-8 环境。
- 增加中文子进程输出回归，避免 Windows locale 差异把 stage 通过误判为失败。
- 本地 smoke、stage 和离线全量 629 项通过、42 项按环境跳过；GitHub 最新失败 run 的 job steps 已确认失败点为 stage，原始日志受 GitHub 权限限制暂不可读。

### 下一阶段全局规划

1. 推送本修复并确认 GitHub Actions 的 stage 与完整离线回归均执行成功。
2. 从产品、架构、真实模型、数据、部署和前端整体检查 CI 是否覆盖正确边界，继续保持默认 CI 离线且可复现。
3. Docker engine 恢复后执行 FastAPI/readiness、SQLite/artifact/recovery 和真实数据卷联合验收；没有真实远程工具来源时不引入 MCP 运行时依赖。

## M108：跨入口结果契约 Harness（进行中）

### 实现内容

- 新增 `evaluation/contract_harness.py`，以小接口统一归一化和比较 CLI、HTTP、artifact、recovery 的稳定结果证据，并报告有界字段差异。
- 将复杂空间分析的跨入口验收从测试文件内的重复投影迁移到 Harness；运行 id、路径和时间等 transport-specific 字段不参与一致性比较。
- 增加 Harness 自身的差异报告、传输字段忽略和 JSON-safe 回归。

### 当前验收证据

- M108 Harness 与 M81 跨入口验收共 13 项通过；另以 50 次重复 targeted loop 验证异步 artifact/GeoJSON 轮询竞态修复。
- 修复异步服务在 Runtime 中间 `COMPLETED` 快照与 artifact/GeoJSON 最终引用之间的轮询竞态。
- Docker Linux engine 当前仍不可用；FastAPI/Docker production acceptance 和动态浏览器 smoke 仍未宣称通过。

### 后续顺序

1. 运行 full-stage、离线全量和 CI，确认 Harness 没有扩大默认测试边界。
2. 将 Harness 证据接入 release/production acceptance 的统一契约矩阵。
3. Docker 恢复后继续进行真实部署、数据卷和前端动态验收。

## M108 已完成

- Contract Harness 已统一 CLI、HTTP、artifact 和 recovery 的稳定结果投影与比较；运行 id、路径和时间等传输字段不参与一致性判断。
- 复杂空间分析跨入口回归已改用 Harness；异步 artifact/GeoJSON 轮询竞态已修复，50 次 targeted loop 全部通过。
- full-stage、严格离线评测、smoke、Python 编译和 `git diff --check` 通过；完整离线测试 634 项通过、42 项按环境跳过。
- Docker Linux engine 仍无法连接 `dockerDesktopLinuxEngine` named pipe，当前版本 FastAPI/Docker production acceptance 和动态浏览器 smoke 未宣称通过。

### M109 全局规划

1. 产品与模型：增加一条非“空间总览/建设筛选”固定模板的开放式多工具回放，验证能力目录、TaskPlan、DAG、结果类型和中文答案的通用闭环。
2. 架构与测试：回放必须继续经过 LLMPlanner 计划校验和 ToolRegistry，不新增区域专用分支；默认保持离线、脱敏和可重复。
3. 部署与数据：Docker 恢复后继续做当前版本 FastAPI/readiness、真实数据卷、artifact/recovery 和跨入口 acceptance；回放不能替代真实 GIS 证据。
4. 工具来源：没有真实远程工具来源时不引入 MCP 运行时依赖，继续以 ToolRegistry 作为唯一执行边界。

## M109 已完成

- 新增脱敏 `open_capability_query` 回放：“请概括江夏区的道路和水体分布”。该请求不是固定总览或建设筛选模板，包含道路/水体 schema 查询和分区矢量汇总两个并行分支。
- 回放验证 4 个注册工具步骤、依赖 DAG、`zonal_vector_summary_result`、中文答案以及无计划修复；没有增加区域专用规则或真实模型/私有数据依赖。
- M109 专项回放 4/4 通过；full-stage 通过；离线全量 634 项通过、42 项按环境跳过。

### 下一阶段全局规划

1. 生产与部署：Docker engine 恢复后重建当前版本，完成 FastAPI/readiness、SQLite 多 worker、artifact/recovery 和真实数据卷的跨入口验收。
2. 产品与模型：扩展开放式请求的结构化澄清、能力发现和受控失败修复，保持统一 RequestFacts/CapabilityCatalog/WorkflowTemplate 边界。
3. 数据与体验：验证真实数据 provenance、覆盖/对齐降级和 Console 动态 workspace/views/地图/轨迹；不以脱敏回放替代真实环境验收。

## M110：生产入口复用统一结果契约（已完成）

### 实现与验收

- 新增 `scripts/contract_harness_check.py`，将生产入口的多个公开结果交给 `evaluation/contract_harness.py` 统一归一化和比较。
- `scripts/production_acceptance.ps1` 现在比较同步运行结果与 artifact 的稳定契约，覆盖结果类型、答案、RequestFacts、规划证据、工具治理、步骤、trace、workspace、views 和 artifact 可用性；不重复维护第二套字段投影。
- 新增 M110 专项 4 项，包含等价结果、差异路径、真实 Service/artifact payload 和 PowerShell 调用 seam；PowerShell parser、full-stage 和离线回归均通过。
- 完整离线测试 638 项通过、42 项按环境跳过。Docker Linux engine 仍不可用，当前版本 production acceptance 仍未宣称真实容器通过。

### 下一阶段全局规划

1. 部署可靠性：Docker engine 恢复后重建当前版本，执行 readiness、核心/可选数据卷、同步/异步、SQLite 重启恢复和生产 acceptance，确认新 Harness 在真实 HTTP/artifact 边界工作。
2. 产品能力：扩展开放式请求的结构化澄清、能力发现和受控失败修复，不增加区域专用分支。
3. 数据与前端：补真实武汉数据 provenance/对齐降级和动态 Console workspace/views/地图/轨迹验收；真实模型继续作为显式 live 路径。

## M111：开放式能力澄清与预览契约（已完成）

### 实现与验收

- 结构化澄清现在输出版本化 `spatial-agent.clarification.v1`，并携带来自 CapabilityCatalog 的中文能力标签、匹配能力详情、候选能力详情和有界下一步动作。
- 修复能力分类信息在 `clarification_details` 中丢失的问题，避免 Console 只能显示能力 ID；没有新增区域或问题专用分支。
- 新增开放式未注册能力的 Service/HTTP 澄清一致性测试，以及“江夏区道路和水体分布”计划预览的 Service/HTTP 一致性测试。
- M111 专项 2 项、既有空间意图/HTTP 回归、full-stage 和完整离线回归通过；Docker/FastAPI 真实生产验收仍待宿主环境恢复。

### 下一阶段全局规划

1. 部署可靠性：Docker engine 恢复后执行当前版本 readiness、数据卷、同步/异步、SQLite 重启恢复、artifact 和 production acceptance。
2. 产品与模型：增加更多非固定表达的脱敏/可选 live 回放，并验证澄清到计划的多轮闭环和失败修复。
3. 数据与前端：完成真实武汉数据 provenance/对齐降级和动态 Console workspace/views/地图/轨迹的真实入口验收。

## M112：Domain Pack 与数据集解耦（已完成）

### 全局判断

- Runtime、Planner、TaskPlan、ToolRegistry、结果契约、观测、artifact 和 HTTP 入口已经是通用 Agent Runtime 能力。
- 但 GIS 数据集名称、GIS 能力目录、GIS discovery 和 GIS workflow context 曾集中在 `agent` 公共模块中，导致新增领域只能复制或修改核心 Runtime。
- 本阶段把 GIS 视为默认 Domain Pack：洪山区、DEM、土地利用、道路和水体保留为真实回归数据，不再作为 Runtime 的架构前提。

### 实现内容

- 新增 `DomainPack` seam，Runtime 和 `build_runtime()` 支持注入领域包；默认行为仍懒加载 GIS 包，保持现有 CLI/HTTP/Console 兼容。
- 新增 `domains/gis`，集中持有 GIS 数据集工具映射、数据分组、能力定义、GIS discovery 和 workflow context。
- 公共 capability catalog 构造器改为接收领域能力定义、数据分组、工具映射、workflow templates 和 domain id；旧 GIS 导入名保留为兼容别名。
- workflow context 也改由 Domain Pack 提供，非 GIS Domain Pack 不会意外获得 GIS 模板。
- 新增非 GIS 文本领域 fake pack 和非 GIS catalog builder 回归，验证 Runtime、能力发现和 planner context 不依赖 GIS 数据集。

### 当前验收证据

- M112 专项 3 项通过；`full-stage`、编译和 `git diff --check` 通过。
- 三 worker SQLite 幂等用例单独连续 20 次通过；完整离线套件在完整资源压力下偶发该既有用例失败（643 项执行、42 项跳过、1 项失败），不涉及本阶段文件，沿用开发问题记录中的并发竞态说明。
- 本阶段未改变真实 GIS 数据文件、模型 provider 或 Docker 依赖；Docker Linux engine 仍需恢复后验收。

### 下一阶段全局规划

1. 先从产品、架构、数据、模型、部署、前端和测试七个维度建立跨领域能力验收矩阵，避免继续围绕单个 GIS 数据集增加功能。
2. 将能力目录、workflow、结果类型和数据 provenance 的领域扩展点继续收敛为可验证契约，并补一个真正独立于 GIS 的最小 adapter/replay。
3. Docker/真实环境可用时，复验 GIS Domain Pack 的 HTTP、SQLite、artifact、地图和真实模型闭环；离线 CI 仍不依赖原始数据或 live provider。
4. 只有出现真实远程工具来源时才实现 MCP adapter；MCP 仍不能替代 ToolRegistry、schema 校验和执行治理。

## M113 已完成：非 GIS Domain Pack 闭环

- 新增独立于 GIS 的 `domains/text` Domain Pack，包含自有 RequestFacts 提取、能力目录、discovery、Planner、ToolProvider、AnswerComposer 和 Runtime factory。
- 文本摘要请求已通过同一条 `RequestFacts -> capability discovery -> TaskPlan -> ToolRegistry -> Runtime -> Service -> result envelope -> artifact` 链路执行；没有引入 GIS 数据集、空间模板或区域专用规则。
- `AgentService` 支持注入自定义 `runtime_factory`，使 Service/HTTP 边界可以复用非 GIS Runtime；planning evidence 现在记录通用 `domain_id`。
- `text_summary_result` 使用通用 workspace 的 `generic` 面板，Contract Harness 能比较 Service payload 与 artifact，证明结果契约不只服务空间结果。
- M113 专项 3 项、M112 回归 3 项、`full-stage`、离线全量 646 项（42 项按环境跳过）、Python 编译和 `git diff --check` 通过。

### M114 全局规划

1. 对 Runtime、Service、HTTP capability snapshot、result views、provenance 和 failure/replanning 做一次领域泄漏审计，并将仍带 GIS 假设的部分下沉到 Domain Pack。
2. 将数据集、实体、能力和结果类型的扩展点收敛为可校验的 Domain Pack 契约；用至少两个 GIS 数据源/区域和一个非 GIS Domain Pack 做契约测试。
3. 恢复 Docker/真实环境后，重新验收 GIS Domain Pack 的 HTTP、SQLite、artifact/recovery、真实武汉数据和可选真实模型路径；CI 仍保持离线。
4. 前端继续消费动态 result envelope/workspace/views，不为文本或 GIS 分别复制固定结果面板；没有真实远程工具来源时不引入 MCP 运行时依赖。

## M114 已完成：Domain Pack 默认行为下沉

- `AgentRuntime` 不再在未显式传入时直接创建 GIS `AnswerComposer` 或固定使用 `spatial_data:read`；默认答案组合器和权限集合现在由选中的 Domain Pack 提供，并保留旧 GIS fallback。
- GIS Domain Pack 声明空间答案组合器与空间读取权限；Text Domain Pack 声明文本答案组合器与 `text_data:read`，文本 Runtime 因此不再需要额外注入领域实现。
- 公共 `result_contract.py` 移除 `text_summary_result` 的专用标题映射，文本标题来自 Domain Planner 的 output metadata，未知结果继续使用兼容默认值。
- M114 定向 17 项、`full-stage`、离线全量 646 项（42 项按环境跳过）、编译和 `git diff --check` 通过。
- 审计仍确认 `result_contract.py` 的 GIS view/panel 注册、生产 capability endpoint 和部分 provenance/数据健康逻辑属于下一阶段的残留领域边界；本阶段没有声称全部领域泄漏已消除。

### M115 全局规划

1. 把结果类型标题、workspace panel 注册和 view builder 的扩展点从公共硬编码进一步收敛为 Domain Pack/结果注册契约，同时保持旧 GIS 结果兼容。
2. 让 HTTP/runtime capability snapshot 读取实际 Runtime/Domain Pack，而不是直接导入 GIS catalog；增加 Text/GIS 双入口契约测试。
3. 审计 provenance、failure/replanning、数据健康和前端动态渲染的领域假设，明确哪些是通用证据、哪些必须由 GIS pack 提供。
4. Docker/真实数据可用后做 GIS 真实入口验收；默认 CI 继续不访问原始数据、私有模型或 Docker。

## M115 已完成：Domain Pack 结果注册契约

- 新增通用 `ResultContractRegistry`/`ResultTypeSpec`，结果类型标题与 workspace panel 注册由 Domain Pack 提供；公共 `result_contract.py` 不再维护 GIS/文本类型字典。
- GIS 结果 metadata 下沉到 `domains/gis/result_registry.py`，Text Domain Pack 注册 `text_summary_result` 与 generic workspace；旧的直接调用 `build_result_contract(payload)` 仍懒加载 GIS registry 兼容。
- Runtime 持有所选 registry，Service 在同步、重试、运行详情和 artifact 结果构建时传递它；没有该新方法的旧自定义 Runtime 使用安全 fallback，不破坏可替换 Runtime 契约。
- M115 相关定向回归 16 项、`full-stage`、离线全量 646 项（42 项按环境跳过）、编译和 `git diff --check` 通过。

### M116 全局规划

1. 将 `/capabilities` 与 `/capabilities/runtime` 的领域目录来源改为实际 Runtime/Domain Pack，保留 GIS 数据健康作为 GIS pack 的可选 runtime evidence。
2. 用 Text Domain Pack 与 GIS Domain Pack 做 HTTP/Service capability snapshot 契约测试，避免生产入口直接导入 GIS catalog。
3. 继续审计 provenance、failure/replanning 和前端动态结果消费；只有跨入口证据稳定后再做 Docker/真实 GIS 验收。

## M116 已完成：HTTP 能力目录复用 Runtime

- `AgentRuntime.capability_catalog()` 和 `AgentService.capabilities()` 已成为能力目录读取 seam，实际返回选中 Domain Pack 的 catalog 与 backend environment。
- 开发 HTTP `/capabilities` 和生产 FastAPI `/capabilities` 不再直接导入 GIS catalog；支持通过 `planner`/`backend` 选择 Runtime，保留统一 JSON 目录契约。
- 新增 Text Domain Pack 的 Service/HTTP 能力目录回归，确认 HTTP 入口只返回文本能力，不泄漏 GIS 能力；`/capabilities/runtime` 的 GIS 数据健康探针仍保持独立兼容路径。
- M116 定向 18 项、`full-stage`、离线全量回归、编译和 `git diff --check` 通过。

### M117 全局规划

1. 为 `/capabilities/runtime` 增加 Domain Pack 可选 runtime evidence seam：通用部分包含 provider/tool governance，GIS 才附加数据健康、覆盖和 provenance。
2. 补 production FastAPI 与开发 HTTP 的 Text/GIS capability snapshot 契约测试；依赖缺失时保持显式跳过，不把旧宿主环境当作生产证据。
3. 继续审计 provenance、failure/replanning 和前端动态结果消费，随后再安排 Docker/真实 GIS/真实模型验收。

## M117 已完成：通用 runtime capability snapshot seam

- `AgentRuntime.runtime_capabilities()` 和 `AgentService.runtime_capabilities()` 已统一输出 Domain、backend、provider health、tool governance 和有界 runtime metadata。
- Domain Pack 可通过可选 `runtime_evidence(max_files=...)` 提供领域数据/运行证据；Text Domain Pack 已提供 `not_applicable` 数据状态，缺少该 seam 时使用通用 `not_evaluated`，异常只返回有界错误码。
- M117 定向 25 项、`full-stage`、离线全量回归、编译和 `git diff --check` 通过；现有 GIS `runtime_capability_snapshot()` 保持兼容，尚未宣称 HTTP runtime endpoint 已完成迁移。

### M118 全局规划

1. 将 `/capabilities/runtime` 接入新的 Service/Runtime snapshot，同时保留 GIS 数据健康、manifest、alignment 和 provenance 的 Domain evidence。
2. 补开发 HTTP 与生产 FastAPI 的 runtime snapshot 双领域契约测试，验证旧 GIS 客户端字段和新通用字段同时稳定。
3. 继续审计 provenance、failure/replanning 与前端 evidence 消费，再进行 Docker/真实 GIS/真实模型验收。

## M118 已完成：HTTP runtime snapshot 接入 Domain Pack

- 开发 HTTP `/capabilities/runtime` 在正常 Service 入口下改为读取 `AgentService.runtime_capabilities()`；生产 FastAPI 通过同名兼容包装进入 Service/Runtime，旧的可 patch 函数名和字段保持兼容。
- GIS Domain Pack 将既有数据健康、manifest、analysis-ready、coverage/provenance 和 capability runtime evidence 适配到通用 snapshot；Text Domain Pack 的 HTTP snapshot 返回 `not_applicable` 数据证据。
- `service=None` 的隔离测试仍使用旧 snapshot provider，避免测试 harness 误把缺少 Service 当成业务领域；正常请求不再直接绕过 Runtime。
- M118 定向 23 项、`full-stage`、离线全量回归、编译和 `git diff --check` 通过；当前生产 FastAPI 依赖在宿主未安装，相关用例按环境跳过。

### M119 全局规划

1. 将 release evidence、provenance 和 failure/replanning 中剩余 GIS 语义分为通用证据与 Domain evidence，避免 HTTP snapshot 之外继续存在旁路。
2. 在 FastAPI 依赖和 Docker 可用时执行生产 runtime snapshot、readiness、SQLite、artifact/recovery 的真实验收；不以开发 HTTP 代替生产证据。
3. 审计前端是否完全消费 result/workspace/views/runtime evidence，补 Text/GIS 双领域动态展示契约后，再进入真实模型与真实数据组合验收。

## M119 已完成：通用证据边界收敛

- `ResultTypeSpec.requires_geometry` 取代公共 `result_contract.py` 中的 GIS result type 集合；几何未知降级提示现在由 Domain Pack 的结果 metadata 决定。
- provenance 增加版本、`domain_id` 和 Domain-neutral 的有界计数摘要；不复制任意文本或原始工具 payload，保留原有 GIS 证据兼容。
- failure/replanning 已确认本身是通用 schema，本阶段没有为 GIS 增加额外分支；Text 结果验证不会错误生成 `geometry_unknown`。
- M119 相关定向回归、`full-stage`、离线全量 650 项（42 项按环境跳过）、编译和 `git diff --check` 通过。
- 当前仍有 GIS view builder/tool 判断和 provenance 中的少量兼容字段；下一阶段继续下沉，不宣称公共结果模块已经完全无 GIS 语义。

### M120 全局规划

1. 将 result views 的 GIS tool/result type 判断继续收敛为 Domain Pack 的 view builder registry，Text 领域保持 generic view，不增加前端类型分支。
2. 将 provenance 中 `admin_name/crs` 等领域字段变为可选 Domain evidence，同时保留旧 artifact 读取兼容。
3. 补前端动态 workspace/views/runtime evidence 的 Text/GIS 契约测试；Docker/FastAPI/真实模型和真实数据继续作为显式验收路径。



## M127 已完成：Evidence Provider 与 Action 可恢复闭环

- 新增 `spatial-agent.domain-evidence.v1` 统一 evidence envelope；GIS/Text provider 与旧 Domain Pack 均可通过同一 runtime/release seam 输出，旧 runtime/release 方法仍保留兼容。
- Action 增加规范化输入指纹、显式幂等键、成功复用、输入冲突和失败 artifact 重放；Action metrics 与 bounded observability event 进入 Service metrics/事件流。
- 开发 HTTP 与生产 FastAPI 增加 Action 历史列表和 Action artifact 读取入口，并保持普通 Run 列表、指标和 artifact 路径隔离。
- Console 的比较结果、Action 详情和历史列表统一展示 Action ID、状态、trace、幂等复用状态、artifact/recovery 链接；不增加 GIS 专用渲染分支。
- 脱敏模型回放 evaluator 支持 Text 与 GIS 两种 Domain Pack；新增开放式文本请求和复杂 GIS 总览 fixture，共享工具覆盖、计划质量、结果类型、中文答案及 token/延迟脱敏指标。
- M127 专项 7 项、离线全量 674 项通过（42 项跳过）；smoke、stage profile、`git diff --check` 和远端 CI 稳定门禁通过。
- FastAPI/Docker/真实 GIS 数据/可选真实模型仍属于环境条件验收，不能用离线结果代替生产矩阵证据。

### M128 全局规划

1. 从完整 Agent 闭环审计 Run 与 Action 两套执行记录，抽取通用 Execution Record/事件投影 seam，统一状态、trace、metrics、artifact/recovery 和幂等证据。
2. 将 CLI、开发 HTTP、生产 FastAPI、同步/异步、artifact 和 Console 接入同一 Contract Harness，用 Text 与复杂 GIS 回放验证跨领域一致性。
3. 将数据健康/降级证据与执行结果建立通用关联；真实数据只作为 GIS Domain evidence，真实模型只作为可选 live 基线。
4. 阶段末执行专项+全量，并在 Docker/FastAPI 可用时完成部署矩阵；环境不可用时保留明确阻塞证据。

## M128 当前实现：统一 Execution Record 与跨入口投影

- 新增 `agent/execution_contract.py`，提供 `spatial-agent.execution-record.v1` 有界投影；Run 与 Domain Action 共用同一字段集合，身份、耗时、请求文本和 payload 彼此隔离。
- `AgentRunResult.to_dict()`、Service、ArtifactStore 和 result envelope 均暴露执行记录；Action artifact、Run artifact、历史列表和恢复入口均保留该记录。
- Contract Harness 新增 transport-neutral execution projection，开发 HTTP、同步/异步、SQLite 恢复、Text Domain 和 Console 回归覆盖；没有执行身份的旧 fixture 不被强制升级。
- 当前验证：M128 专项 7 项、受影响契约 13 项、离线全量 681 项通过（42 项跳过）；smoke、stage profile、compileall 和 `git diff --check` 通过，文档已收尾，待推送阶段版本。

## M121 已完成：provenance Domain projection

- `ResultContractRegistry` 增加 provenance projector；公共 provenance 只自动保留通用运行血缘和 bounded numeric counters，GIS 的 `admin_name/crs` 等兼容字段由 GIS registry 投影。
- Text Domain Pack 不会从文本工具结果中继承 GIS provenance 字段，同时保留 `domain_id`、`word_count` 等安全通用 evidence；旧 GIS artifact/recovery 回归保持通过。
- M121 定向回归、`full-stage`、离线全量 651 项（42 项按环境跳过）、编译和 `git diff --check` 通过。
- 公共 `result_contract.py` 仍包含 GIS view builder 的实现本体，但它已只能由 GIS registry 调度；下一阶段处理物理迁移。

### M122 全局规划

1. 将 GIS view builder 实现物理移动到 `domains/gis`，公共结果模块只保留通用 envelope、registry dispatch 和 geometry primitives。
2. 将前端静态 GIS 结果面板逐步收敛为 result views/workspace 驱动，并补 Text generic views smoke。
3. Docker/FastAPI/真实数据/真实模型可用后执行生产矩阵；所有数据集继续作为可替换 Domain evidence，而非 Runtime 前置条件。

## M122 已完成：GIS 视图实现下沉与跨领域前端 smoke

- 新增 `domains/gis/views.py`，迁移 raster、overview、health、composite、buildability、vector 和 map view builder；`domains/gis/result_registry.py` 直接注册 GIS 实现。
- 公共 `result_contract.py` 不再实现 GIS view builder，只保留通用结果 envelope、workspace/geometry evidence、lineage、对比视图和通用 view primitive。
- 新增 `tests/test_m122_domain_views.py`：验证 GIS registry 的物理归属、Text 结果只使用 generic workspace，以及 Console 不为 Text Domain 增加领域专用分支。
- 全量离线测试 653 项通过（42 项按环境跳过），quick、full-stage、compileall 和 `git diff --check` 通过；真实 GIS、FastAPI、Docker 和 live LLM 仍未在当前宿主重新验收。

### M123 全局规划

1. 从全局产品能力审计前端静态 GIS controls、Service 专用 comparison 入口和默认 GIS 兼容路径，区分必须保留的 GIS Domain Pack 能力与应下沉的 Domain adapter。
2. 为 Domain Pack 增加可声明的 workspace view renderer metadata，使前端能够按 view kind/metadata 扩展，而不是持续增加 GIS 面板选择器。
3. 建立第二个非 GIS 领域的真实跨入口回放（Service、HTTP、artifact、Console generic），并将结果一致性纳入 Contract Harness；默认 CI 继续不依赖网络和私有数据。
4. Docker/FastAPI/真实 GIS 数据/真实模型可用后，执行生产验收矩阵；任何数据集问题都作为 Domain evidence 处理，不能修改公共 Runtime 规则。

## M123 已完成：领域视图元数据与通用 Console 渲染

- `agent/result_registry.py` 新增有界 `ViewSpec`，Domain Pack 可以声明 view id、renderer、标题和 schema；workspace 与 capability context 会携带相同的结构化元数据。
- GIS registry 为 raster、overview、health、composite、buildability、vector、map 和 comparison 声明 renderer；旧 GIS view 算法仍只在 `domains/gis` 内执行。
- Console 增加 generic metrics/table/chart renderer，对未注册的领域面板不再要求新增 GIS 页面分支；Text 与自定义 registry 回放均验证通过。
- 删除前端 `needsRaster`、固定 DEM/土地利用关键词和本地 GIS 预判，数据依赖与降级改由 Service/Runtime 返回；Node 内联脚本语法检查通过。
- 全量离线测试 654 项通过（42 项按环境跳过），quick/full-stage、compileall 和 `git diff --check` 通过；Docker、FastAPI、真实 GIS 数据和 live LLM 仍待环境验收。

### M124 全局规划

1. 将 GIS 专用比较入口和 Console comparison controls 收敛为 Domain-owned capability/action metadata，公共 HTTP/前端只处理通用 action contract。
2. 增加第二个完整非 GIS Domain Pack replay，验证 Service、HTTP、artifact、recovery、generic Console 和 Contract Harness 的一致性，而不是只验证 registry 级别。
3. 从部署和数据质量维度复验 domain capability snapshot、降级、artifact 和 SQLite 恢复；在 Docker/FastAPI/真实数据可用时执行生产矩阵。
4. 继续保持 Planner/Runtime/ToolRegistry 的稳定 seam，禁止为具体区域、数据集或页面显示新增公共规则。

## M124 已完成：Domain-owned Action seam 与非 GIS 完整回放

- 新增通用 `DomainActionSpec`、Action catalog 和显式 Domain Pack dispatch；GIS 的三个建设筛选对比动作由 `domains/gis/actions.py` 声明，未注册动作不能执行，Text Domain Pack 不泄漏 GIS action。
- 开发 HTTP 与生产 FastAPI 均提供 `/actions` 和 `/actions/{action_id}`；原比较路由保留为兼容 wrapper，不再是前端主路径。
- Console 先读取当前 Domain Pack 的 action catalog，再统一调用 action dispatch；比较结果继续通过既有 `ViewSpec`/chart renderer 展示，没有新增 GIS 专用公共 Runtime 分支。
- Text Domain Pack 已完成 Service、HTTP、artifact、recovery 和 Contract Harness replay，验证 generic workspace、domain_id、结果类型和跨入口一致性。
- M124 专项与 Console 回归 24 项、全量离线测试 659 项通过（42 项按环境跳过），Node 内联脚本语法、`git diff --check` 通过。

### M125 全局规划

1. 从公共 Runtime 领域泄漏审计开始，优先将 `agent/answer_composer.py`、GIS 数据健康/analysis-ready 规则和兼容 catalog 默认值收敛为 Domain Pack provider；保留显式 GIS bootstrap 与旧 artifact 读取兼容。
2. 为 Domain action 增加通用输入 schema 校验、错误 envelope、观测和 artifact/recovery 证据，使 action 与 tool 一样具有清晰的执行契约，但不把 action 反射成任意 Service 方法。
3. 让前端能力、action、workspace view 和结果 evidence 统一来自 Runtime snapshot；GIS 示例与控件作为可选 Domain 配置，验证 Text/第二非 GIS pack 不出现 GIS 语义。
4. 在数据质量、真实模型、部署和用户体验维度做跨入口回归矩阵；真实武汉数据只作为 GIS Domain evidence，默认 CI 仍离线可复现。

## M125.1 已完成：领域数据预检与 Action schema seam

- `agent/runtime.py` 不再直接列出 GIS 数据集、DEM/土地利用网格关系或 GIS 像元工具；通用 Runtime 通过 `DomainPack.preflight_tool()` 委托领域数据与证据门控。
- GIS 预检实现下沉到 `domains/gis/preflight.py`，保留原有数据健康、网格对齐、不可用数据和严格依赖证据行为；Text/自定义 Domain Pack 没有该方法时安全保持通用路径。
- 新增 bounded `validate_action_payload()`，Domain action 在显式 dispatch 前校验 required、unknown fields、嵌套数组和基础类型/范围；仍禁止任意 Service 反射调用。
- M125.1 新增领域预检负向测试和 Action schema 回归；全量离线测试 662 项通过（42 项按环境跳过），compileall、quick/full-stage 和 `git diff --check` 通过。

### M125.2 全局规划

1. 继续将 GIS AnswerComposer、数据健康/analysis-ready 兼容 provider 和 release evidence 物理收敛到 GIS Domain Pack；保留有界旧导入兼容。
2. 为 Action 增加结构化错误、trace/observability、artifact/recovery 一致性证据，并用第二个非 GIS Domain Pack 做真实 dispatch replay。
3. 审计 Console 与生产入口是否只消费 Runtime snapshot、Action catalog、ViewSpec 和 result evidence，随后执行 Docker/FastAPI/真实数据/可选模型矩阵。

## M125.2 已完成：Composer 归属与 Action 执行证据

- GIS `AnswerComposer` 已物理迁移到 `domains/gis/composer.py`；`agent/answer_composer.py` 仅保留旧导入 shim，Runtime 不再直接依赖 GIS composer 实现。
- Action dispatch 增加 `domain_id` 和 `spatial-agent.action-execution.v1` 执行证据，记录已校验输入、完成状态和有界耗时；未知/不可执行/非法输入返回结构化 `action_id` 与 `action_error_code`。
- M125.1 的 Domain preflight、Action schema 校验与本阶段 Composer/Action 证据合并为一个可复用的纵向契约；旧 GIS、Text Domain、HTTP、artifact 兼容路径保持通过。
- 阶段末验证：Composer/Action/HTTP 相关回归 25 项通过；此前阶段全量 663 项通过（42 项按环境跳过）；compileall、quick/full-stage、Node 页面语法和 `git diff --check` 通过。

### M126 全局规划

1. 将 GIS data-quality、analysis-ready 和 release evidence 的实现从 `agent/` 进一步收敛为 Domain-owned provider，同时保留 HTTP/旧 artifact 的兼容 seam。
2. 让 Action execution evidence 进入统一 trace/result/artifact 观测模型，并用第二个非 GIS Domain Pack 做有成功、校验失败和恢复读取的跨入口回放。
3. 全局审计 Console、生产 FastAPI、Docker、真实 GIS 数据与可选真实模型，确认数据只是 Domain evidence；阶段末再做一次完整矩阵验收。

## M126 已完成：领域证据与 Action 执行闭环

- 新增 `DomainPack.release_evidence()` seam；Runtime、Service、开发 HTTP 和生产 FastAPI 的正常路径读取当前 Domain Pack 的 release evidence。GIS 通过 `domains/gis/evidence.py` 适配既有 data-quality、analysis-ready、manifest 和 release provider，旧 provider 入口继续兼容。
- Action execution 进入统一结果模型：成功与 schema 校验失败都记录 `spatial-agent.action-execution.v1`、有界 trace、`result` envelope 和独立 action artifact；新增 `/action-executions/{execution_id}` 只读恢复入口，artifact 不会混入普通 run 列表或运行指标。
- Text Domain Pack 新增 `text.summarize`，覆盖非 GIS action 的 catalog、Service、HTTP、成功、输入失败、artifact recovery 和 runtime/release evidence；验证公共 Runtime 不因 Text pack 继承 GIS 语义。
- 中文问题记录已补充领域证据入口绕过、Action 与普通 Run 结果收敛、非 GIS fixture 历史断言失效等经验；恢复文档同步记录新的阶段节奏和 M126 状态。
- 阶段收尾仅运行一次代表性专项与一次全量离线回归：专项 13 项通过；全量 667 项通过、42 项按环境跳过；compileall、`git diff --check`、私有配置 ignore 检查通过。

### M127 全局规划

1. 继续把领域证据从“兼容 Adapter”深化为可替换 Evidence Provider 接口，统一 runtime snapshot、release report、provenance projection 和 failure/degradation 的版本化 schema；同时保留旧 artifact/脚本读取。
2. 将 Action 与普通 Run 的观测进一步接入统一 metrics、事件流和 Console 动态 workspace，补充跨领域 action 的失败重试/幂等边界，但不复制 GIS 专用页面或 Service 方法。
3. 形成真实部署验收切片：FastAPI/readiness、SQLite 多进程、action artifact/recovery、能力快照、真实 GIS 数据卷和可选真实模型使用同一 contract harness；Docker 不可用时保留明确阻塞证据。
4. 以一个开放式非固定表达和一个 GIS 复杂表达做端到端回放，比较 Rule Planner、脱敏 LLM Planner 与真实模型可选路径的计划、工具、证据、token/延迟和降级差异；阶段末统一回归后再全局重规划。

## M120 已完成：Domain-owned view builder seam

- `ResultContractRegistry` 新增 view builder 回调；`build_result_contract()` 只调用选定 registry 的 builder，不再无条件执行 GIS view model。
- GIS registry 通过惰性 builder 保留现有 raster/vector/composite/map view 算法；Text registry 不注册 GIS builder，结果 views 稳定返回 generic empty panels。
- Text/GIS 结果、artifact、lineage、geometry degradation 与既有 view contract 回归通过；没有新增前端按领域分支。
- M120 定向 25 项、`full-stage`、离线全量 650 项（42 项按环境跳过）、编译和 `git diff --check` 通过。
- 当前公共模块仍保留 GIS view builder 实现代码，但调用权限已由 registry 控制；下一阶段可在不改变结果契约的前提下继续移动实现位置。

### M121 全局规划

1. 将 GIS view builder 实现从公共 `result_contract.py` 移至 `domains/gis`，公共模块只保留通用 view envelope 与 registry dispatch。
2. 将 provenance 中 `admin_name/crs` 等兼容字段变成 Domain evidence projection，并验证旧 artifact/recovery 不丢字段。
3. 补前端动态 workspace/views/runtime evidence 的 Text/GIS 契约测试；Docker/FastAPI/真实模型和真实数据继续作为显式验收路径。

## M129 已完成：Domain-owned Planner Guidance

- `DomainPack` 新增 `planner_guidance()` seam，并由 `agent/planner_guidance.py` 提供版本化 `spatial-agent.planner-guidance.v1` 的有界规范化与渲染。
- 公共 `LLMPlanner` 现在只负责 TaskPlan JSON 契约、注册工具边界、工作流/依赖引用和通用安全约束；GIS 规划规则已迁移到 `domains/gis/planner_guidance.py`。
- Text Domain Pack 提供独立摘要 guidance；脱敏模型回放、运行时工厂和跨领域测试均验证同一 LLM Planner 可切换 guidance，Text prompt 不泄漏 GIS 语义。
- 新增 M129 跨领域负向契约；旧 GIS Planner prompt 测试改为显式注入 GIS guidance，避免把 GIS 默认值当作公共接口。
- 阶段收尾验证已完成：685 项离线测试通过、42 项按环境跳过；M129 专项/受影响契约、smoke、stage、full-stage、compileall 和 `git diff --check` 均通过。真实模型、真实 GIS 和 Docker 仍按可选环境验收，阶段版本随后推送。

## M129.1 已完成：精简提交测试门禁

- 新增 `ci` profile，提交/PR 只运行 3 个 quick 核心契约、服务 smoke 和 1 个复杂空间编排代表场景；完整 `stage` 仍保留 3 个离线边界场景，按阶段收口显式运行。
- `evaluate_global.py` 增加有界 `--case-ids` 选择，不复制验收 JSON，也不改变 Runtime 执行契约。
- GitHub Actions push/PR 改为运行 `ci` profile；完整离线回归继续只在 `workflow_dispatch` 中运行，历史专项测试不删除。
- 本阶段验证重点为 profile dry-run、profile 契约和 `ci`/`stage` 入口；下一阶段恢复 M130 的 Capability Routing/Catalog 全局解耦工作。

### M130 全局规划

1. 继续审计 `capability_routing.py`、`capability_catalog.py` 和遗留 GIS RequestFacts 兼容路径，建立 Domain-owned Request Understanding/Capability Discovery guidance，避免 Planner 解耦后路由层仍绑死 GIS。
2. 让 planner guidance、RequestFacts、能力目录和 workflow template 在同一上下文/证据投影中可追踪，补充跨 CLI、HTTP、artifact 和回放的计划来源证据。
3. 在不增加 GIS 专用规则的前提下，增加一个更接近开放式任务的非 GIS 脱敏回放，并验证澄清、拒绝、结果类型和 ToolRegistry 边界。
4. 阶段末复验真实模型可选基线、Docker/FastAPI 条件路径和稳定 CI；重型全量回归保持阶段验收，不重新成为 push 门禁。

## M130 已完成：Domain-owned Request Understanding 与 Capability Discovery

- 新增 `spatial-agent.request-understanding-guidance.v1` projection；GIS/Text Domain Pack 分别声明事实字段、任务/约束/证据提示和澄清策略，Runtime 将其纳入 Context 与 `plan_evidence`。
- Rule Planner 优先消费 Runtime 已抽取的 `RequestFacts`，避免正常 Runtime 路径重复解析；直连 Planner 仍保留兼容 fallback。
- GIS RequestFacts 解析、路由信号与路由表已移入 `domains/gis`；`agent/capability_discovery.py` 只保留领域无关的 route/value objects，旧 `agent/capability_routing.py` 和默认 catalog 入口保留惰性兼容 facade。
- Contract Harness 已纳入请求理解 guidance 的稳定投影；M69 workflow hint 回归已修复并通过。
- 阶段验收：M130 定向回归、`ci`、`stage`、跨入口 plan evidence 回归、compileall、`git diff --check` 通过；全量离线 690 项通过、42 项按环境跳过。
- 真实 GIS、真实模型、FastAPI/Docker 仍按环境条件作为显式验收，不以本阶段离线结果代替。

### M131 全局规划

1. 让确定性 Rule Planner 通过 Domain-owned adapter 选择，Runtime factory 不再把 GIS Planner 当作所有领域的默认实现。
2. 保持 `TaskPlan`、workflow 校验、ToolRegistry 和 Runtime 执行契约不变，验证 GIS/Text/自定义 Planner 的替换、同步/异步和 artifact/recovery 入口。
3. 下一步再物理迁移 GIS Rule Planner 的剩余策略与固定回答，公共 Planner 只保留通用协调和兼容 facade；不以一次迁移破坏历史直连导入。
4. 阶段验收继续覆盖真实数据降级、脱敏模型回放、HTTP/Console 结果证据和稳定 CI。

## M131 当前实现：Domain-owned Rule Planner seam

- `DomainPack.rule_planner()` 已加入 Domain Contract；GIS 与 Text 分别提供确定性 Planner，`runtime_factory` 和 Text Runtime 均通过该 seam 选择 Planner。
- 旧的 `RuleBasedPlanner()` 直连入口保持兼容，TaskPlan/Runtime/ToolRegistry 执行契约未改变；新增 M131 适配测试验证自定义 Planner 可被 Runtime factory 替换。
- 剩余 GIS Rule Planner 实现仍保留在兼容路径中，后续阶段再做物理迁移；当前不宣称公共 Planner 已完全无 GIS 代码。
- 测试门禁同步收敛：`quick` 保留 2 个核心 tripwire，`stage` 只跑 3 个阶段验收场景，`full-stage` 只跑完整全局离线评测/模型回放；历史测试未删除，避免 profile 叠加重复执行。

## M132 全局规划

1. 从“Domain Pack 负责选择”推进到“Domain Pack 负责实现”：物理迁移 GIS Rule Planner/Composer，公共层只留下通用接口和有界兼容 facade。
2. 保持 Planner 输出的 `TaskPlan`、workflow 校验、ToolRegistry、Runtime trace/result/artifact 契约不变，并用 GIS 与 Text 两个领域做正向和负向隔离验证。
3. 审计自定义非 GIS Planner 的 Service、HTTP、artifact/recovery 证据是否复用同一 Runtime 契约；不为测试增加新的 GIS 专用分支。
4. 阶段收口只运行必要专项、`ci`、`stage`、编译和静态检查；真实 GIS、模型、FastAPI/Docker 继续作为显式环境验收，再根据产品、架构、数据、模型、部署、体验和测试七维重规划。

## M132 当前实现：GIS Planner 物理归属收口

- `domains/gis/planner.py` 现在承载 GIS `RuleBasedPlanner` 的请求事实复用、拒绝/澄清和 TaskPlan 入口；`domains/gis/rule_planning.py` 承载 GIS capability route 到 workflow builder 的具体策略。
- `agent/planner.py`、`agent/rule_planning.py` 已收敛为通用协议/兼容委托；旧 `RuleBasedPlanner`、`RuleBasedPlanComposer` 导入仍能工作，但正常 Runtime factory 走 Domain-owned Planner。
- 新增归属契约验证：实现模块必须位于 `domains.gis`，compat facade 必须委托到 Domain 实现；既有 route、facts、Text Domain 和复杂空间执行链路保持通过。

### M132 代码清理收尾

- 新增 `docs/code-cleanup-plan.md`，明确无效代码统计、测试精简边界和删除判据；不把兼容 facade、可选 live/Docker 入口或历史契约误删为“死代码”。
- 清理运行代码和测试中的确认无效导入/变量，修复静态检查发现的未定义全局和缺失类型导入；capability discovery 的有意兼容 re-export 通过 `__all__` 明确保留。
- 阶段验证：Pyflakes、Ruff F401/F821/F841、Vulture、受影响专项 102 项（5 项按环境跳过）、M81 profile 9 项、`ci`、`stage`、compileall、`git diff --check` 通过；测试用例未因数量目标删除，profile 测试的重复 subprocess 样板已抽成 helper。

## M132.1 可疑死代码与测试替身审计

- 修正相对导入后，`agent/`、`domains/`、`evaluation/` 没有孤立运行模块；无直接 import 的 `scripts/` 文件均为 README/API/PowerShell/profile/专项测试引用的显式 CLI 或验收入口。
- 删除 `AgentService._ensure_memory_session()`、`ServiceState` 中 7 个仓库内无调用的旧 runtime/session/memory-job 方法，以及两个测试替身中只赋值不读取的字段；保留兼容 alias、动态导出、结果 registry 查询和反射序列化字段。
- 验证：异步/重启/重规划/几何证据/profile 专项 43 项通过（1 项按 FastAPI 环境跳过），`ci`、`stage`、Ruff F401/F821/F841、Pyflakes、Vulture、compileall 和 diff check 通过。

## M132.2 跨入口重复 fixture 审计

- 发现 `tests/fixtures/m65_spatial_overview_response.json` 与 M67 canonical model fixture 的 `response` 完全重复；M65 Runtime/ToolRegistry 测试已改为读取 M67 的 `response`，删除重复文件。
- M127 领域回放中的同内容响应继续内嵌，保持 Text/GIS replay suite 自包含，不把跨协议 fixture 强行耦合到模型评测文件。
- M65/M67/M127/M81 相关 30 项回归通过，静态检查、compileall 和 diff check 通过；没有合并有独立失败模式的跨入口断言。重复断言样板、删除 fixture 残留引用和过期运行注释复核完成，没有新增可安全删除项。

## M133 全局规划：跨领域 Runtime 闭环验收

- 产品：用 Text 与 GIS 两个 Domain 验证统一的请求理解、能力发现、计划、执行、结果、轨迹和 artifact 闭环。
- 架构：建立 Domain Pack、Planner、ToolProvider、Result Registry、HTTP/Console 的跨入口契约矩阵，公共 Runtime 不再承载 GIS 策略。
- 数据与模型：统一 provenance、CRS/栅格对齐和降级证据；脱敏回放为默认模型证据，live planner 只作为显式验收。
- 部署与体验：验证同步/异步、SQLite 重启、artifact 恢复、多进程观测和动态 workspace 的一致性与可解释空态。
- 执行顺序：先锁定跨领域结果/执行记录矩阵，再补双 Domain 回归，随后做 HTTP/Console/artifact/recovery 验收，最后运行 GIS/live/Docker 专项并整体重规划。

## M133.1 Domain-owned ToolProvider seam

- 通用 `runtime_factory` 不再直接创建 GIS 工具注册表；`DomainPack.tool_provider()` 负责领域工具定义、provider dispatch 和 backend 选择，GIS/Text 各自实现该 seam。
- 默认权限由选定 Domain Pack 提供；Text Runtime 委托通用 Factory，rule/openai Planner 都经过同一 Registry/Runtime 执行路径；旧 Domain Pack 保留有界兼容 fallback。
- M133.1 新增 2 项跨领域回归，连同 M112/M113/M124/M126-M131 受影响回归共 49 项通过；Ruff、Pyflakes、compileall 通过。
- 下一步补 HTTP、异步、artifact/recovery 的 Domain Pack 选择矩阵，再进行 GIS/live/Docker 显式验收和全局重规划。

## M133.2 Service/HTTP 的显式 Domain Pack 选择

- `AgentService` 新增 `domain_pack` 配置 seam；与显式 `runtime_factory` 互斥，默认服务仍使用 GIS Domain Pack。
- Text Domain 通过同一 Service 配置覆盖同步、HTTP、artifact、异步 SQLite 和重启恢复；结果、planning、execution evidence 保持统一。
- M133.2 受影响回归 65 项通过；离线全量 700 项通过、42 项按环境跳过；`ci`、`stage`、Ruff、Pyflakes、Vulture、compileall 和 diff check 通过。

## M134 全局规划：部署边界的 Domain Registry 与跨入口矩阵

- 产品与体验：展示当前 Domain/Planner/Backend，并按结果类型动态展示能力、证据和 workspace；切换配置时不串用旧会话。
- 架构与部署：建立受控 Domain Registry/选择器，统一 CLI、HTTP、生产 API、Console、环境配置和 Runtime 缓存，禁止任意模块反射导入。
- 数据与模型：各 Domain 保留 provenance、健康/对齐降级策略；Text/GIS 共享 LLM Planner 接口并用脱敏回放、可选 live 基线验证计划契约。
- 测试：补配置错误负向、跨入口 Harness、SQLite/artifact/restart/multi-worker 串域矩阵，默认 `ci`/`stage` 继续离线，真实环境显式验收。

## M134 已完成：受控 Domain Registry 与持久化隔离

- 新增静态 allowlist Domain Registry，仅注册 `gis` 与 `text`；环境变量 `SPATIAL_AGENT_DOMAIN`、CLI `--domain`、Service 配置、开发 HTTP、生产 API 和 Runtime Factory 均通过同一选择边界解析，未知值和模块路径输入会被拒绝。
- 新增 `GET /domains`；capabilities、preview、run、artifact、execution record 和异步 payload 保留当前 `domain_id`，前端和运维入口可以识别当前领域。
- SQLite run/history/metrics、异步恢复与 reaper、普通 artifact/Action history 和幂等读取按 Domain 过滤；同一 run_id 跨 Domain 覆盖会被拒绝，旧无 domain 字段数据按 GIS 兼容。
- M134 专项 7 项、Text/GIS/SQLite/Action 受影响回归、离线全量 707 项（42 项按环境跳过）、full-stage、compileall、Ruff F401/F821/F841、Pyflakes、Vulture、`ci` 和 `stage` 均通过。真实 GIS、live 模型和 Docker 未因本阶段离线契约改动强制启动，继续作为显式环境验收。

## M135 当前实现：版本化 Runtime Context 快照

- 新增领域无关的 `spatial-agent.runtime-context.v1`，绑定 Domain、Planner、Backend、ToolProvider、权限、批准工具、依赖证据策略和核心契约版本；快照只保留有界配置，不保存请求、密钥、工具参数或原始 provider 响应。TaskPlan 与 result envelope 版本由 `agent/contract_versions.py` 统一定义。
- Runtime run/preview/capabilities、Service 同步/异步、Domain Action、SQLite snapshot、artifact 和 Console 执行证据均可读取同一 Context；异步任务在 worker 完成前就持久化快照，重启恢复会校验原快照，发现部署配置漂移时以 `runtime_context_mismatch` 失败并保留原证据。
- M135 专项 8 项、M128 执行记录回归 7 项通过；完整离线回归 715 项通过、42 项按环境跳过，`quick`/`ci`/`stage`/`full-stage`、GIS-core profile、Ruff、Pyflakes、Vulture、compileall 和 diff check 均通过。M135 已完成，下一步提交版本并按七维度整体重规划。

## M136 全局规划：跨入口 Runtime Context 与 Deployment Evidence Contract

- **产品**：让用户和面试演示能看到一次运行的 Domain、Planner、Backend、ToolProvider、权限和契约版本，并解释配置漂移、数据降级与工具失败的区别。
- **架构**：将有界 `RuntimeContext` 纳入 Cross-entry Contract Harness 的 canonical projection，统一直接 Service、开发/生产 HTTP、异步、artifact/recovery 和 Domain Action 的证据读取；旧 payload 保持兼容。
- **数据与模型**：预留不含原始路径/数据/密钥的 data provenance、健康、manifest、模型 replay/live 身份引用，使真实数据和模型证据关联到同一运行快照而不改变核心结果契约。
- **部署与体验**：补滚动重启、异步接管、配置漂移的机器错误码和恢复证据；Console 通过结构化 Context/failure/degradation evidence 动态展示状态，不增加区域专用面板。
- **测试**：先做 Context canonical projection 与漂移负向，再覆盖 HTTP、异步轮询、artifact、重启、Action、Text/GIS；默认测试不访问真实模型或私有数据，阶段末按条件运行 GIS/live/Docker。

M136 顺序任务：Context Harness -> 跨入口一致性矩阵 -> data/model evidence binding -> Console 动态展示 -> 分层验收与全局重规划。

## M136 当前实现：跨入口 Context 与模型证据绑定

- `evaluation/contract_harness.py` 将规范化 `RuntimeContext`、安全 `model_evidence` 和 provenance Context 指纹纳入 canonical projection；顶层、result envelope、HTTP、artifact 和 recovery 的位置差异不再造成假不一致，Context 字段漂移会输出有界路径。
- `result_contract.py` 新增版本化 `spatial-agent.model-evidence.v1`，只保留 provider/model/wire_api、状态、重试、延迟和 token 使用等白名单字段，并绑定 Context fingerprint；结果模型与 artifact 写入边界统一规范化 Context，排除密钥、私有路径和 provider 原文。
- 异步观测增加 `runtime_context_fingerprint`，因此提交、轮询、重启接管和最终结果可以用同一安全身份关联；Console 继续通过通用执行证据显示领域、Planner、Backend、Provider 和 Context 版本。
- 新增 M136 跨入口回归 3 项，M108/M135 安全与 Harness 回归同步扩展；受影响矩阵 83 项通过，完整离线回归 722 项通过、42 项按环境跳过，`quick`/`ci`/`stage`/`full-stage`、Ruff、Pyflakes、Vulture、compileall 和 diff check 均通过。真实 GIS、live LLM 和 Docker 仍作为显式环境验收，数据 provenance/manifest 深化进入下一阶段。

## M137 全局规划：统一 Deployment Evidence Contract

- **产品**：让一次运行、一次发布检查和一次模型评测都能回答“使用了什么配置、数据是否可信、模型证据来自哪里、结果是否可恢复”，并由前端按结构化证据展示可信度。
- **架构**：在现有 `RuntimeContext`、`evidence_contract`、`result envelope`、`provenance` 和 `model_evidence` 之上增加统一的有界 deployment evidence projection；Domain Pack 只提供领域数据证据，公共 Runtime 负责关联和比较。
- **数据**：把 runtime/release data provenance、manifest、CRS/栅格对齐、source binding 和 output manifest 压缩为无私有路径的快照；缺失、degraded、metadata-only 和 hash verified 必须可区分。
- **模型**：为 rule、offline replay、live provider 统一记录安全的执行模式、fixture/replay 标识、provider/model/wire API、token/延迟和错误分类；不复制 prompt、响应原文、密钥或 URL 查询凭据。
- **部署**：让 `/release-evidence`、生产 readiness、同步/异步结果和 artifact/recovery 使用同一 Context fingerprint；Docker/FastAPI/GIS/live 作为显式 acceptance，宿主 Docker 当前不可用不阻塞离线实现。
- **体验与测试**：Console 以通用 evidence card 显示数据/模型/运行状态；Harness 覆盖 release evidence、run artifact、async polling/restart 和 Text/GIS，默认 profile 仍不访问私有环境。

M137 顺序任务：

1. 将 release/runtime evidence 绑定到 Runtime Context fingerprint，并补 Text/GIS 正负契约。
2. 扩展安全 model evidence 的 replay/live identity，接入 evaluator 与 result/artifact/recovery。
3. 建立 deployment evidence canonical projection 和 Console 动态证据视图。
4. 运行离线/分层回归；Docker 恢复后执行当前版本 production acceptance、真实 GIS 与可选 live baseline。

## M137 当前实现进展

- Runtime runtime/release evidence 均绑定 `runtime_context_fingerprint`；Text/GIS 正向与降级路径共享 `spatial-agent.domain-evidence.v1`，不会把数据状态误当作 Runtime 配置身份。
- `model_evidence` 支持 `rule`、`offline_replay`、`live_model` 三种安全执行模式；脱敏评测报告带有界 `fixture_id`，真实客户端保留 provider/model/wire API 和 token/延迟/错误分类，不复制原始响应。
- 新增 `spatial-agent.deployment-evidence.v1`，聚合 Context、模型、runtime/release 数据状态、manifest/source/output verification 和降级摘要；结果 envelope、runtime capabilities、release evidence 与 Console 共享该投影。
- M137 专项 4 项、M135/M136 相邻 Context/跨入口专项 12 项通过；`quick`、`ci`、`stage`、`full-stage`、compileall、Ruff、Pyflakes、Vulture 和 `git diff --check` 均通过；完整离线回归 726 项通过、42 项按环境跳过。Docker 宿主当前不可用，真实 production/GIS/live 证据不提前宣称。

## M138 全局规划：Deployment Evidence 跨入口验收与发布 readiness

M137 的统一 deployment evidence 已进入 Runtime、release、result 和 Console，但生产 acceptance 还没有把该投影作为跨入口门禁。M138 先补齐 runtime capabilities、`/release-evidence`、同步/异步结果、失败结果、artifact/recovery 的一致性检查，再完善通用前端证据卡；所有数据、模型和部署专项都通过该公共契约接入，不新增 GIS 区域规则。

### M138 顺序任务

1. 增加 deployment evidence 的生产脚本断言：schema、状态、Context fingerprint、模型执行模式、必需 section 和敏感字段过滤。
2. 将 release endpoint、运行 artifact、失败运行和异步终态纳入同一 acceptance 结果摘要与 Contract Harness。
3. 让 Console 展示 deployment/data/model/recovery 的有界摘要和发布证据引用，Text/GIS 共用渲染路径。
4. 以少量离线契约、PowerShell parser 和显式环境验收收口；Docker 不可用时保留未验证证据，不用旧容器结果替代当前版本。

## M138 当前实现状态

- 生产 acceptance 已增加 `spatial-agent.deployment-evidence.v1` 门禁：runtime capabilities、`/release-evidence`、同步/失败/异步运行和 artifact 均校验 schema、Context fingerprint、模型模式、数据/降级 section 与敏感字段边界。
- Console 统一执行证据显示 deployment/data/degradation 摘要，并可从 lineage 打开 `/release-evidence`；没有增加 GIS 专用渲染分支。
- M138 关联回归 19 项通过（1 项真实 Docker acceptance 按环境跳过）；`quick`、`ci`、`stage`、`full-stage`、compileall、Ruff、Pyflakes、Vulture、PowerShell parser、Node 内嵌 JS 和 `git diff --check` 通过；完整离线 726 项通过、42 项按环境跳过。
- Docker Linux engine 当前不可用，FastAPI/Docker/真实 GIS/live production acceptance 仍待环境恢复后执行。

## M139 当前实现状态

- GIS intent/clarification 已下沉到 `domains/gis/intent.py`；公共 `agent.spatial_intent` 仅做惰性兼容委托，GIS Rule Planner 直接使用 Domain-owned policy。
- `DomainPack.clarification_details()` 和 Runtime fallback 贯通 preview/run：缺少 Planner details 时由选定 Domain 提供结构化澄清，Text Domain 不输出 GIS 选项。
- M139 专项 3 项、M62/M130 相关回归 11 项通过；`quick`、`ci`、`stage`、`full-stage`、compileall、Ruff、Pyflakes、Vulture 和 `git diff --check` 通过；完整离线 729 项通过、42 项按环境跳过。
- 真实 GIS/live/FastAPI/Docker 仍是显式环境验收；下一阶段继续把 capability 的必需事实和开放式回放做成 Domain-owned 通用契约。

## M139 全局规划：Domain-owned 开放式澄清与能力发现

下一阶段从整体 Agent 闭环推进请求理解边界：公共 `agent/spatial_intent.py` 仍包含 GIS 词汇和缺参策略，M139 将其迁移到 GIS Domain，建立可替换的 intent/clarification seam，并让 preview、run、HTTP 和模型回放共用结构化 discovery evidence。该阶段不新增区域专用功能，继续保持默认离线测试和最大并发度 1。

### M139 顺序任务

1. 定义 Domain-owned intent/clarification projection 与兼容 facade。
2. 迁移 GIS 词汇/澄清逻辑，补 Text 领域隔离和旧导入回归。
3. 贯通 Rule/LLM preview、run、HTTP 的澄清 evidence，确保不初始化 backend。
4. 增加一条开放式脱敏回放和跨入口契约，阶段收口后再决定真实 GIS/live/Docker 验收。

## M140 全局规划：CapabilityCatalog-owned 请求需求与真实部署复验

M139 已完成 GIS intent 的领域归属，但能力所需的区域、数据集和约束事实仍可能重新落回 capability ID 分支。M140 从完整 Agent 闭环推进声明驱动的请求澄清：能力目录声明有界 `request_requirements`，通用投影器比较 RequestFacts，Domain 只提供词汇和能力定义；同时用当前工作树完成真实 GIS/Docker 验收。

### M140 顺序任务

1. 在 CapabilityCatalog 增加版本化、长度受限的实体/数据集/约束需求归一化和通用 `missing_fields` 投影。
2. 为 GIS 能力声明区域、数据集和筛选阈值需求；删除 intent 中按 capability ID 推断缺参的逻辑，并验证 Text Domain 隔离。
3. 修复生产 acceptance 的 Python 解释器解析和 Harness 空输出诊断；使用 `.env.production` 正确展开真实数据卷并重建当前容器。
4. 运行 M140/相邻回归、分层离线 profile、GIS-core、Docker production acceptance 和一次脱敏 live smoke；据全局结果规划下一阶段。

## M140 当前实现与验证状态

- `agent/capability_catalog.py` 新增 `spatial-agent.capability-requirements.v1` 归一化和通用需求投影；`domains/gis/catalog.py` 声明实体、数据集与约束需求；GIS intent 不再按 capability ID 硬编码缺参，Text Domain 不继承 GIS 词汇。GIS legacy evidence 的 `capabilities` 在 Domain adapter 内归一化为 `capabilities_runtime`。
- `production_acceptance.ps1` 自动跳过 WindowsApps Python alias，Harness 失败报告实际解释器和退出码；生产重建使用 `--env-file .env.production` 将 `D:/dataset/agent` 挂载到 `/data`。当前容器 healthy，核心/可选数据 ready，preview、同步/artifact、失败证据、错误边界和异步幂等均通过。
- M140/M139/M62 专项 15 项、`quick`、`ci`、`stage`、`full-stage`、GIS-core、compileall、Ruff、Pyflakes、PowerShell parser、`git diff --check` 和全量离线 735 项通过（42 项按环境跳过）。live smoke 的约束建设案例通过；空间总览因模型生成重复 `range_query` 与未声明依赖被严格 `tool_validation` 拦截，provider error 为 none，未将部分 live 结果宣称为全量通过。

## M141 当前实现与验证状态

- `agent/runtime.py` 已增加 planning-phase bounded plan repair：初始 TaskPlan 校验失败时，LLM Planner 最多修复一次；修复计划重新通过 workflow、TaskPlan 和 ToolRegistry 校验，planning repair 与 execution replan 共用单次预算。repair context 只继承有界的工具、能力发现、能力目录和 workflow template 投影，不携带凭据或模型原文。
- `agent/replanning.py`、`result_contract.py` 和 `agent/trace_formatter.py` 已为 repair lineage 增加受限 `phase`（`planning`/`execution`）；preview、同步执行、artifact/recovery 的证据保持一致。Rule Planner 不进入模型修复分支，避免改变默认离线确定性行为。
- M141 专项与 M80/M99/M102/M81 相邻回归 34 项通过；`quick`、`ci`、`stage`、`full-stage` 和全量离线 739 项通过、42 项按环境跳过；新增文件的 F401/F821/F841、Pyflakes、compileall 和 `git diff --check` 通过。
- Docker Engine 29.6.2 使用国内镜像重建，真实 `D:/dataset/agent` 数据卷挂载正确，容器 healthy，production acceptance 全部通过。验收期间修复 production FastAPI JSON 未声明 UTF-8 charset 导致 PowerShell sync/artifact contract 比较乱码的问题，并增加 `UTF8JSONResponse` 契约测试。真实 live 复杂总览仍是可选基线，不能以本阶段离线/容器验收替代完整 live 成功声明。

## M142 全局规划参考

M141 已让计划校验失败具备一次安全修复能力，但 repair 仍主要是 Runtime seam，尚未形成跨入口的模型质量评估和用户可恢复交互。下一阶段从全局推进“计划修复质量与可解释交互”：先建立脱敏 replay 的 repair quality 评测和错误分类，再验证异步/重启/HTTP/artifact 的 repair lineage，最后让 Console 对“已修复/拒绝/需澄清”使用统一动态证据。继续保持单线程、默认离线，不为单个 GIS 区域增加专用分支；真实 GIS/live/Docker 作为阶段收尾证据。

## M142 当前阶段：极简测试门禁与历史测试隔离

M141 之后的首要工程问题不是继续增加测试，而是降低反馈成本。M142 将测试分为 compact active gate 与显式历史诊断资产：默认 discovery、quick、smoke 和 CI 只验证少量共享 Runtime/HTTP 契约；阶段 acceptance、GIS、live、Docker 和历史里程碑测试仍保留，但不再隐式参与日常门禁。

- 新增 `tests/__init__.py` 的 active module allowlist 与 3 个 Runtime/artifact/澄清 smoke、1 个标准 HTTP 健康契约；`python -m unittest discover -s tests -t .` 实际只运行 4 项。
- `quick` 只运行 2 个 compact Runtime 契约，`ci` 收敛为 quick + service smoke，不再每次 push 重跑阶段代表场景；`stage`、`full-stage`、GIS、live、Docker 保持显式入口。
- 历史测试文件不删除，仍可按模块显式运行；README、测试策略、smoke、CI、恢复文档统一使用 `-t .`，避免平铺 discovery 绕过 active suite。该边界和原因已记录到中文问题文档。
- 验证：compact discovery 4 项通过、quick 2 项通过、ci 两个检查通过、stage 代表性验收通过、`smoke_check.py --with-unit-tests` 运行 4 项并通过；未将历史全量回归误报为默认门禁。

## M143 全局规划参考

在测试反馈已经收敛后，下一阶段再从全局 Agent Runtime 评估是否需要补充跨入口契约：优先以一条 compact contract 验证 Planner、Runtime、ToolRegistry、结果 envelope 和 artifact；只有共享边界发生变化时才扩展专项测试。真实数据质量、模型 replay/live、部署和 Console 继续通过显式阶段入口验收，避免测试规模再次按里程碑累加。

## M143 当前阶段：跨入口最小契约证据

M143 将 M142 的 compact gate 与总体验收标准重新对齐：同一条稳定结果投影现在同时覆盖 direct Service、真实 CLI、HTTP `/runs` 和 artifact。该阶段没有增加 active 测试数量，而是提高单条契约的入口覆盖，证明前端所消费的 HTTP result envelope 与 CLI/持久化结果保持一致。

- `tests/test_dev_gate.py` 的 Runtime/artifact gate 运行同一请求，比较 Service、`run_demo.py`、标准库 HTTP 服务和两份 artifact 的 `evaluation.contract_harness` 结果。
- 比较投影包含结果类型、中文答案、Planner/能力证据、工具步骤、轨迹、workspace/views 和 execution contract；排除 run ID、路径、时间等传输差异。
- 验证：compact discovery 4 项、CI 的 quick + service smoke、Pyflakes、compileall 和 `git diff --check` 通过；默认门禁仍不访问真实模型、私有数据或历史全量测试。

## M144 全局规划参考

下一阶段从整体产品闭环检查 Domain-owned view spec、结果 envelope 与前端动态 renderer 是否真正跨 GIS/Text 可替换：先梳理通用 view schema 和空态/未知 view 的处理，再补一个跨领域负向契约，避免新增领域时把前端重新写成 GIS 专用分支。真实 GIS、live、Docker 和历史测试继续作为显式验收，最大并发度保持 1。

## M144 当前阶段：跨领域动态 view contract

M144 将前一阶段的跨入口结果一致性继续推进到用户界面：Text Domain 通过自己的 `ViewSpec` 和 view builder 提供结构化摘要，公共 Console 仅按 workspace/view spec 动态渲染。这样新增领域可以提供自己的 view model，而不需要在 `web/index.html` 中增加结果类型判断。

- 新增 `domains/text/views.py`，输出 bounded `generic` view（摘要、字符数、词数），并注册 `spatial-agent.view.v1` 的 `ViewSpec`。
- Console generic renderer 接受 `generic` 及未知 view ID，统一处理 metrics、rows、table、error、note 和 raw fallback；没有加入 `text_summary_result` 专用前端分支。
- 验证：M122/M113/M124/M133 跨领域专项 21 项、Console 静态 smoke 14 项、compact 4 项、Pyflakes、compileall、Node smoke 脚本语法检查通过；当前 Docker 重建后 healthy，production acceptance 通过。
- 宿主 Chrome CDP 本轮启动失败，动态浏览器 smoke 未宣称通过；静态契约与 Docker/API 证据保持明确边界。

## M145 全局规划参考

下一阶段从整体闭环补齐 generic view 的空态、降级和 artifact 引用：这些状态应来自结构化 evidence，并在 Text/GIS 的同步、异步恢复和 HTTP 入口中保持一致。默认 compact 门禁不扩张；动态浏览器 smoke 仅在 CDP 环境恢复后显式运行。

## M145 当前阶段：统一 view 空态与恢复证据

M145 继续沿完整 Agent 闭环推进结果可信度：view 不再只有“成功数据”或 raw JSON 两种状态。公共结果契约将声明的 ViewSpec、降级矩阵和 artifact 可恢复性组合成统一 `unavailable` view，保证失败、空结果和旧 artifact 恢复时仍能被 API、artifact 与 Console 解释。

- `result_contract.py` 新增 bounded view fallback：按 ViewSpec 生成 `kind: unavailable`、有界 `reason` 和 `artifact_available`；未注册但声明 generic workspace 的结果也有通用 fallback。
- `AgentService.get_run()` 不再用旧 artifact 的空 view map 覆盖当前契约；成功 artifact 的非空 view 仍保持权威。前端 generic renderer 渲染 unavailable 状态和安全 basename artifact 链接。
- 验证：M122/M113/M124/M133 相关 22 项、Console 静态 smoke 14 项、compact 4 项、CI、Pyflakes、compileall、Node 脚本语法检查和 Docker production acceptance 通过。
- Chrome CDP 本轮仍未监听，动态浏览器 smoke 明确未验证；不使用 Docker/API/静态检查替代浏览器证据。

## M146：异步结果证据生命周期（已完成）

M146 将 M145 的 view 空态继续贯通到异步生命周期。`GET /runs/{run_id}/async` 增加有界 `spatial-agent.async-result-evidence.v1`，由公共 result contract 与选定 Domain registry 生成，统一暴露 pending/success/degraded/unavailable、结果类型、workspace/view 状态和 artifact 是否可恢复；不泄露请求、模型原文、工具错误或宿主文件路径。

- SQLite 重启、终态轮询、artifact 和 HTTP `/async` 的 Text Domain 专项 2 项通过。
- 宿主 compact/CI、Docker 容器专项与 compact/CI、生产 acceptance 均通过；真实容器 Engine 29.6.2、核心/可选数据 ready、async view state=`success`。
- acceptance 首次真实 GIS cold start 约 8 秒，已将 GET 验收超时从 5 秒提高到 30 秒并记录原因；这不是业务错误。
- 未执行 Chrome CDP 动态 smoke；未改变默认 active suite 数量。

## M147 规划参考

围绕证据版本迁移、旧 artifact 兼容、跨 Domain 负向隔离和动态 Console 消费做下一条全局纵向切片，继续保持单线程、最小 active gate 与显式 Docker/GIS/live 验收。

## M147：artifact 版本化、安全恢复与 async Console 消费（已完成）

M147 在 M146 async evidence 之上补齐公共 artifact 边界：run artifact 写入 `spatial-agent.run-artifact.v1`，旧的无版本 artifact 保持兼容，未知版本拒绝解释；`run_id` 对写入和读取都执行跨平台安全文件名校验，Domain 过滤继续保护恢复和列表入口。Console 以通用 renderer 消费 async result evidence，不按 Text/GIS 结果类型硬编码。

- M147 专项 3 项，M146/M122/M124/M133 相邻专项共 19 项通过；compact、CI、compileall、内嵌 JS 语法检查通过。
- 最终 Docker 镜像内 M147/M146 专项 5 项通过，生产 acceptance 通过：核心/可选数据 ready、artifact contract ok、async view state=`success`、失败/400/幂等边界通过。
- 未执行动态 Chrome CDP smoke；没有将 Docker/API/静态 JS 证据替代浏览器证据。

## M148 规划参考

将 artifact/async evidence 版本投影接入 Contract Harness，并完成 Text/GIS 双 Domain 的 HTTP/Console 负向隔离矩阵；保持极简默认门禁，M148 起允许最多 5 个边界清晰的并行子任务，公共 schema 与 Runtime 状态由主线统一集成。

## M146 全局规划参考

下一阶段从项目整体验证 view evidence 的异步生命周期：同步、SQLite、多 worker、重启恢复、artifact 详情和 HTTP 轮询必须保留相同的 success/degraded/unavailable 语义；同时检查 artifact 引用的安全边界。默认 active suite 继续保持极简，专项按风险显式执行。

## M141 全局规划参考：模型计划稳健性与通用修复闭环

下一阶段不围绕洪山区或某个工具追加规则，而是从整体 Agent Runtime 处理 M140 暴露的跨边界风险：规则 Planner、脱敏 replay 和 live Planner 必须共享同一 capability requirements、TaskPlan schema、DAG 校验、ToolRegistry 和 repair lineage。

1. **产品能力**：展示模型计划被校验、修复或拒绝的可读原因和可恢复动作。
2. **架构边界**：建立有预算的 bounded plan repair seam；只允许基于 capability/tool schema 的有界替换，禁止绕过 Registry。
3. **数据质量**：repair 继续绑定数据健康、覆盖、CRS/对齐和 provenance evidence，不把真实 GIS 降级误报为模型失败。
4. **真实模型**：增加复杂总览的脱敏 replay 与一次可选 live 基线，记录重复步骤、未声明引用、token 和延迟，不保存原文/密钥。
5. **部署可靠性**：验证同步、异步、artifact/recovery 和多 worker 中 repair lineage 一致，保留明确的配置漂移、超时和 provider 暂态分类。
6. **用户体验**：Console 使用通用规划/修复/失败证据动态展示，不增加 GIS 专属页面分支。
7. **测试证据**：先做 schema/DAG/repair 契约测试，再做 Text/GIS replay、HTTP/artifact/async 矩阵，最后运行 Docker/GIS/live 显式验收。

## M148：跨 Domain artifact、async evidence 与 Docker replay（已完成）

M148 从完整 Agent Runtime 视角收敛跨入口证据边界，而不是增加 GIS 专用分析规则。Contract Harness 现在比较 artifact schema、async result evidence、degradation/view states 和 artifact availability；路径、run_id、时间等传输细节不进入稳定投影。

- 新增统一 Domain-aware artifact 访问函数，开发 HTTP 与生产 FastAPI 对 run/action/GeoJSON 下载执行同一 Domain 校验；Text/GIS 负向矩阵覆盖三类 artifact。
- run artifact 保存有界 async result evidence；SQLite job 丢失时从 artifact 恢复，旧 artifact 缺失 evidence 时明确返回 `unavailable + availability=unknown`。
- 修复异步自定义 Runtime Context 使用错误缓存 key 导致的 HTTP 500：ServiceState 的 tuple key 与提交快照一致；无选择器 run detail 从持久化 Context 推断 planner/backend。补充 artifact evidence 的首次轮询/重启恢复一致性。
- Console 根据 `/capabilities.domain_id` 动态隐藏并禁用 GIS 专用控件，保持通用结果 renderer，不增加 Text/GIS 结果类型分支。
- 新增 opt-in Docker/offline replay，覆盖 Text 与真实 GIS 的 LLMPlanner、ToolRegistry、AgentService、同步 artifact、HTTP async、轮询和 SQLite/artifact 恢复；两例通过，模型执行模式为 `offline_replay`，重启后不重复调用模型。GIS degraded 状态被正确保留。
- 验证：M148 及相邻专项 25 项通过；Docker replay 和 `scripts/production_acceptance.ps1` 均通过。宿主 FastAPI 生产路由单测因依赖未安装跳过，但容器生产 acceptance 已覆盖实际生产入口；Chrome/CDP 与 live provider 保持独立未执行证据。

下一阶段 M149 从整体推进嵌套 result/view/workspace schema 迁移、replay/live plan repair 证据和生产 FastAPI/Console 动态矩阵；默认 active suite 保持精简，最大并发度为 5。

## M149 当前执行规则：并发度调整为 5（进行中）

M149 使用最多 5 路并行开发。并行任务必须具备独立写入边界和专项验收；共享 schema、result envelope、Runtime 状态迁移与前端核心函数由主线负责集成，合并后统一运行精简门禁和显式环境验收。此前 M141-M147 记录的单线程约束属于历史阶段。

## M149 当前实现状态（已完成）

- 主线新增统一嵌套 schema 迁移/校验 seam；legacy 缺失版本可读，未知 result/workspace/views/view/panel 版本拒绝静默解释。
- artifact、HTTP、async recovery 和 Console 均使用有界 unavailable fallback 或安全拒绝；plan-repair replay/live 评测使用同一脱敏证据投影。
- M149 专项与 M147/M148 相邻回归 28 项通过（FastAPI 环境相关 3 项跳过）；quick、ci、stage、full-stage 和 Node smoke 通过。动态 Chrome/CDP、live provider、Docker 仍未作为本阶段已通过证据。

## M150 全局规划参考

M150 不再扩展单一 GIS 数据集，而是把 M149 的契约边界推进到完整 Agent 闭环：

1. **产品能力**：公开计划修复/拒绝原因、可恢复动作和最终证据，支持多轮继续执行。
2. **架构边界**：建立 capability-guided、预算有界的 Runtime plan-repair seam，仍统一经过 TaskPlan、DAG、ToolRegistry 和 result envelope。
3. **数据质量**：将数据健康、覆盖、CRS/对齐和 provenance 绑定到 repair 决策；缺数据只产生可解释降级。
4. **真实模型**：replay 与可选 live 共享 repair lineage、token/延迟和 provider error 的脱敏投影。
5. **部署可靠性**：补 FastAPI 依赖环境、同步/异步/artifact/recovery 生产矩阵和滚动重启证据。
6. **用户体验**：完成 Console 动态浏览器/CDP 验收，统一显示计划、修复、视图空态和恢复链接。
7. **测试证据**：active suite 继续保持极简；M150 使用显式 profile，最多 5 路并行，阶段末统一专项、Docker、live 和浏览器验收。

## M150：Runtime 计划修复执行闭环（已完成）

M150 将 capability-guided plan repair 从评测投影推进到可替换的 Runtime 执行 seam。`PlanRepairEngine` 统一负责有界 capability context、repair budget、Planner 调用、TaskPlan/workflow 校验和 repair lineage；Rule Planner 不调用模型 repair，所有替换计划仍经过 DAG、ToolRegistry 和结果契约边界。

- replay/live 评测、同步/异步/artifact/recovery、生产 acceptance 和 Console 使用同一类脱敏 repair evidence；Console 新增通用决策证据区域，可显示修复、拒绝、澄清和 provider 不可用状态。
- 修复 Contract Harness 漏读 artifact 顶层 `async_result_evidence` 的真实 Docker acceptance 问题，新增回归覆盖在线终态与 artifact 等价；FastAPI TestClient 缺少 `httpx2` 时测试明确跳过，生产镜像不引入非必要测试依赖。
- M150 专项 15 项通过、1 项宿主环境跳过；M141/M148/M149 相邻回归 31 项通过、3 项环境跳过；M80 回归 32 项通过；quick、ci、stage、full-stage、compileall、diff check 通过。Docker Text/GIS offline replay 和当前镜像 production acceptance 通过，真实 GIS 数据卷、同步/异步、artifact contract、失败/400/幂等和 async evidence 均已验证。
- Chrome/CDP 动态浏览器与外部 live provider 未执行，不能以 Docker/API/静态 Console 证据替代。

## M151 全局规划参考

从全局 Runtime 推进“可修复”到“可控继续执行”：先定义跨 Domain 的 repair decision/action contract 和多轮恢复边界，再贯通 HTTP、异步、artifact、Console 与评测，最后进行 Docker、可选 live planner 和浏览器动态验收。避免为单一区域或单一 GIS 数据集增加硬编码规则，默认 active suite 保持精简，最多并行 5 路。

## M151：计划确认与可控继续执行（已完成）

M151 新增版本化 `DecisionStore` 和 `WAITING_FOR_DECISION` 状态。Runtime 在计划校验后可以保存原始计划、fingerprint 和脱敏决策证据，用户批准后从同一计划快照继续执行，拒绝则保持工具未执行；SQLite 使用版本 CAS 防止重复提交。

- Service、标准库 HTTP、FastAPI、异步轮询、SQLite 重启和 result envelope 已接入统一 decision projection；Console 提供可选执行前确认及批准/拒绝按钮。
- M151 专项 8 项、M46/M10 相关回归 19 项通过；Docker、live planner 和 Chrome/CDP 仍是独立显式验收，未用离线证据替代。

## M152 全局规划参考

统一澄清补充、计划修复批准、失败重试/恢复和用户确认的 action contract，补齐过期/取消、artifact-only recovery、跨进程 CAS 及 Text/GIS 双 Domain 的显式部署验收。

## M152：决策 artifact 恢复与过期/取消边界（已完成）

M152 将 M151 的确认状态推进到可恢复边界：run artifact 保存有界 decision record 和完整计划节点；无 SQLite 的新服务可以找回待确认决策并批准原计划，不重新调用 Planner。SQLite DecisionStore 对过期决策执行 CAS，待确认运行可取消且不会 dispatch 工具，默认决策 TTL 为 30 分钟。

- artifact、SQLite、嵌套结果契约和 M151 决策专项共 40 项回归通过；quick/ci 通过。
- Docker、真实 live planner 和 Chrome/CDP 仍为独立显式验收，未以离线证据替代。

## M153 全局规划参考

统一澄清补充、计划修复、用户确认、拒绝、重试和恢复的 action/version/evidence contract，优先覆盖重复提交、未知 action、artifact、HTTP、异步和 Console 一致性。

## M153 当前实现状态

- 新增领域无关的 `agent/action_lifecycle.py` 深模块；它与 `DecisionLifecycle` 分离，只做无 I/O 的 bounded run/Action 状态投影。
- `result_contract.py`、run artifact、async result evidence 和 Console decision evidence seam 已消费 `spatial-agent.action-lifecycle.v1`，统一展示澄清、确认、失败恢复、重试和修复计数；未知 async lifecycle 版本回落到安全状态。
- 新增 4 项 M153 专项，覆盖等待确认/恢复动作过滤、未知状态拒绝默认为失败、result/async 生命周期一致性和 Contract Harness 稳定比较；M151 11 项、M149/M150 相邻契约 16 项、quick、compact discovery 和 Node 语法检查通过。
- 当前版本 Docker production acceptance 已通过，真实 live-short 已执行但两个案例均因模型重复步骤的 `tool_gate` 失败；动态 Chrome/CDP 尚未作为 M153 已通过证据。该 live 失败已记录到 `docs/agent-development-issues.md`，下一阶段修复 Planner/Workflow repair seam。

## M154 全局规划参考

在 M153 生命周期投影稳定后，从项目整体推进“动作可执行、证据可比较”：把 lifecycle 纳入 Contract Harness、artifact-only recovery 和 HTTP/异步重复提交矩阵，再验证 Console 动作按钮是否严格由 `allowed_actions` 驱动。保持默认 active suite 精简，Text/GIS 双 Domain、Docker、live 和浏览器作为显式阶段验收。

## M154：通用 Workflow-aware Planner Repair（已完成）

M154 将 M153 暴露的真实模型重复步骤问题收敛为通用 Planner/Workflow seam，不放宽 ToolRegistry、TaskPlan schema 或 DAG 门控，也不增加洪山区专用分支。

- 新增 `agent/plan_quality.py`，对唯一匹配的 workflow blueprint 进行有界诊断，检查步骤数量、顺序、id、tool、参数键和依赖；诊断只产生 issue code，不静默删除或去重模型步骤。
- 规划阶段 `PlanRepairEngine` 和执行阶段 adaptive replan 均收到同一份 bounded blueprint context；replacement/merged plan 必须再次通过 blueprint quality 校验后才能继续执行。
- LLM Planner 在 `range_query` 参数边界对模型常见的 `op`、`=` 等无歧义比较符做有限 canonical normalization；最终参数仍由 ToolRegistry 严格校验，冲突或未知值不会被猜测放行。
- 验证：容器内 M154、M141、M150 和 M2 相关专项 30 项通过；Docker `ci`、`stage`、production acceptance 通过；容器内真实模型 + 真实 GIS `live-short` 2/2 通过，两个案例均为 `COMPLETED`、错误分类 `none`。容器 runtime/data health ready，生产同步的 warning/degraded 状态按契约保留。
- 宿主 Python 3.14 缺少 Rasterio 的失败已与代码证据区分；最终 live 证据使用重建后的 Docker GIS 环境。动态 Chrome/CDP 仍未作为本阶段通过证据。

## M155 全局规划参考

M154 已让模型计划在 workflow repair 后可执行，下一阶段从项目整体推进“计划质量证据跨入口一致”：将 plan-quality/repair lineage 统一投影到 replay、live、同步、异步、artifact/recovery、HTTP 和 Console，并验证开放式非模板能力仍保持可组合而不是被模板硬编码。继续保持默认 active suite 精简，真实模型、真实 GIS、Docker 和浏览器使用显式验收；不新增单区域专用规则。

## M155：计划质量证据跨入口一致性（已完成）

M155 将 M154 的 workflow-aware 计划校验从 Runtime 内部诊断推进为公共、可迁移的证据契约。新增 `spatial-agent.plan-quality-evidence.v1`，统一表达唯一蓝图匹配、蓝图不匹配和没有唯一蓝图三种状态；计划修复与执行重规划事件同时保留修复前后的有界质量快照，不静默删除模型步骤。

- 同步结果、artifact、异步轮询和 Contract Harness 均消费相同的 `plan_quality` 投影；异步 artifact-only recovery 也保留该证据。
- replay/live 脱敏评估增加 Runtime 计划质量投影；Console 依据结构化证据展示计划质量状态，并明确“未套用唯一模板蓝图”。
- 新增 M155 专项 4 项；M155 及 M154/M150/M149/M148/M81 相邻契约合计 26 项宿主通过；quick、stage、compileall、Node 语法检查和 `git diff --check` 通过。
- 当前 Docker 镜像已重建；容器内 M155/M154 专项 8 项通过，production acceptance 通过（运行时/核心与可选数据 ready、同步/异步 artifact contract ok）。本阶段未执行外部 live provider 和动态 Chrome/CDP，不以 Docker/API/静态证据替代这两类验收。

## M156 全局规划参考

从项目整体继续推进“证据可操作化”而不是增加 GIS 专用功能：

1. **产品能力**：让计划质量、修复 lineage、生命周期和结果视图形成可读的统一执行时间线，明确用户何时可批准、重试、澄清或恢复。
2. **架构边界**：将 plan-quality 与 repair lineage 从结果字段进一步抽象为版本化 Evidence Registry/投影，供未来 Planner、Domain Pack 和入口复用；保持 ToolRegistry 为最终执行边界。
3. **数据质量**：在质量证据与 GIS 数据 readiness/degradation 之间建立引用关系，只说明“计划可执行性”和“数据可用性”各自的证据，不把二者混为模型成功。
4. **真实模型**：运行当前版本的最小 live replay/live 基线，验证真实模型在唯一模板、开放式无模板和修复失败三类请求中都输出可解释证据。
5. **部署可靠性**：覆盖异步轮询、artifact-only recovery、重启接管和旧证据版本迁移，确保新证据缺失时是明确 unavailable 而不是静默成功。
6. **用户体验**：Console 继续消费通用 Evidence，不新增 GIS 结果类型分支；把计划 DAG、质量状态和修复事件合并到紧凑时间线。
7. **测试证据**：默认 quick/stage 保持精简；新增跨入口 Evidence Harness 后，再按风险运行 Docker/GIS/live/browser 显式验收。

## M156：统一执行时间线证据（已完成）

M156 将计划质量、步骤状态、修复事件和生命周期组合为领域无关的 `spatial-agent.execution-timeline.v1`。它是只读展示/比较投影，不替代 Runtime 状态机，也不复制请求、参数、原始错误或时间戳。

- result envelope、ArtifactStore、异步轮询和 Contract Harness 均保留同一执行时间线；未知或缺失版本安全降级为 unavailable。
- Console 的通用证据区显示时间线事件数量和可追溯状态；没有增加 GIS 专用结果分支。
- 新增 M156 专项 3 项；M155/M156 相邻契约 7 项通过，quick、stage、compileall、Node smoke 和 `git diff --check` 通过。
- 当前 Docker 镜像重建后，M155/M156 容器专项 7 项和 production acceptance 通过；异步 artifact contract、幂等、恢复与核心/可选数据 ready 通过。
- 外部 live provider、动态 Chrome/CDP 仍未执行，继续作为独立显式验收。

## M157 全局规划参考

从整体推进时间线“可操作化”和真实模型验证：

1. 将时间线事件与统一 lifecycle `allowed_actions` 关联，支持通用批准、重试、澄清和恢复入口。
2. 为 Evidence Registry/引用索引确定最小公共接口，避免 result、async、artifact 和 Console 各自拼接证据。
3. 在 Text/GIS 双 Domain 验证开放式无模板请求、计划修复失败和数据降级的时间线一致性。
4. 运行当前版本最小 live baseline 与可用浏览器/CDP 验收；默认 CI 继续离线精简。

## M157：执行时间线动作投影（已完成）

M157 将执行时间线与统一 Action Lifecycle 连接：时间线终态事件现在携带 `allowed_actions`，但只接受 Lifecycle 已声明的动作。前端和异步消费者可以据此显示通用“澄清/取消/批准/重试/恢复”能力，不需要按 Domain 或结果类型猜测按钮。

- 时间线构建和归一化均执行 lifecycle action allowlist；未知动作被过滤，不能通过 artifact 或手写 async evidence 注入危险操作。
- 新增 M157 专项 2 项；M155/M156 相邻契约 9 项通过，quick、stage、compileall、Node smoke 和 `git diff --check` 通过。
- Docker 当前镜像重建后，M156/M157 容器专项 5 项和 production acceptance 通过；async artifact contract、幂等、恢复和数据 readiness 保持通过。
- 外部 live provider、动态 Chrome/CDP 尚未执行。

## M158 全局规划参考

下一阶段从整体推进证据引用和可恢复动作：定义最小领域无关 Evidence Registry/lineage reference，让 result、async、artifact、Console 和未来 Domain Pack 使用同一证据索引；随后验证动作执行仍以 Runtime/ToolRegistry 为边界，并运行 Text/GIS 双 Domain、live 和浏览器显式验收。
