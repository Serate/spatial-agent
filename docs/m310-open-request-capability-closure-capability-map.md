# M310 开放请求能力选择与数据语义闭合能力图

## 全局目标

在 M309 已完成的 provider 状态、TaskPlan bridge 和默认 Agent 投影之上，继续提高开放式请求进入合法执行链路的成功率。模型负责从可信能力目录选择能力并拆分目标，Domain 负责解释自己的请求事实和 workflow 约束，公共 Runtime 负责统一校验、执行、恢复和证据发布。

本阶段不把某个数据集或某类问句做成专用流程，也不引入 RAG、自由联网或模型自创工具。

## 七维能力模块

| 模块 | 目标 | 依赖 |
|---|---|---|
| request-fact-closure | 让组件请求的实体、数据集、约束和时间事实有明确来源、缺失与歧义状态 | — |
| capability-selection-closure | 让模型选择与 Domain discovery、catalog readiness、workflow identity 保持一致 | request-fact-closure |
| plan-materialization-closure | 让已选能力稳定物化为 TaskPlan/DAG，并区分澄清、拒绝与预览失败 | capability-selection-closure |
| readiness-evidence-closure | 将数据可用、字段匹配、空间/时间对齐和来源状态接入可执行决策 | request-fact-closure |
| user-agent-surface | 让默认界面展示“理解—计划—执行—结论”，技术细节按需展开 | plan-materialization-closure |
| cross-entry-closure | 对照 CLI/HTTP/async/View/artifact/restart 的核心身份与证据 | plan-materialization-closure, readiness-evidence-closure |
| docker-live-release | Docker 精简门禁、一次显式 live、文档和版本交付 | 全部 |

## 实施顺序

`request-fact-closure → capability-selection-closure → plan-materialization-closure → readiness-evidence-closure → user-agent-surface → cross-entry-closure → docker-live-release`

## 全局边界

- 新增专题能力优先通过 Domain catalog、RequestFacts、tool schema、workflow 和 Result 类型扩展，不修改公共 Runtime 的领域策略。
- 模型只能选择 catalog 中已登记且满足执行 readiness 的能力；模型输出不能携带 workflow、工具实现、路径或权限。
- 事实不足或多个候选都合理时返回结构化澄清；预览异常不得伪装成澄清或执行成功。
- 默认测试保持离线、精简、可重复；真实模型、真实 GIS、Docker 和浏览器只作为显式验收路径。
