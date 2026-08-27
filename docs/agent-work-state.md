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

- 阶段：M310 开放请求能力选择与数据语义闭合（已完成）
- 状态：M309 已完成并推送版本 `19e8506`；M310 已完成 Docker 阶段验收、文档收口，产品默认保持 `openai + local`，Docker 是统一 Python/GIS/live 验收环境。
- 当前任务：M310 已完成；Docker M310 契约 14/14、M309 相邻回归 8/8、跨入口、真实本地 GIS HTTP、Node projection、compileall、architecture strict、Service smoke 和 readiness 通过。唯一一次真实模型调用到达 provider 并返回结构化澄清，未创建 run。下一阶段需按项目全局重新规划。详见 [`tasks/task-progress.md`](../tasks/task-progress.md) 与 [`tasks/task-state.md`](../tasks/task-state.md)。
- 阶段规划：
  - [`docs/m310-open-request-capability-closure-capability-map.md`](m310-open-request-capability-closure-capability-map.md)
  - [`docs/m310-open-request-capability-closure-spec.md`](m310-open-request-capability-closure-spec.md)
  - [`docs/m310-open-request-capability-closure-plan.md`](m310-open-request-capability-closure-plan.md)

## 当前任务明确文件

- `docs/m310-open-request-capability-closure-capability-map.md`
- `docs/m310-open-request-capability-closure-spec.md`
- `docs/m310-open-request-capability-closure-plan.md`
- `agent/data_readiness.py`
- `agent/capability_catalog.py`
- `agent/composite_request_context.py`
- `agent/runtime_core/analysis_discovery.py`
- `agent/runtime_core/planner_envelope.py`
- `agent/application/composite_planning.py`
- `tests/test_m310_open_request_capability_closure.py`
- `web/src/console_result_projection.js`
- `scripts/console_result_projection_smoke.js`

> M310 已收口；上述文件仅用于阶段追溯。下一阶段开始前，先创建新的 Spec/Plan，
> 再把新的待修改文件替换到本清单，避免恢复上下文时读取无关文件。

## M310：开放请求能力选择与数据语义闭合 — 已完成

- 结果：统一 `any/all/one` 事实需求语义，闭合 capability → Domain workflow →
  TaskPlan/DAG → ToolRegistry → execution binding；新增领域中立 readiness 和有界
  `planning_failure` 投影，区分澄清、预览失败、绑定失败和拒绝。
- 前端：结构化结果投影能够显示等待补充、计划未生成和计划校验未通过，不显示内部
  错误码、工具名、prompt 或 provider 原文；修复 planning failure 阶段条件的字段
  命名/逻辑运算符问题。
- 验证：Docker M310 **14/14**、M309 相邻回归 **8/8**、compileall、architecture
  strict、Node projection、Service smoke、跨入口 identity、真实本地 GIS HTTP 和
  `/health/ready` 200 通过。
- 真实模型：唯一一次显式调用使用结构化输出通道并到达 provider，返回
  `NEEDS_CLARIFICATION`，未创建执行 run；按真实语义澄清记录。

## M308-F：开放组合纵向链路与用户答案质量 — 已完成

- 结果：真实 GIS/Economic/Indicators 三组件完成规划和执行；答案契约增加可选 `next_steps`；上下文 workflow 约束漂移与 handoff 无条件合并问题已修复。
- 验证：Docker M308/相邻 Composite **28/28**，真实组合与跨入口验收通过；compileall、architecture strict、Node projection、Service smoke、生产 HTTP acceptance 和 readiness **200/ready**。
- 交付准备：阶段文档已补齐，下一阶段 M309 文档已创建；本次工作区待统一提交并推送。

## M309-A：模型计划结果矩阵与全局基线 — 已完成

- 目标：以 M308 的 3+ 组件闭环为基线，冻结 provider-backed 成功、澄清、非法计划、有限修复、provider failure 和执行失败的公共状态与 run 创建边界。
- 边界：只使用现有 Planner Envelope、Capability Catalog、TaskPlan/DAG、ToolRegistry、workflow、execution binding 和 Result/Evidence seam，不新增专题工具或领域专用前端分支。
- 结果：planner-attempt 对无 metrics 客户端也能记录真实调用状态和 retryable；provider failure、语义拒绝和澄清保持独立状态。
- 验证：Docker M309-A 精简契约 **4/4** 通过；阶段门禁仍在 M309-E 集中执行，真实模型最多显式调用一次。
- 阻塞：无。

## M309-B：真实模型到可执行计划的受控闭合 — 已完成

- 目标：让多目标开放请求通过 Capability Catalog 形成多个已登记组件，并在 schema、canonical DAG、TaskPlan、ToolRegistry、workflow 和 execution binding 全部门禁通过后执行。
- 结果：模型提示补充通用多目标拆分原则；3+ 组件输出继续经过 catalog/schema/canonical DAG/TaskPlan/ToolRegistry/workflow/execution binding 全部门禁。
- 验证：Docker M309-A/B 相关契约与 M305/M287 相邻回归 **18/18** 通过；未执行真实模型。
- 边界：有限 repair 最多一次；不得用 Rule/Replay 静默替代真实模型失败，不得放宽执行授权。
- 阻塞：无。

## M309-C：默认 Agent 的可感知体验 — 已完成

- 目标：结构化答案对象只投影可读文本；失败提示按公共错误平面生成；阶段状态、限制和下一步继续由 Result/View/Evidence 驱动。
- 结果：聊天摘要安全读取 `summary/headline` 或明确字符串；拒绝、规划失败和执行失败提示通用化，不展示内部对象字段。
- 验证：Docker 前端构建与 Node Console Result Projection smoke 通过。
- 阻塞：无。

## M309-D：跨入口恢复与一致性 — 已完成

- 目标：确认 M309 的 planner receipt、默认答案和阶段投影不改变同步、异步、HTTP、View、artifact、SQLite/restart 的公共 identity。
- 结果：Docker 三组件跨入口验收六项 identity 对照全部为 `true`，artifact 可用，View answer 保留 `next_steps` 字段。
- 验证：`scripts/m308_cross_entry_acceptance.py` 通过；未执行额外真实模型请求。
- 阻塞：无。

## M309-E/F：阶段验收、文档与版本交付 — 已完成

- 阶段门禁：重建 Docker 镜像并强制重建服务后，M309/M308/M303/M305 精简契约 **31/31**，compileall、architecture strict、Node projection、Service smoke、跨入口验收、真实 GIS 三组件验收和生产 HTTP acceptance 全部通过；`/health/ready` 为 `ready`。
- 真实模型：唯一一次调用在修复前返回结构化计划，但 GIS `raster_metadata` preview 因缺少 `dataset` 事实失败；未创建 execution run。修复后的成功由脱敏 Replay 和真实 Docker GIS 验收证明，不冒充 live 成功。
- 交付：中文问题日志、M309 Plan、恢复快照、任务账本和 M310 能力图/Spec/Plan 已同步；本次版本提交后推送。

## M310-A：事实需求矩阵与基数语义 — 已完成

- 目标：冻结 `any/all/one` 事实需求语义及缺失、歧义、ready、unavailable 的公共投影；不改变 Runtime、Planner、ToolRegistry 的执行授权边界。
- 当前文件：`agent/capability_catalog.py`、`agent/runtime_core/component_fact_handoff.py`、`agent/composite_request_context.py`、`tests/test_m310_open_request_capability_closure.py`。
- 阻塞：无。

## M310-B：Capability 到 Domain workflow 闭合 — 已完成

- 结果：选中 capability 的 workflow 必须由 Domain resolver 确认，不能从 context workflow 兜底；workflow 身份不完整或不属于 capability 时在 preview 前终止；不可用与未绑定 capability 保持不同状态。
- 文件：`agent/runtime_core/composite_taskplan.py`、`tests/test_m310_open_request_capability_closure.py` 及 M310-A 公共 requirements 投影文件。
- 验证：Docker M310-B **10/10**；未执行真实模型。
- 下一步：进入 M310-C，统一 TaskPlan 物化和失败分类。

## M310-C：TaskPlan 物化与失败分类 — 已完成

- 目标：复用已有 TaskPlan/DAG、ToolRegistry 和 execution binding 门禁，统一 clarification、preview invalid/failed 和 binding failed 的 public evidence 与 run 创建边界。
- 当前文件：`agent/application/composite_planning.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/execution_binding.py`、`tests/test_m310_open_request_capability_closure.py`。
- 验证：开发期间只运行新增或直接相关契约；阶段收口在 Docker 集中执行，并包含一次显式真实模型验收。
- 阻塞：无。

## M310-D：数据 readiness 与结果证据 — 进行中

- 目标：将 capability 的字段、空间/时间对齐、覆盖范围和来源状态投影为明确 readiness，并保持事实、限制和结果证据一致。
- 结果：规划失败返回有界 `planning_failure`，区分 clarification、preview_invalid、preview_failed、binding_failed 和 rejected；通用 `failure.v1` 同步保留，非 `PLANNED` 状态不创建 execution run。
- 当前文件：`agent/capability_catalog.py`、`agent/runtime_core/analysis_discovery.py`、`agent/composite_request_context.py`、`agent/composite_view.py`、`tests/test_m310_open_request_capability_closure.py`。
- 验证：开发期间仅运行新增或直接相关契约；阶段收口在 Docker 集中执行，并包含一次显式真实模型验收。
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
