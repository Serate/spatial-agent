# M303 开放式 LLM Composite 执行成功链路实施计划

## A：全局基线与状态矩阵

- 从 M302 的阶段 Envelope、selection evidence、execution binding 和 M278 生命周期中冻结 `PLANNED`、`NEEDS_CLARIFICATION`、`REJECTED`、`FAILED`、`COMPLETED` 的输入/输出矩阵。
- 选定一个可由现有 GIS/Economic catalog 支撑、事实足够明确的跨域请求作为 live probe；另选一个事实不足请求验证澄清，不将具体问句写入生产分支。
- 明确可观测字段：request/discovery/binding fingerprint、component identity、result profile、provider 状态、是否创建 run。

## B：模型决策契约与输出适配

- 审查 `LLMCompositePlanner` 的 system/user 投影、structured schema 和 repair 入口，确保模型只看到当前 selection 阶段需要的候选和执行闭合信息。
- 把模型输出中的组件 identity、依赖、请求事实和结果类型统一映射到现有 Composite request；未知字段丢弃或拒绝，未知 identity fail closed。
- 保持一次既有有界 repair；repair 不能改变领域、能力、数据、事实、权限或执行结果。
- 记录有界 planner evidence，不保存 provider 原文。

## C：Canonical TaskPlan 与执行闭合

- 用合法多组件 replay fixture 验证模型适配结果能进入现有 Composite TaskPlan/DAG、workflow、ToolRegistry 和 execution binding。
- 对空组件、未绑定 workflow、依赖环、未注册能力、readiness 不可用和组件事实缺失逐类验证，确保都在 run 创建前终止。
- 对 Rule/Replay/LLM 比较 request fingerprint、component identity、plan fingerprint、binding fingerprint 和 result profile；不建立第二套执行授权。

## D：真实数据与跨入口验收

- 在 Docker 中使用当前真实挂载数据，先通过 Rule/Replay 完成 GIS/Economic 的同步对照。
- 复用 M278 生命周期执行一次同步、异步、artifact、SQLite/restart 和 evidence 查询，比较 canonical result/view/evidence identity。
- 仅在计划和数据 readiness 均通过后执行显式 live；provider 失败不重复消耗 token，按 receipt 分类。

## E：前端与交付门禁

- 验证 Console 只按结构化 Result/View/Evidence 展示选择、阶段、结果和限制，不读取模型原文或工具名分支。
- 集中执行 M303 contract、相邻 Composite Planner/TaskPlan 回归、production acceptance、compileall、architecture strict、Node projection、Service smoke 和 readiness。
- 若发现结果/证据/视图漂移，优先修复公共 contract seam，并新增最小回归；不在 acceptance 脚本中放宽判断。

## F：文档、版本与全局重规划

- 用中文更新 `docs/agent-development-issues.md`、`docs/milestones.md`、`docs/agent-work-state.md`、`tasks/task-progress.md`、`tasks/task-state.md`、`tasks/todo.md` 和本阶段 Plan。
- 阶段验收完成后提交并推送一个版本，记录实际 live 状态；不把“provider 可达”写成“跨域成功执行”。
- 再从产品、架构、数据、模型、部署、体验、测试七个维度检查下一阶段，优先补全目标中仍缺失的通用能力，而不是继续扩大单一数据集测试。

## 依赖、风险与检查点

| 检查点 | 必须成立 | 失败处理 |
| --- | --- | --- |
| A 完成 | 状态矩阵和 live 请求边界明确 | 更新 Spec，不进入模型改动 |
| B 完成 | 合法模型输出可被安全适配，非法输出 fail closed | 保留 provider failure/clarification |
| C 完成 | 计划经既有 TaskPlan/binding 门禁 | 不创建 run，记录 reason code |
| D 完成 | 真实数据和跨入口核心 identity 一致 | 结构化降级，定位数据或 provider 平面 |
| E 完成 | 精简门禁和前端投影通过 | 修公共 contract，不删测试 |
| F 完成 | 中文文档、版本和下一阶段规划完成 | 阶段不标记完成 |

## 当前实施顺序

先完成 A/B 的代码审查与最小契约，再完成 C/D 的真实数据纵向验收，最后集中执行 E/F。全程串行，默认测试只在阶段收口集中运行。

## 实际阶段收口

- A/B/C 已完成：模型结构化输出经过 canonical Composite request、TaskPlan/DAG、ToolRegistry 和 execution binding 的唯一门禁；Rule、Replay、LLM 不再拥有分叉执行授权。
- D 已完成：Docker 真实 GIS/Economic 数据的 sync/async、artifact、SQLite/restart 和 evidence 对照通过；活动 Composite `PLANNING` 快照误投影为 `FAILED` 的问题已修复。
- E 已完成：M303 与相邻回归 **12/12**，compileall、architecture strict、Node projection、Service smoke、生产 HTTP 和 readiness **200** 通过。
- 显式 live 只执行 1 次，60 秒、0 重试，返回脱敏 `FAILED/timeout` receipt，未创建 execution run；该结果不计为真实模型成功。
- F 已完成：中文问题日志、里程碑、任务账本、恢复快照已同步，并已创建 M304 的全局 capability map、Spec 和 Plan。
