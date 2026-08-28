# Agent 当前工作快照

> 这是默认恢复入口，必须保持短小，只记录当前阶段。历史阶段、完整计划和问题记录不放在这里。
> 默认恢复命令：`pwsh -NoProfile -File scripts/resume_context.ps1`。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime；真实模型默认通过受控 ReAct
理解开放式问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答。GIS 只是业务载体。

## 当前阶段

- 阶段：M318-M325 受控开放 Agent Runtime
- 当前阶段：M323 人工审批、持久化和 Registry 治理
- 当前任务：M323-A，冻结审批状态机、持久化边界、注册版本和 HTTP 语义
- 状态：规划中
- 最近交付：M322 已完成并推送，版本 `1b0bcdc`
- 协作：单 Agent，最大并发度 1；Python、GIS、测试和阶段验收优先使用 Docker

## 当前阶段入口

- 能力图：[`stages/M323/capability-map.md`](stages/M323/capability-map.md)
- Spec：[`stages/M323/spec.md`](stages/M323/spec.md)
- Plan：[`stages/M323/plan.md`](stages/M323/plan.md)
- 交接：[`stages/M323/handoff.md`](stages/M323/handoff.md)
- 任务状态：[`../tasks/current-state.md`](../tasks/current-state.md)
- 文档索引：[`document-index.json`](document-index.json)

## 当前任务必要文件

- `agent/tooling/proposal.py`
- `agent/tooling/__init__.py`
- `agent/tools.py`
- `agent/runtime.py`
- `agent/runtime_core/react_runtime.py`
- `agent/sqlite_store.py`
- `agent/application/http.py`
- `tests/test_m323_tool_approval.py`（待创建）
- `scripts/resume_context.ps1`
- `scripts/validate_document_index.ps1`
- `scripts/archive_document_sections.ps1`

## 最近验证

- M322 Docker 契约：7/7
- M318-M322 合并契约：43/43
- Docker compileall、architecture strict、smoke、readiness 200 和 sidecar socket 验证通过
- 当前无阻塞；未调用真实模型，未保存 Prompt、模型原文、密钥或敏感数据

## 恢复规则

1. 先读取本文件、`document-index.json`、`tasks/current-state.md` 和当前阶段 `handoff.md`。
2. 只按交接文件的“必要文件”读取源码、Spec 或 Plan；不读取完整历史。
3. 需要查历史时使用 `resume_context.ps1 -Topic ...`，需要归档时显式增加 `-IncludeHistory`。
4. 每个子任务完成后更新 `tasks/current-state.md`、`tasks/task-progress.md` 和本快照。
