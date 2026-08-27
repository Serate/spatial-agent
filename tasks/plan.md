# 当前实施计划：React 前端迁移（下一 Goal，尚未开始）

当前 Agent Runtime Goal 已完成。React 阶段需另立 Goal；恢复时只读取当前快照、
`tasks/task-progress.md` 最近记录和 React 阶段明确列出的文件。

前置条件：HTTP、Result、View、Evidence、Trace、Artifact 和会话生命周期契约已稳定；
React 只改变前端实现与体验，不重写 Runtime、Planner、ToolRegistry 或 Domain Pack。

建议任务包：

1. [ ] React shell 与现有 Console 页面并行运行，确认路由、静态资源和部署入口。
2. [ ] 将对话、会话选择、清空/新建、阶段轨迹接入现有 HTTP API。
3. [ ] 将结构化 Result/View/Evidence 动态映射为通用结果组件，不按领域分支。
4. [ ] 接入地图、栅格、指标、趋势、来源证据和 artifact 下载视图。
5. [ ] 保留错误、澄清、异步轮询、恢复和 provider 状态的用户投影。
6. [ ] 完成一次浏览器验收与精简前端契约，再决定是否删除旧 Console。

---

当前任务：无。下一步应先创建 React 阶段的 capability map、Spec、Plan 和 Goal，
再开始实现；不在本次已完成 Goal 中混入 React 改造。

默认测试策略：开发期间只做必要静态/契约检查；阶段收口集中运行精简浏览器验收、
HTTP contract 和构建检查，不为每个小改动重复测试。

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
