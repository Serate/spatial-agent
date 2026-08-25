- [x] M279-A 完成 Planner-facing cross-Domain catalog projection
- [x] M279-B 建立 Rule/LLM Composite Planner bounded contract
- [x] M279-C 实现 resolve → plan → validate/repair → clarify/submit Application
- [x] M279-D 接入 HTTP/CLI semantic command，保持 FastAPI/stdlib 一致
- [x] M279-E Docker 定向/阶段级验收与中文记录、提交推送
- [x] M280-A 有界 Planner response compatibility normalizer
- [x] M280-B Planner evidence 与 compatibility 摘要
- [x] M280-C 离线 replay 与真实 planning probe
- [x] M280-D 真实 GIS + Economic sync/async/restart 验收
- [x] M280-E 文档、提交推送与全局重规划
- [x] 建立 `tasks/task-progress.md` 作为恢复用的进行中/最近完成子任务账本
- [ ] 每完成一个子任务，先更新 `tasks/task-progress.md`，再同步 `tasks/task-state.md` 和 `docs/agent-work-state.md`

## M281 动态 Composite 结果体验（收口中）

- [x] M281-A 完成全局能力图、Spec、Plan
- [x] M281-B 结果/View/Evidence 面向前端的公共投影
- [x] M281-C 简洁答案与结构化结果一致性
- [x] M281-D CLI/HTTP/前端/artifact 跨入口验收
- [x] M281-E Docker/browser smoke、文档、提交推送与全局重规划

## M282 开放式请求解析与受控 Composite Planner（进行中）

- [x] M282-A 完成能力图、Spec、Plan
- [x] M282-B Context contract 与 RequestFacts 聚合
- [x] M282-C Capability matching、缺失事实与结构化澄清
- [x] M282-D Planner gateway 与跨入口验收
- [x] M282-E Docker/真实验收、文档与阶段收口
- [x] M282-E 提交推送与全局重规划

## M283 开放式请求 Agent 闭环（进行中）

- [x] M283-A 全局七维度能力图、Spec、Plan
- [x] M283-B Planner gateway 收口
- [x] M283-C 开放式成功切片与跨入口恢复
- [x] M283-D 动态结果体验与阶段里程碑
- [x] M283-E 真实模型/GIS/Docker/browser 显式验收
- [x] M283-F 文档、提交推送与全局重规划

## M284 会话清空与跨入口状态一致性（已完成）

- [x] M284-A capability map、Spec、Plan
- [x] M284-B 领域中立 reset boundary 与 stale-render guard
- [x] M284-C 精简 contract/browser 回归
- [x] M284-D 文档、提交推送与全局重规划

## M285 开放式 Planner 多工具编排纵向切片（进行中）

- [x] M285-A 全局 capability map、Spec、Plan
- [x] M285-B Planner entry policy 与 source evidence
- [x] M285-C TaskPlan bridge 与至少两步 replay
- [x] M285-D Python/HTTP/async/artifact 精简跨入口验收
- [ ] M285-E Docker/live/文档、提交推送与全局重规划

## M286 中转模型 Planner 适配与能力身份稳定性（进行中）

- [x] M286-A 七维度能力图、Spec、Plan
- [x] M286-B context 精确能力身份、工具/结果提示和预算
- [x] M286-C provider 有界格式兼容与严格拒绝
- [x] M286-D 失败分类、跨入口 projection 与有限 repair lineage
- [x] M286-E 精简 Docker/live 验收、中文记录、提交推送与全局重规划

## M287 有界 Planner 修复与失败恢复（进行中）

- [x] M287-A 七维度能力图、Spec、Plan
- [x] M287-B Repair Request/Lineage contract 与错误码白名单
- [x] M287-C provider/application 一次性修复回合
- [x] M287-D 跨入口恢复与前端阶段投影
- [x] M287-E 精简 Docker/live 验收、中文记录、提交推送与全局重规划

## M288 Provider Wire-level Structured Output 能力协商（进行中）

- [x] M288-A 七维度能力图、Spec、Plan
- [ ] M288-B provider structured-output profile contract
- [ ] M288-C client/Planner wire mode adapter
- [ ] M288-D 跨入口 mode evidence 与体验投影
- [ ] M288-E 精简 Docker/live 验收、中文记录、提交推送与全局重规划
