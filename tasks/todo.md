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
- [x] M288-B provider structured-output profile contract
- [x] M288-C client/Planner wire mode adapter
- [x] M288-D 跨入口 mode evidence 与体验投影
- [x] M288-E 精简 Docker/live 验收、中文记录、提交推送与全局重规划

## M289 真实 Composite Planner 纵向成功链路（进行中）

- [x] M289-A 全局规划与 success/clarification/rejection 验收矩阵
- [x] M289-B Planner-to-TaskPlan 纵向收口
- [x] M289-C 真实 GIS/Economic 执行与恢复对照
- [x] M289-D 答案与前端验收
- [x] M289-E 集中门禁、live、中文记录、提交推送与全局重规划

## M290 Provider Deadline 与真实 Composite 完成（进行中）

- [x] M290-A 全局 deadline/timeout 状态建模
- [x] M290-B Provider 与 harness deadline 对齐
- [x] M290-C 超时恢复与跨入口一致性
- [x] M290-D 真实 Composite 纵向验收与用户体验
- [x] M290-E 集中门禁、文档、版本与全局重规划

## M291 Planner 语义完整性与能力计划完整性（进行中）

- [x] M291-A 全局能力图、Spec、Plan 与语义状态契约
- [x] M291-B Planner outcome 与 plan completeness gate
- [x] M291-C capability → workflow → TaskPlan 一致性校验
- [x] M291-D 跨入口语义恢复、artifact 和前端用户投影
- [x] M291-E 集中门禁、显式 live、文档、版本与全局重规划

## M292 Planner 组件事实交接与可恢复澄清（已完成）

- [x] M292-A 全局能力图、Spec、Plan 与事实来源模型
- [x] M292-B 组件级 requirements 与 preview 交接
- [x] M292-C 澄清 continuation 生命周期
- [x] M292-D 前端与跨入口用户体验
- [x] M292-E 集中门禁、显式 live、文档、版本与全局重规划

## M293 多组件事实协调与可恢复 Composite 续跑（进行中）

- [x] M293-A 全局能力图、Spec、Plan 与多组件 identity 设计
- [x] M293-B 多组件 handoff 聚合与全局 continuation
- [x] M293-C 重新规划与跨入口生命周期投影
- [x] M293-D 集中精简验收与兼容修正
- [ ] M293-E 中文记录、版本交付与全局重规划

## M294 已验证计划到执行/答案/证据闭合（已完成）

- [x] M294-A 全局能力图、Spec、Plan 与 execution binding 设计
- [x] M294-B Composite coordinator 消费 validated binding
- [x] M294-C 答案、View 和 Evidence 闭合
- [x] M294-D 同步/异步/重启与真实数据验收
- [x] M294-E 中文记录、版本交付与全局重规划

## M295 全局开放式分析与数据发现闭环（已完成，待版本交付）

- [x] M295-A 全局基线与 discovery receipt 契约冻结
- [x] M295-B 领域中立 Discovery Gateway
- [x] M295-C Planner 与生命周期集成
- [x] M295-D Result/View/Evidence 与前端渐进展示
- [x] M295-E 跨领域真实数据与显式 Docker/HTTP/Node 验收
- [x] M295-F 中文记录、版本交付与全局重规划（文档待提交推送）

## M296 通用能力可执行闭合与真实跨域成功链路（已完成）

- [x] M296-A 全局基线与 execution-readiness 契约冻结
- [x] M296-B Catalog → Workflow → ToolRegistry 闭合
- [x] M296-C Planner / TaskPlan / binding 纵向接入
- [x] M296-D 真实 Docker 跨域成功与可恢复降级
- [x] M296-E 前端连续阶段与观测交付
- [x] M296-F 阶段收口与全局重规划

## M297 通用分析组合与跨类型结果闭合（已规划）

- [ ] M297-A 目录与类型边界冻结
- [ ] M297-B 通用组合校验与引用解析
- [ ] M297-C 少量工具的开放式组合闭环
- [ ] M297-D 跨类型 Result/View 与用户答案
- [ ] M297-E 真实数据、恢复与显式模型验收
- [ ] M297-F 阶段收口与全局重规划
