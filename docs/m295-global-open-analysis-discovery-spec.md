# Spec：M295 全局开放式分析与数据发现闭环

## Objective

让开放式问题先经过领域中立的能力/数据发现，再进入已经验证的 TaskPlan/DAG 和 execution binding；信息不足时返回可恢复澄清，数据不可用时返回结构化降级，不依赖固定问句分支。

## Public contracts

1. 新增版本化 discovery receipt（建议 `spatial-agent.analysis-discovery.v1`），包含 request fingerprint、候选能力、数据需求、readiness、来源和缺失事实的有界摘要。
2. discovery receipt 不携带 prompt、模型原文、凭据、完整路径或原始私有数据；可从其 projection 恢复同一澄清 identity。
3. Planner 只能选择 catalog 中 `available` 且有合法 workflow 的能力；缺失事实或数据时进入统一 clarification/fail-closed 状态。
4. 通过 discovery 的候选仍必须经过 TaskPlan schema、DAG、completeness 和 execution-binding 校验；discovery 不是执行授权。
5. Result/View/Evidence/Artifact/SQLite/restart 只引用同一 request/discovery/plan/binding identity。
6. Rule、Replay 和 LLM 使用同一结构化边界；Provider 失败不改变 capability allowlist。

## Acceptance criteria

1. 未预定义的 GIS + Economic 开放问题能够得到结构化能力/数据需求和澄清，而不是固定字符串拒绝。
2. 数据完整时，至少一个跨领域请求可以从 discovery 进入 validated TaskPlan、execution binding、实际执行和结果投影。
3. 数据集缺失、字段不匹配、时间/空间覆盖不足和 Domain 后端不可用能区分为稳定 reason code，并可恢复或明确结束。
4. CLI、HTTP、异步、前端、artifact 和 restart 对同一请求保留一致 discovery/request/plan/binding fingerprint。
5. 前端不新增 GIS/Economic 专用分支，能够显示 discovery 状态、关键结果和限制。
6. Docker 中通过一组精简 contract、compileall、architecture、readiness，并执行一次显式真实模型或真实 GIS 验收；默认 CI 不依赖私有数据或 live provider。

## Boundaries

- Always：先发现能力/数据，再规划；所有可执行步骤经过统一工具和计划门禁。
- Ask first：修改现有公共 Result/Artifact schema 版本、改变 Domain 选择权限或引入新的外部数据源。
- Never：为单一区域、单一指标、固定表达添加 `if/elif` 流程；不能把 catalog 命中当成数据事实；不能用模型文本替代 evidence。

## Failure semantics

- `needs_facts`：能力存在但必要事实不足，产生 continuation。
- `data_unavailable`：能力存在但数据/后端不可用，保留 readiness 和恢复建议。
- `capability_unavailable`：没有可执行能力，结构化拒绝并列出有限候选。
- `discovery_invalid`：发现 receipt 或模型输出不合规，有限 repair 或拒绝。
