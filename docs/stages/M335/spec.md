# Spec：M335 通用多工具执行与 Provider 健康

## Objective

让开放式请求在真实模型、工具或网络不稳定时仍能给出可解释、可恢复的结果；正常情况下支持多个已注册工具的连续组合，并在前端持续展示真实阶段进展。

## Public contracts

### Provider Health

新增或扩展版本化安全投影，至少包含：`schema_version`、`provider_id`、`status`、`attempt_count`、`elapsed_ms`（可分桶）、`reason_code`、`retryable` 和 `observed_at`。禁止包含原始异常、请求头、Prompt、模型原文和密钥。

### ReAct composition

每轮动作必须先通过现有决策适配器、ToolRegistry schema、权限、Execution Policy 和预算校验；工具结果进入安全 history 后，模型只能基于结果决定继续、澄清、降级或完成。重复动作、循环和工具数量必须有界。

### Result closure

多工具结果沿用 Result Registry、Evidence Bundle 和 Composite 对齐契约。无法对齐的范围、时间、单位、CRS 或版本必须成为 limitation；子结果失败时父结果只能是 partial/degraded，不得声称全部完成。

## Non-goals

- 不开放任意 Python、任意网络、任意模型生成代码的自动上线。
- 不引入 RAG、网页正文持久化或领域专用回答模板。
- 不为某个地区、数据集或固定问句增加硬编码路径。

## Testing

- 默认只运行受影响的 Provider/ReAct/Result 紧凑契约和必要 smoke。
- 用 fake Provider 覆盖超时、重试、结构化响应无效、网络不可用、部分成功和循环阻断。
- Docker 阶段门禁覆盖 readiness、SQLite/Artifact/SSE 恢复和跨入口结果一致性。
- 真实模型 + 本地 GIS + `public` 网页只执行一次有界显式验收，记录脱敏状态和 reason code。

## Acceptance criteria

1. 一个至少包含两个不同能力的开放请求能在受控 ReAct 下连续执行或结构化降级。
2. Provider 超时、网页不可达和工具失败可区分，并保留可恢复的阶段事件与 evidence。
3. 多结果组合保持 source identity、quality、alignment 和 partial 语义。
4. CLI、HTTP、SSE、Artifact、SQLite 恢复和前端消费同一核心结果契约。
5. Docker/真实模型验收不泄漏模型原文、Prompt、网页正文或密钥。
