# Spatial Agent 阶段记录

本文档记录项目每个阶段完成的功能、验证结果和关键工程决策。README 只保留当前能力与使用方式；后续阶段完成后，先更新本文档，再更新恢复文档，并创建对应 GitHub 版本。

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
- 每个大阶段先按模块边界拆成可独立验收的子任务；无依赖的子任务可以并行，最大并发数为 5。
- 并行任务必须共享工具 schema、运行状态、结果 envelope、评测用例和数据能力契约，集成阶段统一解决冲突并执行全量回归。
- 阶段完成的判定同时包含功能、离线测试、GIS 测试、浏览器/HTTP 验收和文档更新；通过后创建并推送一个 GitHub 版本。
- 每次阶段复盘必须从项目整体能力、数据质量、真实模型、部署可靠性和用户体验五个维度重新规划下一阶段。

## 下一阶段 M59：统一能力编排与全局评测扩展

- 将数据集健康能力、工具依赖、结果类型和环境要求收敛为可查询的能力目录，供 Planner、Runtime、Console 和评测共同消费。
- 扩展全局评测矩阵的跨环境执行与报告对比，明确区分规划成功、工具执行成功、真实空间几何和演示结果。
- 为异步运行、会话恢复、失败重试和结果引用增加跨进程部署契约测试。
- 以最多 5 路并行拆分能力目录、评测报告、部署契约和 Console 展示，最后统一集成验收并重新规划 M60。

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
- 按依赖最多拆分 5 路并行任务，集成后重新验收真实模型、GIS 数据和部署链路。

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

- 一个大阶段最多拆成 5 个并行子任务；只有边界清晰、互不修改同一核心契约且可以独立测试的任务才允许并行。
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
