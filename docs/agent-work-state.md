# Agent 当前工作快照

> 新对话或上下文压缩后的唯一默认入口。恢复脚本只读取本快照和 [`tasks/task-state.md`](../tasks/task-state.md)；不要自动读取完整历史恢复卡、问题日志、milestones、归档、全量测试、模型响应或无关源码。

## Goal 摘要

建设可测试、可观测、可替换、可恢复的领域中立 Agent Runtime。GIS 只是业务载体；系统通过能力目录、Planner、TaskPlan/DAG、ToolRegistry、统一生命周期、Result/View/Artifact/Evidence 支撑开放式、多领域、可恢复分析，不为单一区域、单一问句或单一数据集增加硬编码流程。

## Goal 附加约束：低成本上下文恢复

- 恢复只读取：本快照、当前阶段对应的 Spec/Plan、任务账本中最近的进行中任务，以及该任务明确列出的待修改文件。
- `tasks/task-state.md` 是进行中/最近完成子任务的记录源；`tasks/todo.md` 只保留阶段清单，不替代任务记录。
- 历史恢复卡、问题日志、milestones、归档、全量测试和模型原文只在当前任务明确需要时读取。
- 每个子任务开始、完成或暂停时，先更新任务账本；阶段收口时再同步阶段文档、快照和任务清单。

## 当前阶段

- 阶段：M281 动态 Composite 结果体验与跨入口一致性
- 状态：M280 已完成并推送 `599881c`；M281 全局规划待创建。
- 当前任务：M281-B 公共 Composite View Projection，详见 [`tasks/task-state.md`](../tasks/task-state.md)。
- 阶段规划：
  - [`docs/m281-dynamic-composite-capability-map.md`](m281-dynamic-composite-capability-map.md)
  - [`docs/m281-dynamic-composite-spec.md`](m281-dynamic-composite-spec.md)
  - [`docs/m281-dynamic-composite-plan.md`](m281-dynamic-composite-plan.md)

## 当前任务明确文件

- `agent/composite_contract.py`（待定位）
- `agent/result_registry.py`（待定位）
- `agent/application/http.py`（待定位）
- `tests/test_m281_dynamic_composite.py`（新增）

## 验证与安全约定

- Python、GIS、compileall、架构检查统一在 Docker 中运行：
  `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent ...`
- 默认测试保持离线精简；真实模型、真实 GIS、Docker HTTP 和浏览器只做显式验收。
- 不读取、输出或提交 API key、`.env.production`、模型原文、真实原始数据或宿主机私有路径。

## 恢复后的最小动作

1. 读取本文件和 `tasks/task-state.md`。
2. 按当前任务记录读取对应阶段 Spec/Plan。
3. 只读取当前任务明确列出的源码/测试文件。
4. 完成或暂停子任务后先更新 `tasks/task-state.md`，再更新本快照。
