# Agent 当前工作快照

> 新对话或上下文压缩后的唯一默认入口。恢复脚本只读取本快照和 [`tasks/task-progress.md`](../tasks/task-progress.md) 最近记录；不要自动读取完整历史、全量源码、全量测试、模型响应或敏感配置。

## Goal 摘要

建设可测试、可观测、可替换、可恢复的领域中立 Agent Runtime。GIS 只是业务载体；系统通过能力目录、Planner、TaskPlan/DAG、ToolRegistry、统一生命周期、Result/View/Artifact/Evidence 支撑开放式、多领域、可恢复分析，不为单一区域、单一问句或单一数据集增加硬编码流程。

## Goal 附加约束：低成本上下文恢复

- 恢复只读取本快照、当前阶段 Spec/Plan、任务账本中最近的进行中任务，以及该任务明确列出的待修改文件。
- 只读取当前任务必需的文件；历史文档、milestones、归档、全量源码、全量测试、模型原文和敏感配置按需读取。
- 每个子任务开始、完成或暂停时更新 `tasks/task-progress.md`；阶段收口再同步任务状态、快照和历史恢复卡。
- 阶段任务按完整能力切片编排，测试按独立失败模式合并到阶段收口，不因每个小改动重复执行相同测试。

## 当前阶段

- 阶段：M307 Agent Runtime 生命周期与传输边界收敛（已规划，A 进行中）
- 状态：M306 已完成并交付；真实中转 + 本地 GIS/Economic 的 2 组件多入口链路、artifact/restart 和结构化结果一致性通过。产品默认保持 `openai + local`。
- 当前任务：M307-A 冻结生命周期、传输兼容矩阵和 compat 守卫分类；详见 [`tasks/task-progress.md`](../tasks/task-progress.md) 与 [`tasks/task-state.md`](../tasks/task-state.md)。
- 阶段规划：
  - [`docs/m307-runtime-boundaries-capability-map.md`](m307-runtime-boundaries-capability-map.md)
  - [`docs/m307-runtime-boundaries-spec.md`](m307-runtime-boundaries-spec.md)
  - [`docs/m307-runtime-boundaries-plan.md`](m307-runtime-boundaries-plan.md)

## 当前任务明确文件

- `docs/m307-runtime-boundaries-capability-map.md`
- `docs/m307-runtime-boundaries-spec.md`
- `docs/m307-runtime-boundaries-plan.md`
- `agent/runtime_core/run_lifecycle.py`
- `production_api.py`
- `serve_api.py`
- `application/http.py`
- `scripts/architecture_check.py`
- `tests/test_m307_runtime_boundaries.py`

## M307-A：基线与阶段契约 — 进行中

- 目标：以 M306 真实多组件闭环为基线，冻结 Runtime 显式阶段、FastAPI/stdlib 传输兼容矩阵和 compat 守卫分类。
- 边界：先拆生命周期与公共传输边界，不新增领域工具，不修改既有公共 schema，不绕过 canonical DAG、TaskPlan、ToolRegistry 或 execution binding。
- 验证：开发期间只做必要静态/契约检查；B～D 合并后在 Docker 集中运行阶段门禁；本阶段不重复 M306 live。
- 阻塞：无。

## 验证与安全约定

- Python、GIS、compileall、架构检查统一在 Docker 中运行：
  `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent ...`
- 默认测试保持离线精简；真实模型、真实 GIS、Docker HTTP 和浏览器只做显式验收。
- 不读取、输出或提交 API key、`.env.production`、模型原文、真实原始数据或宿主机私有路径。

## 恢复后的最小动作

1. 读取本文件和 `tasks/task-progress.md` 最近记录。
2. 按当前任务记录读取对应阶段 Spec/Plan。
3. 只读取当前任务明确列出的源码/测试文件。
4. 完成或暂停子任务后先更新 `tasks/task-progress.md`，再同步 `tasks/task-state.md` 和本快照。
