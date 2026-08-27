# M312 通用分析算子与跨域真实能力闭合能力图

## 目标

在 M311 的分析意图契约之上，把有限的通用操作真正闭合到已注册能力、数据和
Result Contract，使 GIS 与 Economic 能够共享同一套 Planner/Runtime 链路。重点是
扩大“可组合能力面”，而不是为某个区域、某个问句或某个数据集增加流程分支。

## 能力模块

| 模块 id | 职责 | 依赖 |
|---|---|---|
| operation-binding | 将 query/filter/aggregate/trend/compare/spatial_operation/evidence 与 capability、result profile、事实缺口对齐 | M311 analysis-intent |
| generic-spatial-operators | 通过现有 GIS adapter 和 ToolRegistry 闭合 clip、buffer、intersect、distance 等通用空间算子 | operation-binding |
| economic-domain-pack | 使用可追溯真实指标数据闭合 query、trend、compare、evidence；数据不足时结构化澄清 | operation-binding |
| cross-domain-planning | 让 Planner 在 GIS、Economic 等 Domain 之间组合合法组件、依赖和结果类型 | generic-spatial-operators, economic-domain-pack |
| dynamic-result-consumers | 验证 View、Artifact、Evidence 和前端按 data profile/Result 类型消费，不按工具或领域分支 | cross-domain-planning |
| acceptance-delivery | 完成 Docker、真实数据、跨入口、恢复和一次 live 模型验收并交付阶段版本 | dynamic-result-consumers |

## 构建顺序

`operation-binding → generic-spatial-operators → economic-domain-pack → cross-domain-planning → dynamic-result-consumers → acceptance-delivery`

当前 Goal 约束为串行实施；并行化只作为未来效率优化，不在本阶段改变任务顺序。

## 全局边界

- 公共 Runtime、Planner、TaskPlan/DAG、ToolRegistry 和生命周期仍是唯一执行权威。
- Domain Pack 负责领域数据、字段、workflow 和能力声明；公共层不携带 GIS 或经济策略。
- 优先复用 Docker 中已有的 rasterio、GDAL/PROJ、GeoPandas、Shapely 和现有适配器；
  新增依赖或改变部署方式先暂停确认。
- 不以洪山区、固定表达或单个文件名作为能力分支；区域、时间、字段和数据源都是
  请求事实或数据目录信息。
- ReAct 和 React 前端迁移不属于 M312 的必要实现，分别作为后续独立阶段候选。
