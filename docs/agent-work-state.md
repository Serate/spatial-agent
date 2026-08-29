# Agent 当前工作快照

> 这是默认恢复入口，必须保持短小，只记录当前阶段。历史阶段、完整计划和问题记录不放在这里。
> 默认恢复命令：`pwsh -NoProfile -File scripts/resume_context.ps1`。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime；真实模型默认通过受控 ReAct
理解开放式问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答。GIS 只是业务载体。

## 当前阶段

- 阶段：`M327`
- 当前任务：M327-A 能力描述契约
- 状态：规划完成，尚未实现
- 最近交付：M326 已完成开放式 ReAct 稳定交付、真实 Docker/GIS 验收和跨入口恢复对照
- 协作：单 Agent，最大并发度 1；Python、GIS、测试和阶段验收优先使用 Docker
- M326 已完成：开放 ReAct 与自动 Domain 模板策略解耦；Result/evidence/artifact/SSE/答案统一表达部分结果；
  Artifact 原子发布和 Provider JSON 错误边界已修复；真实模型 + Docker/GIS 多步与矢量请求完成安全验收。
- M327 目标：完善通用能力描述、选择解释和跨类型结果摘要，不为固定区域、问句或 GIS 页面增加专用分支。

## 当前阶段入口

- 当前阶段能力图：[`stages/M327/capability-map.md`](stages/M327/capability-map.md)
- 当前阶段 Spec：[`stages/M327/spec.md`](stages/M327/spec.md)
- 当前阶段 Plan：[`stages/M327/plan.md`](stages/M327/plan.md)
- 当前阶段交接：[`stages/M327/handoff.md`](stages/M327/handoff.md)
- 任务状态：[`../tasks/current-state.md`](../tasks/current-state.md)
- 文档索引：[`document-index.json`](document-index.json)

## 当前任务必要文件

- `docs/stages/M327/handoff.md`
- `docs/stages/M327/spec.md`
- `docs/stages/M327/plan.md`
- `agent/capability_catalog.py`
- `agent/application/catalog.py`
- `agent/domain_contract.py`
- `agent/result_contract.py`
- `agent/result_completeness.py`
- `agent/evidence/projection.py`
- `tests/test_m326_result_completeness.py`
- `docs/document-index.json`
- `scripts/validate_document_index.ps1`

## 最近验证

- M326 Docker 阶段紧凑回归 `49/49`、Artifact/Provider 定向回归、compileall、architecture strict 和 readiness `200` 通过。
- 真实 Docker/GIS：sync/async/polling/artifact/evidence/SSE/Last-Event-ID/restart 对照通过；真实数据仅一次性只读挂载。
- 未保存 Prompt、模型原文、密钥或敏感数据。

## 恢复规则

1. 先读取本文件、`document-index.json`、`tasks/current-state.md` 和 M327 handoff。
2. 只按 M327 Plan 的当前批次读取明确列出的源码；不读取已完成阶段历史。
3. 需要查历史时使用 `resume_context.ps1 -Topic ...`，需要归档时显式增加 `-IncludeHistory`。
4. M323～M326 已完成；恢复时只读取本快照、M327 handoff/plan/spec 和明确源码。
