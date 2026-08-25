# Spec：M296 通用能力可执行闭合与真实跨域成功链路

## Objective

在 M295 discovery receipt 之上，建立一个领域中立的 execution-readiness 语义，使已发现的能力只有在 workflow、ToolRegistry、TaskPlan、DAG 和结果契约完整闭合时才进入执行；使用真实 Docker 数据完成至少一条跨域成功或可解释降级链路。

## Public contracts

1. `spatial-agent.analysis-discovery.v1` 继续作为能力/数据发现入口；如需新增字段，必须保持向后兼容并记录 receipt fingerprint。
2. execution readiness 必须是 bounded、版本化、可脱敏的投影，至少区分 `ready`、`needs_facts`、`data_unavailable`、`capability_unavailable`、`workflow_unbound` 和 `schema_invalid`。
3. 只有 readiness 为 `ready` 且 `execution_ready=true` 的 candidate 才能进入 TaskPlan bridge；计划仍必须通过 canonical TaskPlan、DAG、completeness 和 M294 execution binding。
4. Rule、Replay、LLM 的候选身份、数据需求、workflow、工具和结果类型必须来自同一个 catalog/context，不允许 provider 自行发明。
5. Result、View、Evidence、Artifact、SQLite/restart 和 HTTP/CLI/前端必须保留同一 request/discovery/plan/binding identity。

## Acceptance criteria

1. 一个事实完整的 GIS + Economic 开放请求能够经过 discovery、execution readiness、validated TaskPlan、execution binding 和实际 Docker 执行，或返回明确的结构化不可用原因。
2. 一个未写入固定问句的能力组合能够由 Rule/Replay 或真实 LLM 从 catalog 中选择，不修改公共 Runtime 和前端主流程。
3. workflow 未注册、ToolRegistry schema 缺失、result type 不匹配、数据 readiness unknown/unavailable 和用户事实不足分别返回稳定 reason code。
4. 同一计划在同步、异步、artifact、SQLite/restart 和 HTTP/前端 View 中保持结果、证据和 binding identity 一致。
5. 前端只通过通用结构化 projection 显示准备状态、执行状态、结论、限制和证据，不新增 GIS/Economic 分支。
6. Docker 阶段收口通过精简 contract、相邻回归、compileall、architecture strict、readiness 和必要 HTTP/Node；真实模型只作为显式验收，不进入默认 CI。

## Boundaries

- Always：先使用 discovery receipt，再做 execution readiness，再创建 canonical plan 和 binding。
- Ask first：修改已有 receipt/result/artifact schema 版本、扩大工具权限、引入新外部数据源或改变 production binding policy。
- Never：为单一区域、单一指标、固定自然语言表达增加流程分支；不能用模型原文替代 evidence；不能把 `unknown` readiness 当作 `ready`。

## Failure semantics

- `needs_facts`：能力和 workflow 存在，但公共事实不完整，产生 continuation。
- `data_unavailable`：能力存在，但数据覆盖、后端或 readiness 不满足。
- `workflow_unbound`：能力目录可见，但没有合法 workflow，不能物化计划。
- `schema_invalid`：工具、TaskPlan、DAG 或结果类型契约不闭合，安全拒绝。
- `execution_binding_invalid`：计划在最终绑定时发生 identity/drift，拒绝创建或接管 run。
