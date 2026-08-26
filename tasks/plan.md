# 当前实施计划：M304 Provider-backed 规划可靠性与可恢复交互

恢复入口：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前快照、`tasks/task-progress.md` 最近记录、M304 Spec/Plan 和当前任务列出的文件。

M303 已完成：canonical Composite DAG 适配、共享 TaskPlan/binding 执行闭合、真实 Docker GIS/Economic 跨入口恢复和阶段门禁均已交付；唯一 live 结果为有界 provider timeout，未创建 run。

M304 按全局目标提升 provider-backed Agent 的可用性与可恢复交互，不把 provider timeout 误判为用户澄清或执行失败：

1. [ ] M304-A 从全局七维度冻结 provider 状态矩阵和验收边界。
2. [ ] M304-B 统一 provider deadline、配置健康、结构化响应能力和脱敏 receipt。
3. [ ] M304-C 提升真实模型形成合法 Composite 计划的可观测成功路径，保留 canonical DAG/TaskPlan/binding 唯一门禁。
4. [ ] M304-D 统一 sync/async/HTTP/Console 的规划中、澄清、失败和可重试交互投影。
5. [ ] M304-E 在 Docker 中集中运行精简门禁并进行一次显式 live。
6. [ ] M304-F 更新中文记忆、提交推送版本并再次从全局目标重规划。

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
