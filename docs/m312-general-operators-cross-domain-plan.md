# M312 通用分析算子与跨域真实能力实施计划

依据能力图和 Spec，按串行完整能力切片执行；每个任务覆盖实现边界，测试在阶段收口
集中执行，不为每个小改动重复跑全量测试。

## A：操作到能力/结果类型绑定

- 审计 M311 的 `analysis_operations`、`data_kinds`、capability、workflow 和 result
  profile 是否形成单一绑定语义。
- 补齐缺失的通用字段、输入/输出 profile 和事实缺口投影；未知或冲突绑定 fail closed。
- 不修改 Runtime 主循环，不把 tool name 变成操作语义。

## B：通用 GIS 空间算子

- 以现有 adapter、GDAL/GeoPandas/Shapely/rasterio 和 ToolRegistry 为边界，逐项确认并
  闭合 clip、buffer、intersect、distance 等通用算子的 schema、参数、CRS 和结果 profile。
- 统一空间输入不完整、CRS 不一致、空结果和数据不可用的结构化状态。
- 只使用数据目录和请求事实决定区域、距离和数据集，不增加固定区域分支。

## C：Economic Domain 真实数据闭合

- 审计真实指标目录、时间范围、区域粒度、来源证据和数据 freshness；补齐 query、trend、
  compare、evidence 的 Domain-owned workflow 和 capability 声明。
- 对指标、区域、时间或来源缺失返回结构化澄清/不可用；禁止根据数据不足生成结论。
- 结果统一输出 metrics/timeseries/document_evidence profile，不另建经济专用 Result 协议。

## D：跨域 Planner 与执行闭合

- 让 Rule/Replay/LLM 使用同一 operation-aware capability selection、canonical plan、
  TaskPlan/DAG、ToolRegistry、workflow 和 execution binding。
- 覆盖多步骤依赖、跨结果引用、非执行能力、非法结果类型、局部失败和可恢复动作。
- 只允许模型选择目录中已声明能力；有限 repair 不超过既有公共边界。

## E：动态结果消费者

- 对照 vector、raster、metrics、timeseries、document_evidence 和 composite 的 View、
  Artifact、Evidence、前端投影字段；新增 profile 不得要求领域页面分支。
- 确认跨入口的回答、结果类型、证据和视图 identity；大型空间结果继续通过 artifact 引用，
  不把全部原始数据塞入 planner 或聊天响应。

## F：阶段验收与交付

- 重建 Docker，集中执行 M312 契约、必要 M311/M310 相邻回归、compileall、architecture
  strict、Node projection、Service/readiness、真实 GIS/Economic 和跨入口验收。
- 离线门禁通过后最多调用一次真实模型；只记录脱敏 receipt。
- 更新中文问题日志、milestones、工作快照、任务账本，提交并推送阶段版本；随后从项目
  全局规划下一阶段。React 与 ReAct 继续作为独立候选阶段。

## 依赖与风险

`A → B/C → D → E → F`。B 与 C 在逻辑上可并行，但当前 Goal 规定串行实施。

- 真实数据字段变化：以数据目录和来源证据为准，返回不可用而不是静默适配。
- GIS 库能力差异：优先使用已有 adapter；若缺依赖，先记录并暂停于“需要确认”的边界。
- Provider 输出不稳定：保持结构化 schema、有限 repair 和 fail-closed，不用 Rule 伪装 live 成功。
