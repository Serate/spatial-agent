# Agent 当前工作快照

> 新对话或上下文压缩后的唯一默认入口。恢复脚本只读取本快照和 [`tasks/task-progress.md`](../tasks/task-progress.md) 的最近记录；不要自动读取完整历史恢复卡、问题日志、milestones、归档、全量测试、模型响应或无关源码。

## Goal 摘要

建设可测试、可观测、可替换、可恢复的领域中立 Agent Runtime。GIS 只是业务载体；系统通过能力目录、Planner、TaskPlan/DAG、ToolRegistry、统一生命周期、Result/View/Artifact/Evidence 支撑开放式、多领域、可恢复分析，不为单一区域、单一问句或单一数据集增加硬编码流程。

## Goal 附加约束：低成本上下文恢复

- 恢复只读取：本快照、当前阶段对应的 Spec/Plan、任务账本中最近的进行中任务，以及该任务明确列出的待修改文件。
- Goal 级最小读取规则：只读取当前任务必需的文件；仅做状态判断时只读本快照和任务账本尾部，不默认读取历史文档、问题日志、milestones、归档、全量源码、全量测试或模型响应。
- 每次恢复或开始子任务前，先确定最小文件集合；读取过程中不得以项目熟悉为理由扩大范围，除非当前文件明确证明需要追查另一个文件。
- `tasks/task-progress.md` 是恢复用的进行中/最近完成子任务记录源；`tasks/task-state.md` 保留详细当前状态以兼容旧流程；`tasks/todo.md` 只保留阶段清单，不替代任务记录。
- 历史恢复卡、问题日志、milestones、归档、全量测试和模型原文只在当前任务明确需要时读取。
- 每个子任务开始、完成或暂停时，先更新任务账本；阶段收口时再同步阶段文档、快照和任务清单。
- 阶段任务按完整能力切片编排得更充分：一个阶段尽量覆盖契约、实现、集成、文档和交付准备等连续依赖，避免拆成过多过小的阶段。
- 每个阶段安排更多可连续交付的关联任务；任务数量增加不等于测试轮次增加，测试按独立失败模式合并到阶段收口执行。
- 测试保持精简：集中实现相关改动后统一验证，只保留独立失败模式、关键跨入口契约和阶段级 readiness/架构门禁；不因每个小改动重复运行相同测试。
- Goal 执行节奏：后续每阶段主动合并更多相互依赖的任务，按能力切片推进；开发中只做必要的快速检查，阶段收口再集中运行一次精简门禁，避免测试次数随任务数量线性增加。

## 当前阶段

- 阶段：M302 分阶段 Planner 上下文与开放问题成功链路（规划中）
- 状态：M301 已完成并待本轮版本交付；内部 Composite Context/目录/discovery 默认 256 KiB，provider Planner Envelope 独立 96 KiB。产品默认保持 `openai + local`。
- 当前任务：按项目全局实现 stage-aware provider projection，优先解决模型输入中的诊断重复和选择到执行的成功闭合。详见 [`tasks/task-progress.md`](../tasks/task-progress.md)；详细状态按需读取 [`tasks/task-state.md`](../tasks/task-state.md)。
- 阶段规划：
  - [`docs/m302-stage-aware-planner-context-capability-map.md`](m302-stage-aware-planner-context-capability-map.md)
  - [`docs/m302-stage-aware-planner-context-spec.md`](m302-stage-aware-planner-context-spec.md)
  - [`docs/m302-stage-aware-planner-context-plan.md`](m302-stage-aware-planner-context-plan.md)

## 当前任务明确文件

- `docs/m302-stage-aware-planner-context-spec.md`
- `docs/m302-stage-aware-planner-context-plan.md`
- `agent/runtime_core/planner_envelope.py`
- `agent/composite_request_context.py`
- `agent/application/composite_planning.py`
- `agent/runtime_core/component_fact_handoff.py`
- `agent/runtime_core/clarification_continuation.py`
- `tests/test_m301_planner_first_open_query.py`

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
