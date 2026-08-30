# Agent 当前工作快照

> 默认恢复：`pwsh -NoProfile -File scripts/resume_context.ps1`。只读取本文件、任务状态、当前阶段 handoff 和当前任务必要文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime。真实模型默认通过受控 ReAct 理解开放问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答；GIS 只是业务载体。

## 当前阶段

- 阶段：`M332` 真实模型复杂任务有界执行与增量反馈
- 当前任务：M332 阶段交付与全局重规划
- 状态：M331-A～F 已完成并推送（`11d7492`）；M332-A～F 已完成，代码和文档待提交
- 基线：`0ce3ba4`
- 协作：单 Agent，最大并发度 1；测试与 GIS 优先使用 Docker

## 阶段入口

- [`docs/stages/M332/capability-map.md`](stages/M332/capability-map.md)
- [`docs/stages/M332/spec.md`](stages/M332/spec.md)
- [`docs/stages/M332/plan.md`](stages/M332/plan.md)
- [`docs/stages/M332/handoff.md`](stages/M332/handoff.md)
- [`tasks/current-state.md`](../tasks/current-state.md)
- [`docs/document-index.json`](document-index.json)

## 当前任务必要文件

- `docs/stages/M332/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/runtime_core/run_budget.py`
- `agent/runtime_core/progress.py`
- `agent/integration/structured_response.py`
- `agent/llm_planner.py`
- `agent/answer_generation.py`
- `agent/runtime.py`
- `agent/runtime_core/run_lifecycle.py`
- `agent/run_events.py`
- `agent/application/async_runs.py`
- `agent/application/service_state.py`
- `agent/persistence/sqlite_store.py`
- `production_api.py`
- `web/src/console_run_events.js`
- `web/src/console_app.js`
- M332 直接相关的紧凑测试
- `tasks/current-state.md`
- `docs/document-index.json`

## 恢复规则

1. 只读取当前快照、`tasks/current-state.md`、M331 handoff 和当前任务列出的文件。
2. 历史账本、完整阶段文档、全量源码、全量测试、模型原文和敏感配置按需读取。
3. 每个子任务开始/完成/暂停时先更新热状态，再追加任务账本；阶段结束后更新 handoff、索引并提交推送。
4. 默认只运行受影响的紧凑测试、必要 smoke 和阶段集成验收。

## 最近完成

- M331-D/E/F：答案质量 receipt、ReAct 事件、答案流、文档交接和阶段版本已完成；复杂真实模型规划延迟被列为 M332 输入。
- M332-D/E/F：Runtime 超时/恢复、异步终态 fence、SSE/轮询/前端实时投影和真实 GIS 验收已完成；ReAct 后续超时不再覆盖先前成功的模型证据。Docker 定向回归 `15/15`、前端 smoke、compileall、architecture strict、服务 smoke、readiness `200` 均通过。

## 当前任务交接

- M332-0：已锁定统一 RunBudget、阶段进度协调器、provider 回调、异步终态隔离和前端事件投影的实现顺序；阶段文档和索引校验通过。
- M332 约束：结构化计划和工具参数完整校验后才能展示或执行；心跳只展示安全阶段事实；不保存模型原文、Prompt、隐藏思维链或密钥。
- M332-A：`run_budget` 深模块已实现，支持总/阶段/provider 单次预算、尝试/重试、剩余时间和安全 receipt；Docker 契约测试 `4/4` 通过。
- M332-B：`progress` 深模块已实现，支持有序阶段事件、heartbeat、恢复提示和安全关闭；RunEvent 已兼容增加超时/取消/重试/恢复与计时字段；Docker 预算/进度测试 `6/6` 通过。
- M332-C：已接入 Provider 结构化调用、compact recovery、ReAct 决策、普通答案与 Composite 答案的动态 timeout/deadline 和安全进度回调；Provider 重试/退避不突破 deadline，结构化结果仍须完整校验。
- M332-C 验证：M331 结构化响应 + M332 预算/进度/Provider 紧凑测试 `17/17` 通过；未调用真实模型。
- M332-D/E 红灯与修复：重建 Docker 后已修复 M37 极短 `0.01s` 超时、M60 Mock factory `event_sink` 参数兼容、M69 极短异步超时类型丢失，以及 SQLite reaper/worker 事件序号竞争。
- M332-D/E 验证：Runtime lifecycle、RunBudget、Progress、Provider、M37、M60、M69、M79 定向回归 `30/30` 通过；新增终态事件 fence 测试通过；未调用真实模型。
- 当前动作：M332 已完成，等待提交并推送阶段版本。
- 下一步：提交后按产品体验、Runtime、Planner、Domain/数据、部署和测试全局重规划下一阶段；恢复时只读取本快照、任务状态、阶段 handoff 和新阶段必要文件。
