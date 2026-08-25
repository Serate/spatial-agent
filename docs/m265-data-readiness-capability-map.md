# M265 数据就绪事实能力图

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| dataset-evidence-projection | 将 Domain-owned 数据目录/健康摘要投影为有界 Planner 事实 | DatasetCatalog、公共 capability catalog |
| planner-readiness-context | 把选中能力所需数据的状态、覆盖、CRS、分辨率和对齐摘要放进模型上下文 | dataset-evidence-projection、ContextBuilder |
| readiness-acceptance | 验证目录、Planner context、Result evidence 和既有执行门禁一致 | 前两者、GIS/经济 Domain |

构建顺序：

`dataset-evidence-projection → planner-readiness-context → readiness-acceptance`

本阶段不新增领域，不改变工具数量，也不让 Planner 直接读取文件路径或替代执行前置校验。
