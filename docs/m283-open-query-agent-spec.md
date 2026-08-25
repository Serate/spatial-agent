# Spec: M283 开放式请求 Agent 闭环

## Objective

让一个未预定义的空间/指标复合问题可以从自然语言进入 M282 v2 context，经过 Rule/Replay/LLM Planner 生成受校验的 Composite Plan，进入既有可恢复生命周期，并在 HTTP、异步、artifact 和前端得到一致的用户结果。

## User-visible behavior

- context 完整：展示已识别对象、候选能力、数据就绪和计划摘要。
- context 缺失：返回结构化澄清，说明缺什么、为什么需要，不创建 run。
- 计划非法或 Provider 输出漂移：结构化拒绝或有限 repair，不绕过 allowlist。
- 计划合法：进入 M278 execution，沿用 M281 View/Evidence；结果回答应先给结论，再提供可展开详情。
- 数据缺失、未对齐或后端不可用：明确降级原因和可恢复动作，不生成无依据结论。

## Reused contracts

- `spatial-agent.composite-request-context.v2`
- `spatial-agent.composite-planning-response.v1`
- `spatial-agent.composite-request.v1`
- `spatial-agent.composite-view.v1`
- M278 Composite run/result/evidence/artifact/SQLite lifecycle

规划证据只以有界 `planner_evidence` 投影进入 Composite result/evidence/artifact；完整 v2 context 不进入执行请求或持久化结果。

本阶段不新增新的核心 Result 或 Runtime 生命周期版本；若确实需要新字段，先更新 Spec 再实现。

## Planner gateway contract

1. 输入只来自有界 v2 context 和用户请求摘要。
2. 输出必须经过 documented provider normalization、canonical plan normalize、Domain/Capability allowlist、DAG 校验和 repair budget。
3. Rule、Replay、LLM 三种来源必须产生同一 canonical response shape。
4. 失败分类至少区分 `context_invalid`、`provider_failed`、`plan_response_invalid`、`capability_unavailable` 和 `execution_failed`。
5. 任何失败都不得返回 prompt、模型原文、密钥、私有路径或完整原始数据。

## Acceptance matrix

| 路径 | 最小证据 |
|---|---|
| fake/replay success | context fingerprint、合法 plan、组件 allowlist、无敏感泄漏 |
| clarification/rejection | 状态、reason code、缺失字段、无 run |
| Rule/LLM parity | context schema/fingerprint、canonical plan/result contract 一致 |
| HTTP/stdlib/FastAPI | 同一 semantic application 和核心状态/evidence |
| async/artifact/restart | 同一 run identity、result/view/evidence 可恢复 |
| real model + Docker GIS | provider/plan/execution 分层 receipt；成功或安全失败均可解释 |
| browser | 阶段里程碑、结论优先、动态结果展示，无思维链 |

## Non-goals

- RAG、联网搜索、自动下载或自动生成工具。
- 为经济、GIS 或某个区域增加固定流程。
- 通过扩大 token/响应预算掩盖 Provider schema 不稳定。
