# Agent 当前工作快照

> 默认恢复：`pwsh -NoProfile -File scripts/resume_context.ps1`。只读取本文件、任务状态、当前阶段 handoff 和当前任务必要文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime。真实模型默认通过受控 ReAct 理解开放问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答；GIS 只是业务载体。

## 当前阶段

- 阶段：`M334` 多来源证据与跨域组合
- 当前任务：M334-A 来源身份与质量深模块
- 状态：M334-0 已完成，等待实现来源身份与质量
- 基线：`722db01`
- 协作：单 Agent，最大并发度 1；测试与 GIS 优先使用 Docker

## 阶段入口

- [`docs/stages/M334/capability-map.md`](stages/M334/capability-map.md)
- [`docs/stages/M334/spec.md`](stages/M334/spec.md)
- [`docs/stages/M334/plan.md`](stages/M334/plan.md)
- [`docs/stages/M334/handoff.md`](stages/M334/handoff.md)
- [`tasks/current-state.md`](../tasks/current-state.md)
- [`docs/document-index.json`](document-index.json)

## 当前任务必要文件

- `docs/stages/M334/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/evidence/{contract.py,projection.py,registry.py}`
- `agent/network/{web_search.py,web_fetch.py}`
- `agent/application/composite_view.py`
- `agent/result_summary.py`
- `agent/answer_generation.py`
- `agent/runtime_core/react_runtime.py`
- `tests/test_m334_evidence_quality.py`
- `tasks/current-state.md`
- `docs/document-index.json`

## 恢复规则

1. 只读取当前快照、`tasks/current-state.md`、M334 handoff 和当前任务列出的文件。
2. 历史账本、完整阶段文档、全量源码、全量测试、模型原文和敏感配置按需读取。
3. 每个子任务开始/完成/暂停时先更新热状态，再追加任务账本；阶段结束后更新 handoff、索引并提交推送。
4. 默认只运行受影响的紧凑测试、必要 smoke 和阶段集成验收。

## 最近完成

- M331-D/E/F：答案质量 receipt、ReAct 事件、答案流、文档交接和阶段版本已完成；复杂真实模型规划延迟被列为 M332 输入。
- M332-D/E/F：Runtime 超时/恢复、异步终态 fence、SSE/轮询/前端实时投影和真实 GIS 验收已完成；ReAct 后续超时不再覆盖先前成功的模型证据。Docker 定向回归 `15/15`、前端 smoke、compileall、architecture strict、服务 smoke、readiness `200` 均通过。

## M333 已完成决策

- `SPATIAL_AGENT_WEB_MODE` 支持 `off`、`allowlist`、`public`，默认 `allowlist`；现有搜索配置和行为保持兼容。
- `public` 只允许服务端配置的搜索 Provider，以及用户明确提供或当前搜索结果返回的 HTTPS 来源；禁止私网、回环、链路本地、保留地址、IP 字面量、认证信息和危险重定向。
- 不执行 JavaScript，不支持登录页、PDF 和文件下载；响应、正文、重定向次数和来源数量均有上限。
- `web_fetch` 的正文只存在于当前 Run 的内存模型上下文；持久化只允许保存 URL、标题、哈希、长度、状态和原因码等安全投影。
- Docker 主服务允许显式代理环境变量；工具提案沙箱继续 `network_mode: none`。

## M334 当前任务交接

- M332-0：已锁定统一 RunBudget、阶段进度协调器、provider 回调、异步终态隔离和前端事件投影的实现顺序；阶段文档和索引校验通过。
- M332 约束：结构化计划和工具参数完整校验后才能展示或执行；心跳只展示安全阶段事实；不保存模型原文、Prompt、隐藏思维链或密钥。
- M332-A：`run_budget` 深模块已实现，支持总/阶段/provider 单次预算、尝试/重试、剩余时间和安全 receipt；Docker 契约测试 `4/4` 通过。
- M332-B：`progress` 深模块已实现，支持有序阶段事件、heartbeat、恢复提示和安全关闭；RunEvent 已兼容增加超时/取消/重试/恢复与计时字段；Docker 预算/进度测试 `6/6` 通过。
- M332-C：已接入 Provider 结构化调用、compact recovery、ReAct 决策、普通答案与 Composite 答案的动态 timeout/deadline 和安全进度回调；Provider 重试/退避不突破 deadline，结构化结果仍须完整校验。
- M332-C 验证：M331 结构化响应 + M332 预算/进度/Provider 紧凑测试 `17/17` 通过；未调用真实模型。
- M332-D/E 红灯与修复：重建 Docker 后已修复 M37 极短 `0.01s` 超时、M60 Mock factory `event_sink` 参数兼容、M69 极短异步超时类型丢失，以及 SQLite reaper/worker 事件序号竞争。
- M332-D/E 验证：Runtime lifecycle、RunBudget、Progress、Provider、M37、M60、M69、M79 定向回归 `30/30` 通过；新增终态事件 fence 测试通过；未调用真实模型。
- M333-A：已完成共享 WebAccessPolicy、DNS 地址安全检查、搜索适配和配置兼容；M333 公共策略与 M321 搜索回归通过。
- M333-B：已完成 WebFetchAdapter 基础实现、HTML 正文抽取和 `_model_context` 临时传递 seam。
- 当前动作：M334-0 文档、索引和恢复入口已冻结。
- 下一步：实现 `agent/evidence/identity.py`、`quality.py` 和对应紧凑契约；不重复实现已有 Evidence Registry。
