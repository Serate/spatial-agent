# Spatial Agent 阶段记录

本文档记录项目每个阶段完成的功能、验证结果和关键工程决策。README 只保留当前能力与使用方式；后续阶段完成后，先更新本文档，再更新恢复文档，并创建对应 GitHub 版本。

## 当前执行规则

- 当前最大并发度为 1，阶段任务按依赖顺序单线程执行，不启动并行子任务。
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
