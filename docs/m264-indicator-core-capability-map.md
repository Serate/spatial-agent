# M264 指标分析公共能力图

## 模块边界

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| indicator-core | 对已规范化的数值观测执行目录、latest/trend/compare、期间筛选、统计和来源投影 | 公共 `data_profile` 契约 |
| economic-adapter | 读取真实经济数据、校验来源字段并把领域状态映射到 indicator-core | indicator-core、经济数据源 |
| indicators-adapter | 读取现有指标数据并保持 demo fixture 的兼容行为 | indicator-core、指标数据源 |
| indicator-acceptance | 比较两个 Domain 的结果形态、来源和失败状态 | 两个 adapter、公共 Runtime |

构建顺序：

`indicator-core → economic-adapter / indicators-adapter → indicator-acceptance`

## 设计结论

`indicator-core` 是领域中立的深模块。调用方只需要提供规范化观测、数据集 ID、来源摘要和结果命名策略；期间排序、区域筛选、latest/trend/compare、统计汇总和来源去重隐藏在模块内部。

经济术语、指标别名、真实数据路径、字段完整性和不可用状态仍由 Economic adapter 拥有；指标 Domain 的 demo 来源和旧 ToolError 语义仍由 Indicators adapter 拥有。公共 Runtime、Planner、ToolRegistry、HTTP 和前端不感知该模块的领域实现。
