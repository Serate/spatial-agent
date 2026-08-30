# Spec：M332 真实模型复杂任务有界执行与增量反馈

## Objective

复杂真实模型请求在规划、工具执行和答案生成期间必须有明确预算、真实心跳和可恢复结果。用户可以看到当前阶段与等待时长，但不能看到未校验的模型输出、Prompt 或隐藏思维链。

## Interfaces

- 新增版本化 `spatial-agent.run-budget.v1`，描述总预算、阶段预算、尝试、剩余时间和预算状态。
- 扩展现有 `spatial-agent.run-event.v1`，增加阶段耗时、剩余预算、尝试和恢复信息；增加重试、恢复和超时事件。
- Provider 结构化调用和答案流接收有界 timeout、当前 deadline 与安全进度回调。
- 现有 `timeout_seconds`、ToolRegistry timeout、SSE `Last-Event-ID`、轮询和恢复入口保持兼容。

## Behaviour

- 总预算限制整个 Run；规划/ReAct、工具执行、答案生成拥有独立预算，子预算不能超过总预算剩余时间。
- provider 重试和退避计入阶段预算；部分 JSON、计划和工具参数永不进入前端或执行链路。
- 长调用期间按配置发送 heartbeat；heartbeat 只包含阶段、耗时、预算、尝试次数和安全状态。
- 规划超时、工具超时、答案超时和总超时使用稳定错误码及有限恢复动作。
- 异步 reaper 可立即终结超时 Run；迟到 worker 不得把终态写回为成功、取消或旧结果。
- 恢复必须保留 Run identity、已完成步骤、结果引用和 repair/recovery lineage。

## Project Structure

- Runtime 深模块：`agent/runtime_core/`
- Provider 适配：`agent/integration/` 与 `agent/llm_planner.py`
- 持久化与异步：`agent/application/`、`agent/persistence/`
- 前端事件投影：`web/src/`
- 阶段测试：`tests/` 与 Docker smoke/acceptance 脚本

## Testing Strategy

- 默认 Docker 离线紧凑契约测试：预算、心跳、超时分类、终态隔离、SSE 续传和前端 projection。
- 只对受影响的 Runtime、provider、持久化和前端 smoke 做阶段合并验证。
- 真实模型 + Docker/GIS 作为显式验收，不进入默认 CI。

## Boundaries

- Always：先校验 Schema、权限、结果 owner 和事件安全字段；保存脱敏 receipt；更新交接文档。
- Ask first：新增第三方依赖、破坏现有公共事件版本、改变默认模型权限或修改 CI 策略。
- Never：保存密钥、Prompt、模型原文、隐藏思维链、网页正文或未经校验的计划；不使用线程强杀任意 Python 工具。

## Success Criteria

- 阻塞 provider 期间持续收到真实 heartbeat，并能显示阶段耗时。
- 阶段预算耗尽后在有界时间内得到结构化、可恢复的终态。
- 迟到 worker 不能覆盖超时终态。
- 重试、重启、SSE 断线续传和 Artifact 保持结果及 evidence 一致。
- 答案 delta 继续实时到达，结构化计划仍只在完整校验后展示。

## Assumptions

- 单 Agent、最大并发度 1，默认使用 Docker。
- 保持 `run-event.v1` 做兼容扩展，不升级破坏性 v2。
- 无法安全强杀任意线程；provider socket timeout 与沙箱进程 timeout 是硬边界。
