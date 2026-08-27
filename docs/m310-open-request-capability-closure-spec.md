# Spec：M310 开放请求能力选择与数据语义闭合

## Objective

让开放式请求从自然语言到可执行组件计划的边界更稳定：每个组件都能说明需要哪些事实、事实是否缺失或歧义、选中的 capability 是否有匹配 workflow，以及 TaskPlan preview 为什么接受、澄清或拒绝。系统要让用户感受到 Agent 在理解和组合能力，而不是看到内部异常或固定问句分支。

## Success Criteria

1. 同一套公共事实需求契约可以表达实体、数据集、约束的 `any/all/one` 语义，并在 discovery、handoff、Domain workflow 和澄清投影中保持一致。
2. 模型选中已登记 capability 后，组件 request 能通过 Domain resolver 形成匹配 workflow；缺失或歧义事实在执行前结构化返回，不能落成 `preview_failed`。
3. capability、workflow、TaskPlan/DAG、ToolRegistry 和 execution binding 的身份不漂移；任何失败都不创建未经验证的 execution run。
4. 数据 readiness、字段/CRS/时间范围不匹配和来源不可用能分别表达为可恢复状态，不生成无依据结论。
5. CLI、HTTP、异步、前端 View、artifact 和 restart 对同一请求保留一致的事实、结果、答案和 evidence identity。
6. Docker 精简门禁通过，并在 live 预算允许时完成一次显式真实模型验收；若 provider 不稳定，记录有界失败及其阶段，不用 Replay 冒充 live 成功。

## Non-goals

- 不为洪山区、某个固定问句或单一数据集增加流程分支。
- 不引入 RAG、自由联网数据、模型自创工具或第二套执行授权。
- 不把模型原文、prompt、密钥、私有路径或完整原始数据放入公开结果。

## Public contract expectations

- `RequestFacts`：实体、任务、数据集、约束、证据来源和 schema version。
- capability requirements：声明字段 kind、来源、可选值和基数模式；未知模式安全降级。
- component handoff：保留 request fingerprint、component/capability identity、已知事实、有效约束、缺失/歧义字段和 continuation。
- planner evidence：区分 provider completed、semantic clarification、rejected、preview failure 和 execution failure。

## Verification policy

开发中只运行新增契约和必要静态检查；阶段收口集中运行 Docker 精简契约、跨入口 acceptance、compileall、architecture strict、Node projection、Service smoke、HTTP/readiness 和最多一次显式 live。
