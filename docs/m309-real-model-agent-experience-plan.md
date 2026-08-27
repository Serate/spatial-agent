# M309 真实模型开放组合与默认 Agent 体验实施计划

## A：模型计划结果矩阵与全局基线

- 从 M308 的 3+ 组件闭环出发，冻结真实模型/Replay 的成功、澄清、非法计划、有限修复、provider failure 和执行失败矩阵。
- 盘点当前 Planner Envelope、provider receipt、canonical plan receipt、TaskPlan/DAG 和 execution binding 的公共 identity，确认 run 创建边界。
- 为阶段契约保留最小脱敏回放样本，不保存模型原文或 prompt。

状态：已完成。

- 结果：冻结 success、needs_clarification、rejected、provider_failure、有限 repair 和执行失败的有界状态矩阵；补齐无 metrics 客户端的调用状态与 retryable 兜底；不改变执行授权边界。
- 验证：Docker M309-A 精简契约 **4/4** 通过。

## B：真实模型到可执行计划的受控闭合

- 让模型只能从 Catalog 选择能力，并通过阶段化 Envelope、schema、计划完整性、DAG、ToolRegistry、workflow 和 execution binding 门禁。
- 补充有限 repair/clarification 的统一状态和 lineage；修复失败必须 fail closed，不能隐式降级为 Rule 成功。
- 使用一组紧凑契约验证 success、clarification、rejection 和 provider failure 不会互相伪装。

状态：已完成。

- 结果：模型提示补充通用多目标拆分原则；3+ 组件响应仍通过 capability allowlist、canonical DAG 和现有执行门禁；无 metrics provider 的调用状态已可被 receipt 正确表达。
- 验证：Docker M309-A/B 相关契约与 M305/M287 相邻回归 **18/18** 通过。

## C：默认 Agent 的可感知体验

- 检查产品默认的模型/本地 GIS 路径，确保默认配置和阶段投影表达真实状态，不让测试默认值污染产品路径。
- 让用户优先看到结论、关键指标、限制和下一步；计划、轨迹和证据按需展开。
- 统一“补充事实、重试模型、确认计划、查看结果”等动作的结构化语义，不增加领域专用页面分支。

状态：已完成。

- 结果：聊天摘要只投影结构化答案的 `summary/headline` 或明确字符串；失败展示按公共错误平面给出通用中文提示，不暴露内部对象字段。
- 验证：Docker 前端构建与 Node Console Result Projection smoke 通过。

## D：跨入口恢复与一致性

- 对照 sync、async、HTTP、View、artifact、SQLite/restart 的 plan/binding/result/answer/evidence identity。
- 覆盖活动状态、provider 失败、局部组件失败和重启接管，确保已完成事实不丢失、未验证计划不执行。

状态：已完成。

- 结果：复用 M308 跨入口验收，确认 planner/result/answer/evidence 公共 identity 在同步、异步、HTTP、View、artifact 和 SQLite/restart 中保持一致。
- 验证：Docker 三组件验收中 `sync_async_same`、`http_view_same`、`artifact_view_same`、`evidence_same`、`restart_view_same`、`restart_evidence_same` 全部为 `true`。

## E：Docker 阶段验收与一次显式 live

- 从当前工作区重建 Docker 镜像并强制重建服务，集中运行本阶段契约、相邻回归、compileall、architecture strict、Node projection、Service smoke、HTTP/artifact/restart 和 readiness。
- 离线门禁通过后最多执行一次真实模型 + 真实 GIS/Docker 验收；固定 deadline、0 重试，结果按成功、澄清、拒绝或 provider/harness 失败分类。

状态：已完成。

- 阶段门禁：重建 Docker 镜像并强制重建服务后，M309/M308/M303/M305 精简契约 **31/31**，compileall、architecture strict、Node projection、Service smoke、跨入口验收、真实 GIS 三组件验收和生产 HTTP acceptance 全部通过；`/health/ready` 为 `ready`。
- 诊断修复：真实模型曾返回结构化计划，但在 GIS `raster_metadata` 组件的 TaskPlan preview 阶段因 Domain workflow 缺少 `dataset` 事实而被拒绝。新增最小 Replay 回归并修复 Domain-owned resolver 从请求事实填充唯一数据集；对同时指定 DEM/土地利用的歧义请求，通用需求模式 `one` 直接返回结构化澄清。
- 显式 live：本阶段唯一一次真实模型调用已在修复前使用；provider 请求成功，但计划预览以 `taskplan_component_preview_failed` 结束，0 组件、未创建 execution run。由于 live 预算已用完，修复后的成功由脱敏 Replay 和真实 Docker GIS 验收证明，不把修复后的 Replay 冒充真实模型成功。

## F：文档、版本和全局重规划

- 更新中文问题日志、milestones、`docs/agent-work-state.md`、`tasks/task-progress.md`、`tasks/task-state.md` 和本阶段文档。
- 运行 `git diff --check`，提交并推送一个 M309 阶段版本。
- 从产品、架构、数据、模型、部署、体验、测试七个维度规划下一阶段；不陷入某个数据集或单个问题。

状态：已完成。

- 已记录本阶段故障、根因、修复和预防措施；未保存 API key、prompt、模型原文、私有路径或原始数据。
- 已创建 M310 全局能力图、Spec 和 Plan，下一阶段聚焦“开放请求的能力选择与数据/语义闭合”，不新增单一区域或固定问句分支。
- 交付前检查：`git diff --check`、敏感信息检查和版本提交/推送均纳入本阶段收口。

## 交付顺序

`A → B → C → D → E → F`

开发期间只做必要静态/契约检查；A～D 合并后集中收口 E，测试轮次按独立失败模式合并，不随任务数量线性增加。
