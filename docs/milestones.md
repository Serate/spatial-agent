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

## 下一阶段 M57：全局场景编排与验收

- 从单个工具链扩展到区域对比、时间/阈值对比、栅格-矢量联合分析的统一场景模型。
- 抽取结果 envelope、能力声明和空间证据的公共契约，减少 Planner、Runtime、API 和 Console 之间的重复判断。
- 建立覆盖“通用问答、单区域、跨数据集、多区域、不可用数据、真实模型”的端到端验收矩阵。
- 每个独立子任务最多并行 5 路，集成后必须完成全量、GIS、浏览器和部署健康验证。
