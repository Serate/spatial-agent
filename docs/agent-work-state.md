# Agent 当前工作快照

> 默认恢复：`pwsh -NoProfile -File scripts/resume_context.ps1`。只读取本文件、任务状态、当前阶段 handoff 和当前任务必要文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime。真实模型默认通过受控 ReAct 理解开放问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答；GIS 只是业务载体。

## 当前阶段

- 阶段：`M330` 通用 Agent 开放问题质量与纵向行为验收
- 当前任务：M330-A 通用直接回答场景矩阵
- 状态：M330-A 进行中：固定通用直接回答场景矩阵并补齐最小契约验证
- 基线：`81e79ab`
- 协作：单 Agent，最大并发度 1；测试与 GIS 优先使用 Docker

## 阶段入口

- [`docs/stages/M330/capability-map.md`](stages/M330/capability-map.md)
- [`docs/stages/M330/spec.md`](stages/M330/spec.md)
- [`docs/stages/M330/plan.md`](stages/M330/plan.md)
- [`docs/stages/M330/handoff.md`](stages/M330/handoff.md)
- [`tasks/current-state.md`](../tasks/current-state.md)
- [`docs/document-index.json`](document-index.json)

## 当前任务必要文件

- `agent/general_runtime.py`
- `agent/answer_generation.py`
- `agent/result_summary.py`
- `agent/llm_planner.py`
- `tests/test_answer_generation.py`
- `tests/test_m330_direct_answer.py`
- `docs/stages/M330/{capability-map.md,spec.md,plan.md,handoff.md}`

## 恢复规则

1. 只读取当前快照、`tasks/current-state.md`、M330 handoff 和当前任务列出的文件。
2. 历史账本、完整阶段文档、全量源码、全量测试、模型原文和敏感配置按需读取。
3. 每个子任务开始/完成/暂停时先更新热状态，再追加任务账本；阶段结束后更新 handoff、索引并提交推送。
4. 默认只运行受影响的紧凑测试、必要 smoke 和阶段集成验收。
