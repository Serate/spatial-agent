# 当前实施计划：M313 实时 Agent 交互与可观测执行体验

当前阶段先在现有原生 Console 上完成实时事件、SSE、恢复和答案流；React 前端迁移仍需
另立 Goal。恢复时只读取当前快照、`tasks/task-progress.md` 最近记录和当前任务明确文件。

前置条件：HTTP、Result、View、Evidence、Trace、Artifact 和会话生命周期契约已稳定；
M313 只扩展 RunEvent 和实时读取，不重写 Runtime、Planner、ToolRegistry 或 Domain Pack。

任务包：

1. [x] RunEvent 契约、内存/SQLite 事件账本和游标恢复。
2. [x] Runtime 生命周期、异步提交、工具和终态事件发射。
3. [x] 共享 HTTP 读取语义、FastAPI SSE、Last-Event-ID 和 polling fallback。
4. [ ] 原生 Console 的实时阶段、心跳、当前动作、取消/恢复和默认收起摘要。
5. [ ] 真实模型最终答案 delta 流和完整答案 fallback。
6. [ ] Docker、浏览器、重启恢复、真实 GIS/模型显式验收与版本交付。

---

当前任务：M313 已完成，正在进行阶段交付收口与提交推送。React 阶段待 M313 版本交付后再从
项目全局另立 capability map、Spec、Plan 和 Goal，不与实时事件改造耦合。

默认测试策略：开发期间只做必要静态/契约检查；阶段收口集中运行 M313 精简事件契约、
HTTP/SSE、Node/browser smoke 和构建检查，不为每个小改动重复测试。

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
