# M309 真实模型开放组合与默认 Agent 体验能力图

## 目标

在 M308 已验证的 3+ 组件执行闭环之上，验证真实模型能否稳定把开放请求转换为受控的多步计划，并让默认产品路径把 Agent 的发现、规划、执行、汇总和可恢复动作清楚地呈现给用户。真实模型只能选择已经登记、已经校验且具备数据就绪状态的能力；GIS、Economic 和 Indicators 继续只是可替换的 Domain Pack。

## 能力模块

| 模块 ID | 责任 | 依赖 |
|---|---|---|
| model-plan-acceptance | 建立 provider-backed 成功、澄清、非法计划、修复、超时和拒绝矩阵，冻结 run 创建边界 | — |
| bounded-plan-repair | 让模型输出经过 envelope、schema、catalog、TaskPlan/DAG、ToolRegistry、workflow 和 execution binding 的有限修复与 fail-closed 校验 | model-plan-acceptance |
| default-agent-surface | 让默认模型路径、阶段状态、可读答案和下一步动作消费同一结构化 evidence；详细轨迹保持渐进展开 | model-plan-acceptance |
| cross-entry-recovery | 对照同步、异步、HTTP、View、artifact、SQLite/restart 的计划、结果、答案和 evidence identity | bounded-plan-repair, default-agent-surface |
| docker-live-release | 使用 Docker 完成精简阶段门禁和一次显式真实模型验收，更新文档并交付版本 | model-plan-acceptance, bounded-plan-repair, default-agent-surface, cross-entry-recovery |

## 构建顺序

`model-plan-acceptance → bounded-plan-repair → default-agent-surface → cross-entry-recovery → docker-live-release`

## 不在本阶段

- 不为固定区域、固定问句或某个专题增加专用流程、工具或前端分支。
- 不引入 RAG、联网搜索、自由下载或模型自定义工具；模型只能从 Capability Catalog 选择能力。
- 不放宽 schema、TaskPlan、DAG、ToolRegistry、workflow、execution binding 或数据 readiness 门禁。
- 不展示模型原文、prompt、内部思维链、密钥、完整原始数据或私有路径。
