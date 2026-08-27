# M313 实时 Agent 交互与可观测执行能力图

## 目标

让用户在 Agent 执行期间持续看到真实的阶段进展、工具状态、心跳和最终答案流。
实时展示只消费统一的 `RunEvent`，不新增领域专用页面分支，也不改变 Runtime 的
TaskPlan、DAG、ToolRegistry 和执行授权边界。

## 能力模块

| 模块 id | 职责 | 依赖 |
|---|---|---|
| run-event-contract | 定义版本化、脱敏、可排序、可恢复的 RunEvent 契约 | M312 Result/Trace/Evidence |
| durable-event-ledger | 为内存和 SQLite 提供统一事件追加、游标读取和重启回放 | run-event-contract |
| lifecycle-emission | 在 resolve、clarify、plan、validate、execute、answer、evidence 等真实阶段发出事件 | durable-event-ledger |
| realtime-transport | 提供 SSE、Last-Event-ID、断线续传和 polling fallback | durable-event-ledger |
| live-console | 前端实时消费事件，展示阶段、心跳、工具状态、摘要和最终答案 | realtime-transport |
| answer-stream | 在结构化结果完成且安全校验后，支持真实模型最终答案增量输出 | run-event-contract, live-console |
| acceptance-delivery | Docker、浏览器、重启恢复和一次真实模型验收，并更新交接文档和版本 | 全部模块 |

## 构建顺序

`run-event-contract → durable-event-ledger → lifecycle-emission → realtime-transport → live-console → answer-stream → acceptance-delivery`

本阶段按串行方式实施；测试按阶段合并，避免每个小改动重复运行完整门禁。

## 全局边界

- `RunEvent` 是跨 Runtime、HTTP、CLI、前端和恢复流程的公共事实边界；传输层不自行
  推断阶段或工具状态。
- 事件只包含可审计摘要、稳定 identity、状态、阶段和安全元数据；不包含原始 Prompt、
  模型隐藏思维链、模型原文、密钥、完整错误堆栈或私有路径。
- “分析过程摘要”可以在前端默认收起展示，但内容必须是结构化、脱敏、可验证的计划
  摘要、执行判断和证据引用。
- 最终答案不得在事实未完成时提前生成结论；token 流只适用于已通过结构化校验的答案。
- SSE 断线后以 `Last-Event-ID` 从事件账本续传；事件读取失败时保留现有 polling fallback。
- 内存模式用于离线测试，SQLite/artifact 用于生产恢复；两者输出相同的核心事件字段。
- 不引入 React、ReAct 或新的消息队列作为本阶段前置条件；先利用现有原生 Console、
  SQLite 和 HTTP 边界完成纵向闭环。
