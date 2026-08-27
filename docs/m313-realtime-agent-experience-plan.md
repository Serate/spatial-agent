# M313 实时 Agent 交互与可观测执行实施计划

按完整能力切片串行实施；测试只在改变风险边界或阶段收口时运行，实际代码修改优先。

## A：RunEvent 契约与事件账本（已完成）

- 新增领域中立 `run_events.py`，定义 schema、phase/kind allowlist、脱敏消息、游标和
  有界 data。
- 为内存和 SQLite 增加 append/list 适配，保证同一 run 的 sequence 单调递增；旧数据库
  自动迁移，不影响现有 async_jobs 和 agent_runs。
- 测试只覆盖事件字段、游标、SQLite 重启和敏感字段过滤。

## B：Runtime 生命周期事件（已完成）

- 给 Runtime 注入事件 sink，由生命周期真实阶段发出 started/progress/completed/failed
  事件；工具执行复用现有 StepExecutionHooks，不复制一套执行状态机。
- 异步提交、worker、取消、超时、重试和恢复补充事件，但事件账本不能改变结果状态机。
- 事件和现有 trace/evidence 分离：trace 继续作为最终证据，RunEvent 负责实时通知。

## C：HTTP SSE 与 polling fallback（已完成）

- 在共享 application read seam 增加 `run_events` 语义读取；FastAPI 提供 SSE 长连接，
  参数和 header 都归一化为 `after` 游标。
- 先保证终态和历史事件可回放，再处理心跳；客户端断线可从最后 ID 继续，异常时回退
  现有 `/runs/{id}` polling。
- stdlib 入口只在不复制语义的前提下接入，无法长连接时返回明确的 polling fallback。

## D：Console 实时状态体验（已完成）

- 新增独立事件消费模块或最小 seam，不把 SSE 解析散落到对话提交逻辑。
- 提交后即时显示“已接收/排队/规划/执行/汇总”，展示当前安全动作、耗时、心跳、重试、
  取消和恢复；真实事件到达才推进状态。
- 增加默认收起的分析过程摘要，显示结构化计划摘要和证据引用；最终结果仍由现有
  Result/View/Evidence renderer 消费。
- 验收：Node 事件消费者 smoke 通过；真实持久运行的浏览器验收确认动态结果类型、
  map 视图、轨迹和错误状态均正确展示。

## E：答案增量输出（已完成）

- 在答案生成适配器增加可选 delta callback/iterator；先校验结构化答案边界，再发出
  `answer_delta`，最终事件携带完整答案 fingerprint/长度而不保存原始模型响应。
- 前端将 delta 合并到答案区域，完成后用完整 Result 重新归一化；不支持流式的 provider
  走现有完整答案路径。
- 不展示模型隐藏思维链，只展示可审计摘要。
- 验收：Docker 答案流契约通过；真实模型 + 本地 GIS 运行产生 `live_model`、
  `answer_streaming=true`，Domain SSE 产生 81 个事件，其中 51 个 `answer_delta`。

## F：阶段验收、文档与交付（已完成）

- Docker 集中运行 M313 契约、compileall、architecture strict、Node/browser smoke、
  readiness 和重启事件读取。
- 真实 GIS + 真实模型最多显式一次；验证多阶段事件、终态 Result/Evidence/artifact
  identity，失败也按真实状态记录。
- 更新中文问题日志、milestone、`docs/agent-work-state.md`、`tasks/task-progress.md`、
  `tasks/task-state.md` 和 `tasks/todo.md`，提交推送后按项目全局规划下一阶段。
- 验收：Docker 生产验收通过；服务重启后 `Last-Event-ID: 1` 从第 2 个事件恢复；
  readiness 为 200；compileall、architecture strict 和结果投影 smoke 通过。

## 依赖与风险

`A → B → C → D → E → F`。

- SSE 连接可能被代理缓冲：发送注释/heartbeat，且保留 polling fallback。
- 多 worker 并发写事件：SQLite 使用事务和唯一 `(run_id, sequence)` 边界，冲突重试有限。
- 旧运行没有事件：读取返回结构化 `history_unavailable`，不伪造历史阶段；新运行从提交
  开始记录。
- Provider 不支持 token 流：阶段事件仍可用，最终答案一次性返回并标记 fallback。
- 事件不能替代 Result/Evidence：任何展示结论仍以最终结构化结果为准。
