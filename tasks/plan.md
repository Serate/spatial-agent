# 当前实施计划：M303 开放式 LLM Composite 执行成功链路

恢复入口：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前快照、`tasks/task-progress.md` 最近记录、M303 Spec/Plan 和当前任务列出的文件。

M302 已完成：阶段化 Planner Envelope、validated execution projection、Result/Evidence/View 事实闭合和 Docker/HTTP/异步/artifact/restart/live 阶段验收均已交付并推送。

M303 按全局目标推进开放式 LLM Composite 的合法多步执行：

1. [x] M303-A 从产品、架构、数据、模型、部署、体验、测试七维度冻结状态矩阵和验收边界。
2. [ ] M303-B 将 LLM 结构化选择安全适配为 canonical Composite 请求与合法组件 DAG，不修改 Runtime 主循环。
3. [ ] M303-C 用 Rule/Replay/LLM 对照验证 TaskPlan、workflow、ToolRegistry、binding 和 Result/Evidence identity。
4. [ ] M303-D 使用真实 Docker GIS/Economic 数据完成 sync、async、artifact、SQLite/restart 跨入口验收。
5. [ ] M303-E 集中运行精简门禁和一次显式 live，按 provider/澄清/执行状态记录脱敏证据。
6. [ ] M303-F 更新中文记忆、提交推送版本并再次从全局目标重规划。

默认测试策略：开发期间只做必要静态/契约检查；阶段收口集中运行精简回归、compileall、architecture strict、Node projection、Service smoke、readiness 和一次显式 live，不为每个小改动重复测试。

---

# 历史实施计划：M299 默认 Agent 成功路径收口

恢复入口：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前快照、`tasks/task-progress.md` 最近记录、M299 Spec/Plan 和当前任务列出的文件；历史问题、milestones、全量测试和模型原文按需读取。

本阶段文档：[`docs/m299-default-agent-success-capability-map.md`](../docs/m299-default-agent-success-capability-map.md)、[`docs/m299-default-agent-success-spec.md`](../docs/m299-default-agent-success-spec.md)、[`docs/m299-default-agent-success-plan.md`](../docs/m299-default-agent-success-plan.md)。

M298 已完成：产品入口缺省为 `openai + local`，低层离线调用仍可显式使用 `rule + memory`，前端默认显示 Agent 阶段。M299 不回退默认值，聚焦让默认 Agent 在有充分事实时更容易形成可执行计划，并把澄清/不可用状态讲清楚。

1. [x] M299-A 从全局目标冻结“默认 Agent 成功/澄清/不可用”验收矩阵与最小上下文预算。
2. [x] M299-B 将 Planner-facing context 分为能力索引、选中候选和执行契约三层，减少无关目录进入模型，同时保持结构化 evidence。
3. [x] M299-C 增强通用请求事实与受控能力选择的可解释摘要，不增加区域、专题或固定问句分支。
4. [x] M299-D 让产品阶段条反映真实 planning/discovery/clarification 状态，并把“下一步怎么补充”与结构化澄清绑定。
5. [x] M299-E 在 Docker 真实数据上执行一次跨域 Replay/Rule 对照和一次显式 live；比较同步/异步、artifact/restart 的核心 identity。
6. [x] M299-F 集中运行精简门禁，更新中文问题日志、恢复账本、milestone，提交推送并按七维度全局重规划。

## M300 默认 Agent 开放问题成功率与答案体验（已规划）

- [ ] M300-A 全局能力图、Spec、Plan 与成功率/状态矩阵冻结
- [ ] M300-B 请求事实与能力选择的通用缺口盘点，保持领域包可替换
- [ ] M300-C LLM Planner 成功计划的受控组合与 provider 失败恢复
- [ ] M300-D 结构化结果到简洁用户答案的通用组合与证据摘要
- [ ] M300-E Docker 真实数据跨域验收、显式 live 与最小评测样本
- [ ] M300-F 文档、版本交付与全局重规划

默认测试策略：M300 实现期间仅做必要静态检查；阶段收口集中运行一轮 compact contract、相邻回归、compileall、architecture strict、Node smoke、readiness 和显式 live，不为每个小改动重复测试。
