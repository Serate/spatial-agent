# Agent 当前工作快照

> 新对话或上下文压缩后的唯一默认入口。恢复脚本只读取本快照和 [`tasks/task-progress.md`](../tasks/task-progress.md) 的最近记录；不要自动读取完整历史恢复卡、问题日志、milestones、归档、全量测试、模型响应或无关源码。

## Goal 摘要

建设可测试、可观测、可替换、可恢复的领域中立 Agent Runtime。GIS 只是业务载体；系统通过能力目录、Planner、TaskPlan/DAG、ToolRegistry、统一生命周期、Result/View/Artifact/Evidence 支撑开放式、多领域、可恢复分析，不为单一区域、单一问句或单一数据集增加硬编码流程。

## Goal 附加约束：低成本上下文恢复

- 恢复只读取：本快照、当前阶段对应的 Spec/Plan、任务账本中最近的进行中任务，以及该任务明确列出的待修改文件。
- `tasks/task-progress.md` 是恢复用的进行中/最近完成子任务记录源；`tasks/task-state.md` 保留详细当前状态以兼容旧流程；`tasks/todo.md` 只保留阶段清单，不替代任务记录。
- 历史恢复卡、问题日志、milestones、归档、全量测试和模型原文只在当前任务明确需要时读取。
- 每个子任务开始、完成或暂停时，先更新任务账本；阶段收口时再同步阶段文档、快照和任务清单。

## 当前阶段

- 阶段：M283 开放式请求 Agent 闭环
- 状态：M282 已完成并推送 `a7e933b`；M283-A 全局能力图、Spec、Plan 已完成。
- 当前任务：M283-C 开放式成功切片与跨入口恢复，详见 [`tasks/task-progress.md`](../tasks/task-progress.md)；需要更详细状态时再读取 [`tasks/task-state.md`](../tasks/task-state.md)。
- 阶段规划：
  - [`docs/m283-open-query-agent-capability-map.md`](m283-open-query-agent-capability-map.md)
  - [`docs/m283-open-query-agent-spec.md`](m283-open-query-agent-spec.md)
  - [`docs/m283-open-query-agent-plan.md`](m283-open-query-agent-plan.md)

## 当前任务明确文件

- `agent/application/composite_runs.py`
- `agent/application/composite_planning.py`
- `tests/test_m283_open_query_agent.py`

## 验证与安全约定

- Python、GIS、compileall、架构检查统一在 Docker 中运行：
  `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent ...`
- 默认测试保持离线精简；真实模型、真实 GIS、Docker HTTP 和浏览器只做显式验收。
- 不读取、输出或提交 API key、`.env.production`、模型原文、真实原始数据或宿主机私有路径。

## 恢复后的最小动作

1. 读取本文件和 `tasks/task-progress.md` 的最近记录。
2. 按当前任务记录读取对应阶段 Spec/Plan。
3. 只读取当前任务明确列出的源码/测试文件。
4. 完成或暂停子任务后先更新 `tasks/task-progress.md`，再同步 `tasks/task-state.md` 和本快照。
