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

- 阶段：M284 会话清空与跨入口状态一致性
- 状态：M284-A～D 已完成，进入文档、版本交付与全局重规划。
- 当前任务：M284-E 文档、版本交付与全局重规划，详见 [`tasks/task-progress.md`](../tasks/task-progress.md)；详细状态按需读取 [`tasks/task-state.md`](../tasks/task-state.md)。
- 阶段规划：
  - [`docs/m284-session-reset-consistency-capability-map.md`](m284-session-reset-consistency-capability-map.md)
  - [`docs/m284-session-reset-consistency-spec.md`](m284-session-reset-consistency-spec.md)
  - [`docs/m284-session-reset-consistency-plan.md`](m284-session-reset-consistency-plan.md)

## 当前任务明确文件

- `docs/agent-development-issues.md`
- `docs/milestones.md`
- `tasks/task-progress.md`
- `tasks/task-state.md`
- `tasks/todo.md`
- `docs/agent-work-state.md`

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
