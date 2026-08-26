# M309 真实模型开放组合与默认 Agent 体验实施计划

## A：模型计划结果矩阵与全局基线

- 从 M308 的 3+ 组件闭环出发，冻结真实模型/Replay 的成功、澄清、非法计划、有限修复、provider failure 和执行失败矩阵。
- 盘点当前 Planner Envelope、provider receipt、canonical plan receipt、TaskPlan/DAG 和 execution binding 的公共 identity，确认 run 创建边界。
- 为阶段契约保留最小脱敏回放样本，不保存模型原文或 prompt。

状态：进行中。

## B：真实模型到可执行计划的受控闭合

- 让模型只能从 Catalog 选择能力，并通过阶段化 Envelope、schema、计划完整性、DAG、ToolRegistry、workflow 和 execution binding 门禁。
- 补充有限 repair/clarification 的统一状态和 lineage；修复失败必须 fail closed，不能隐式降级为 Rule 成功。
- 使用一组紧凑契约验证 success、clarification、rejection 和 provider failure 不会互相伪装。

状态：待开始。

## C：默认 Agent 的可感知体验

- 检查产品默认的模型/本地 GIS 路径，确保默认配置和阶段投影表达真实状态，不让测试默认值污染产品路径。
- 让用户优先看到结论、关键指标、限制和下一步；计划、轨迹和证据按需展开。
- 统一“补充事实、重试模型、确认计划、查看结果”等动作的结构化语义，不增加领域专用页面分支。

状态：待开始。

## D：跨入口恢复与一致性

- 对照 sync、async、HTTP、View、artifact、SQLite/restart 的 plan/binding/result/answer/evidence identity。
- 覆盖活动状态、provider 失败、局部组件失败和重启接管，确保已完成事实不丢失、未验证计划不执行。

状态：待开始。

## E：Docker 阶段验收与一次显式 live

- 从当前工作区重建 Docker 镜像并强制重建服务，集中运行本阶段契约、相邻回归、compileall、architecture strict、Node projection、Service smoke、HTTP/artifact/restart 和 readiness。
- 离线门禁通过后最多执行一次真实模型 + 真实 GIS/Docker 验收；固定 deadline、0 重试，结果按成功、澄清、拒绝或 provider/harness 失败分类。

状态：待开始。

## F：文档、版本和全局重规划

- 更新中文问题日志、milestones、`docs/agent-work-state.md`、`tasks/task-progress.md`、`tasks/task-state.md` 和本阶段文档。
- 运行 `git diff --check`，提交并推送一个 M309 阶段版本。
- 从产品、架构、数据、模型、部署、体验、测试七个维度规划下一阶段；不陷入某个数据集或单个问题。

状态：待开始。

## 交付顺序

`A → B → C → D → E → F`

开发期间只做必要静态/契约检查；A～D 合并后集中收口 E，测试轮次按独立失败模式合并，不随任务数量线性增加。
