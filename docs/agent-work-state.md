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

- 阶段：M309 真实模型开放组合与默认 Agent 体验（已规划，A 进行中）
- 状态：M308 已完成阶段验收，准备在本次工作区统一提交并推送；产品默认保持 `openai + local`，Docker 是统一 Python/GIS/live 验收环境。
- 当前任务：M309-A 冻结真实模型/Replay 计划结果矩阵、run 创建边界和公共 identity；详见 [`tasks/task-progress.md`](../tasks/task-progress.md) 与 [`tasks/task-state.md`](../tasks/task-state.md)。
- 阶段规划：
  - [`docs/m309-real-model-agent-experience-capability-map.md`](m309-real-model-agent-experience-capability-map.md)
  - [`docs/m309-real-model-agent-experience-spec.md`](m309-real-model-agent-experience-spec.md)
  - [`docs/m309-real-model-agent-experience-plan.md`](m309-real-model-agent-experience-plan.md)

## 当前任务明确文件

- `docs/m308-open-composition-vertical-slice-capability-map.md`
- `docs/m308-open-composition-vertical-slice-spec.md`
- `docs/m308-open-composition-vertical-slice-plan.md`
- `agent/application/composite.py`
- `agent/application/composite_planning.py`
- `agent/runtime_core/composite_taskplan.py`
- `agent/runtime_core/execution_binding.py`
- `tests/test_m308_open_composition_vertical_slice.py`

## M308-F：开放组合纵向链路与用户答案质量 — 已完成

- 结果：真实 GIS/Economic/Indicators 三组件完成规划和执行；答案契约增加可选 `next_steps`；上下文 workflow 约束漂移与 handoff 无条件合并问题已修复。
- 验证：Docker M308/相邻 Composite **28/28**，真实组合与跨入口验收通过；compileall、architecture strict、Node projection、Service smoke、生产 HTTP acceptance 和 readiness **200/ready**。
- 交付准备：阶段文档已补齐，下一阶段 M309 文档已创建；本次工作区待统一提交并推送。

## M309-A：模型计划结果矩阵与全局基线 — 进行中

- 目标：以 M308 的 3+ 组件闭环为基线，冻结 provider-backed 成功、澄清、非法计划、有限修复、provider failure 和执行失败的公共状态与 run 创建边界。
- 边界：只使用现有 Planner Envelope、Capability Catalog、TaskPlan/DAG、ToolRegistry、workflow、execution binding 和 Result/Evidence seam，不新增专题工具或领域专用前端分支。
- 当前文件：`docs/m309-real-model-agent-experience-capability-map.md`、`docs/m309-real-model-agent-experience-spec.md`、`docs/m309-real-model-agent-experience-plan.md`；后续按任务增量加入契约测试和实现文件。
- 验证：开发期间仅做必要静态/契约检查；M309-A～D 合并后在 Docker 集中收口，真实模型最多显式调用一次。
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
