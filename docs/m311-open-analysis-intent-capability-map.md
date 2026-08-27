# M311 通用分析意图与跨域开放链路能力图

## 目标

让开放式问题先被归一化为领域中立的分析意图，再由 Capability Catalog、数据目录和
Domain resolver 闭合为可执行计划。GIS、经济和后续 Domain 共享同一套操作语义；Domain
只负责自己的数据、字段和 workflow，不在 Runtime 中增加专题分支。

## 能力模块

| 模块 id | 职责 | 依赖 |
|---|---|---|
| analysis-intent | 归一化查询、筛选、聚合、趋势、比较、空间操作和来源证据等有限操作语义 | — |
| capability-binding | 将意图与能力、数据集、结果类型、事实需求和 Domain workflow 对齐 | analysis-intent |
| plan-closure | 将已绑定能力闭合为 canonical plan、TaskPlan/DAG 和 execution binding | capability-binding |
| cross-domain-acceptance | 用 GIS 与 Economic 的开放请求验证同一意图契约和跨入口结果一致性 | analysis-intent, capability-binding, plan-closure |
| result-projection | 按 Result/View/Evidence 动态呈现操作结果、澄清、限制和来源 | plan-closure |

## 构建顺序

`analysis-intent → capability-binding → plan-closure → cross-domain-acceptance → result-projection`

## 边界

- 意图是有限、可版本化的语义标签，不是模型自由生成的工具名。
- LLM 只能从目录提供的操作、能力、数据集和结果类型中选择；未知或冲突信息进入澄清。
- 不为洪山区、经济专题、固定问句或单个数据集增加分支。
- 不改变 Runtime 生命周期、ToolRegistry 的授权、TaskPlan/DAG 或 execution binding 门禁。
