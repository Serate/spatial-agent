# Agent 当前工作快照

> 默认恢复：`pwsh -NoProfile -File scripts/resume_context.ps1`。只读取本文件、任务状态、当前阶段 handoff 和当前任务必要文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime。真实模型默认通过受控 ReAct 理解开放问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答；GIS 只是业务载体。

## 当前阶段

- 阶段：`M331` 真实模型开放任务可靠性与通用能力可用率
- 当前任务：M331-0 全局规划与恢复入口
- 状态：M330 已完成并交付；M331-0 进行中，只建立全局规划和最小恢复入口
- 基线：`81e79ab`
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
- `docs/stages/M330/handoff.md`
- `tasks/current-state.md`
- `docs/document-index.json`

## 恢复规则

1. 只读取当前快照、`tasks/current-state.md`、M330 handoff 和当前任务列出的文件。
2. 历史账本、完整阶段文档、全量源码、全量测试、模型原文和敏感配置按需读取。
3. 每个子任务开始/完成/暂停时先更新热状态，再追加任务账本；阶段结束后更新 handoff、索引并提交推送。
4. 默认只运行受影响的紧凑测试、必要 smoke 和阶段集成验收。
