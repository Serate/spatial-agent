# Agent 当前工作快照

> 默认恢复：`pwsh -NoProfile -File scripts/resume_context.ps1`。只读取本文件、任务状态、当前阶段 handoff 和当前任务必要文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime。真实模型默认通过受控 ReAct 理解开放问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答；GIS 只是业务载体。

## 当前阶段

- 阶段：`M331` 真实模型开放任务可靠性与通用能力可用率
- 当前任务：M331-F 阶段交付与全局重规划
- 状态：M330 已完成并推送；M331-A～F 已完成，待提交阶段版本
- 基线：`0ce3ba4`
- 协作：单 Agent，最大并发度 1；测试与 GIS 优先使用 Docker

## 阶段入口

- [`docs/stages/M331/capability-map.md`](stages/M331/capability-map.md)
- [`docs/stages/M331/spec.md`](stages/M331/spec.md)
- [`docs/stages/M331/plan.md`](stages/M331/plan.md)
- [`docs/stages/M331/handoff.md`](stages/M331/handoff.md)
- [`tasks/current-state.md`](../tasks/current-state.md)
- [`docs/document-index.json`](document-index.json)

## 当前任务必要文件

- `docs/stages/M331/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/context_engineering.py`
- `agent/runtime_state.py`
- `agent/sqlite_store.py`
- `agent/artifact_store.py`
- `agent/run_events.py`
- `agent/application/async_runs.py`
- M331-D/E 答案生成、RunEvent/SSE、前端 projection、Docker 门禁及直接相关紧凑测试
- `tasks/current-state.md`
- `docs/document-index.json`

## 恢复规则

1. 只读取当前快照、`tasks/current-state.md`、M331 handoff 和当前任务列出的文件。
2. 历史账本、完整阶段文档、全量源码、全量测试、模型原文和敏感配置按需读取。
3. 每个子任务开始/完成/暂停时先更新热状态，再追加任务账本；阶段结束后更新 handoff、索引并提交推送。
4. 默认只运行受影响的紧凑测试、必要 smoke 和阶段集成验收。

## 最近完成

- M331-C：修复预算裁剪导致版本化 workflow template 摘要整段丢失的问题；超预算时先保留 schema、能力边界和步骤形状，再按预算继续裁剪。
- M331-C Docker 紧凑恢复回归 `24/24` 通过，覆盖上下文脱敏、SQLite/Artifact、RunEvent/SSE、工具审批恢复和同一 Run identity。

## 当前任务交接

- M331-D/E 已完成：答案质量 receipt、ReAct 事件前端可见性、6000 字符答案流上限和 Docker 阶段门禁已实现并验证。
- M331-F 已完成文档/索引收口：当前阶段 handoff、热状态、任务账本、开发问题记录、代码索引和文档索引已更新；下一阶段输入为真实模型复杂规划延迟与增量反馈。
- 真实验收：通用真实模型直答 `COMPLETED/live_model/streaming=True/quality=pass`；复杂 GIS 多步请求在 provider 规划预算内未返回，已中止并记录为 provider 延迟风险，未保存模型原文。
- 下一步：提交并推送 M331 阶段版本；恢复时只读取 M331 handoff、当前状态和本任务必要文件。
