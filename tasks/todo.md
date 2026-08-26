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

## M297 通用分析组合与跨类型结果闭合（已完成）

- [x] M297-A 目录与类型边界冻结
- [x] M297-B 通用组合校验与引用解析
- [x] M297-C 少量工具的开放式组合闭环
- [x] M297-D 跨类型 Result/View 与用户答案
- [x] M297-E 真实数据、恢复与显式模型验收
- [x] M297-F 阶段收口与全局重规划

## M298 默认 Agent 模式与阶段可见性（已完成）

- [x] M298-A 产品默认选择边界
- [x] M298-B FastAPI/stdlib 产品入口接入
- [x] M298-C Composite 顶层选择继承
- [x] M298-D 前端 Agent 阶段默认可见
- [x] M298-E Docker/live/文档、版本与全局重规划

## M299 默认 Agent 成功路径收口（已完成）

- [x] M299-A 全局基线、success/clarification/unavailable 矩阵与上下文预算
- [x] M299-B 分层 Planner context 与统一投影预算
- [x] M299-C 选择/澄清 evidence 与可恢复摘要
- [x] M299-D 阶段体验与跨入口恢复投影
- [x] M299-E Docker 真实数据、Replay/Rule 对照与显式 live
- [x] M299-F 集中门禁、文档、版本与全局重规划

## M301 Planner-first 开放问题解析（已完成）

- [x] M301-A readiness 契约与 Planner-first 事实投影
- [x] M301-B Context/目录/discovery 与 provider Envelope 分层预算
- [x] M301-C 选中组件门禁、兼容澄清合并与精简验收
- [x] M301-D 文档、版本交付与全局重规划

## M302 分阶段 Planner 上下文与开放问题成功链路（已完成）

- [x] M302-A 全局字段矩阵与阶段契约
- [x] M302-B discovery/selection/execution/repair 最小 Envelope
- [x] M302-C 选择、事实交接、TaskPlan 与 binding 纵向闭合
- [x] M302-D 结构化结果、答案和前端 evidence 投影
- [x] M302-E Docker 真实跨域验收、文档、版本与全局重规划

## M303 开放式 LLM Composite 执行成功链路（已完成）

- [x] M303-A 从全局七维度冻结 LLM Composite 成功/澄清/拒绝/不可用矩阵
- [x] M303-B 收敛模型输入与输出的通用能力选择和合法 DAG 契约
- [x] M303-C 验证 Replay/Rule/LLM 共享 TaskPlan、binding、Result 和 Evidence 边界
- [x] M303-D 用真实 Docker GIS/Economic 数据执行一次跨域 sync/async/artifact 验收
- [x] M303-E 集中运行精简门禁、一次显式 live，并记录 provider 失败或成功证据
- [x] M303-F 更新中文项目记忆、提交推送并按全局目标重规划

## M304 Provider-backed 规划可靠性与可恢复交互（已规划）

- [ ] M304-A 从产品、架构、数据、模型、部署、体验、测试七维度冻结 provider success/timeout/clarification/rejection/execution 矩阵
- [ ] M304-B 统一 provider deadline、配置健康、结构化响应能力和脱敏 receipt，不改变 Runtime 执行门禁
- [ ] M304-C 提升真实模型形成合法 Composite 计划的可观测成功路径，保持 canonical DAG 与有限 repair 边界
- [ ] M304-D 让同步、异步、HTTP、Console 对规划中/澄清/失败/重试动作提供一致的用户交互投影
- [ ] M304-E 在 Docker 中运行精简阶段门禁并进行一次显式 live，比较 provider receipt 与离线 Replay 结果
- [ ] M304-F 更新中文文档、提交推送，并依据七维度全局盘点继续规划下一阶段
