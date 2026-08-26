# Spec：M305 Provider-backed 成功率与可恢复交互

## 目标

在现有 Agent Runtime 和 Composite 执行闭合不变的前提下，降低 provider-backed 规划因上下文、输出格式、期限或交互投影造成的失败，提升形成合法 Composite 计划的可观测成功率。

## 公共契约

1. `ProviderRuntimeEvidence` 继续作为 provider health、structured-output、deadline 和错误分类的唯一安全来源。
2. `PlannerAttemptReceipt` 记录阶段、预算、尝试数、结果类别和下一步动作；不记录 prompt、模型原文、URL 或密钥。
3. `CanonicalPlanReceipt` 只在计划通过能力目录、DAG、TaskPlan、workflow、ToolRegistry 和 execution binding 后标记为可执行。
4. `RecoveryAction` 统一表达“补充信息”“稍后重试”“检查模型配置”“查看已完成结果”等用户动作。
5. `PlannerAttemptReceipt` 使用 `spatial-agent.planner-attempt.v1`，是 planner/provider attempt 的唯一安全统计边界；同一 receipt 可被 Composite View、HTTP 和 Console 投影。

## 行为要求

- provider 请求必须使用当前阶段最小 Envelope，并有显式的 provider/harness deadline 与 max output 上限。
- 每次 provider-backed planner 调用必须产生有限的 attempt receipt；receipt 至少区分阶段、状态、结果类别、attempt/retry、耗时和请求预算，不携带敏感输入或输出。
- 合法模型响应先规范化，再进入现有 Composite canonical adapter；未知字段、未知能力、非法依赖和未闭合 workflow 必须 fail closed。
- 结构性响应错误最多触发一次 repair；repair 不得改变事实、能力、领域、权限、工具参数或执行结果。
- provider timeout、配置错误、非法模型响应、事实澄清、计划拒绝和执行失败必须保持不同的状态/错误码/证据平面。
- 同步、异步、HTTP、artifact、SQLite/restart 和 Console 对相同请求必须保持核心状态、结果类型、证据身份和用户动作一致。

## 验收矩阵

| 场景 | 预期 | 是否创建 execution run |
| --- | --- | --- |
| replay 合法多步计划 | 进入既有执行闭合并保留 canonical receipt | 是 |
| provider 返回合法计划 | 通过完整门禁后进入执行 | 是 |
| provider timeout/网络失败 | `FAILED`，provider evidence，可重试或检查配置 | 否 |
| 模型结构错误 | 最多一次 repair，失败则 `REJECTED` | 仅修复成功且重新通过门禁时 |
| 事实不足 | `NEEDS_CLARIFICATION`，列出缺口 | 否 |
| 已创建 run 的工具失败 | 保留 Result/Evidence 和恢复动作 | 是 |

## M305-A 状态动作约束

- `PLANNED` 不是执行成功；只有通过 TaskPlan、ToolRegistry、workflow 和 execution binding 后才允许创建 execution run。
- `NEEDS_CLARIFICATION` 只表示请求事实或组件事实不足，不承载 provider timeout、网络错误或模型格式错误。
- `REJECTED` 表示计划或能力违反公共契约；不得通过自动扩大权限、工具或预算来“修复”。
- `FAILED` 且 `phase=planning` 表示 provider/planner 侧尚未创建 execution run；`FAILED` 且已有 run 表示执行侧失败，二者必须保留不同 evidence。
- 每次 repair 最多一次；超时不得因为 retryable 自动触发新的 live 请求，用户动作只能由上层显式选择。

## 非目标

本阶段不更换模型供应商，不扩大 GIS/Economic 工具数量，不引入 RAG，不把中转可达性误判为模型规划成功，也不在默认 CI 调用真实模型。

## 阶段门禁

Docker 精简契约、相邻 Composite 回归、compileall、architecture strict、Node projection、Service smoke、生产 readiness、真实 Replay/数据验收和一次显式 live 必须分别可报告；live 可成功、澄清或 provider failure，但必须保留脱敏 receipt。
