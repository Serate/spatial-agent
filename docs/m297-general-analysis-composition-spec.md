# Spec：M297 通用分析组合与跨类型结果闭合

## Objective

在 M296 的 execution-ready 能力闭合之上，支持开放式请求从能力目录中组合多个已登记能力，安全地连接不同数据形态，生成可执行的 canonical TaskPlan，并在统一结果和证据边界中完成展示与恢复。

## Public contracts

1. 能力目录条目必须能表达公共 requirements、输入 data profile、输出 data profile、workflow、允许工具、result type 和 evidence 选项。
2. Planner 的组合输出必须引用 catalog 中的 capability/workflow，步骤依赖只能使用已声明且类型兼容的 `result_ref` 或公共事实。
3. 计划校验顺序保持为 discovery → execution readiness → TaskPlan/DAG/completeness → execution binding；不得另建组合执行循环。
4. Composite Result/View/Evidence 只保存 bounded 的结论、类型、来源摘要、限制、引用和 identity；模型原文、prompt、token 和私有路径不得进入公开投影。
5. 跨入口恢复必须重建同一 canonical plan、binding 和结果类型；类型或来源漂移时 fail closed 并保留可读 reason code。

## Acceptance criteria

1. 至少一个不依赖固定问句的开放请求可以从 catalog 选择两个以上能力，生成合法 DAG，并通过现有 binding 进入执行或结构化澄清。
2. GIS 与 Economic 的组合可以同时产生至少两种 data profile，并在同步、异步、artifact、SQLite/restart 和 HTTP View 中保持一致。
3. 对未知能力、未注册 workflow、工具 schema 缺失、输入/输出类型不兼容、数据时间/空间范围不匹配分别返回稳定的结构化状态。
4. 新增一个目录能力或 workflow 时，不修改公共 Runtime 主循环和前端领域分支；只需完成声明、注册和 Domain adapter 接口。
5. Console 能按结构化结果动态显示结论、指标/时间序列、空间视图、来源和限制；未知结果类型仍有安全通用降级展示。
6. Docker 阶段门禁通过精简 contract、相邻回归、compileall、architecture strict、readiness 和一次显式真实模型/真实 GIS 验收；默认 CI 不访问网络或私有数据。

## Failure semantics

- `needs_facts`：组合所需区域、时间、指标或约束不足，返回有界 continuation。
- `data_unavailable`：数据目录或后端无法满足覆盖、字段、时间或空间条件。
- `composition_invalid`：能力、workflow、引用或 data profile 无法组成合法计划。
- `schema_invalid`：Planner、工具、DAG 或结果契约不闭合，安全拒绝。
- `execution_binding_invalid`：最终执行绑定发现计划、来源、工具或结果类型漂移，拒绝创建/接管 run。

## Non-goals

- 不允许模型自由发明工具、数据集、指标或空间操作。
- 不通过专用问句匹配、扩大 repair 次数或放宽 schema 提高成功率。
- 不把数据下载、RAG 或外部知识检索混入本阶段。
