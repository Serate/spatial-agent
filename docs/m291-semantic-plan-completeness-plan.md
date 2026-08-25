# M291 Planner 语义完整性与能力计划完整性 Plan

## 完整能力包（串行）

### M291-A：语义完整性建模与目录盘点

- 固化 `plan-completeness.v1`、状态/原因码和安全 evidence 字段。
- 盘点 GIS、Economic capability、workflow、工具 allowlist、result types 的声明闭合关系。
- 为 Rule、Replay、LLM 三种 Planner 统一定义输入、校验和失败投影。

### M291-B：Planner outcome 与 completeness gate

- 将空组件 success、缺失组件身份、未知 workflow 和未声明结果类型纳入统一语义 gate。
- 保持现有 canonical request fingerprint、TaskPlan/DAG、ToolRegistry 校验，不复制 Runtime 生命周期。
- 为合法多组件计划保留 success 路径，为不完整计划生成结构化澄清/拒绝。

### M291-C：Capability → workflow → TaskPlan 一致性

- 增加领域中立 catalog consistency 校验和有界诊断 receipt。
- 让 CompositeTaskPlanBridge 在 materialize 前检查 workflow、工具和结果类型闭合，再复用 Domain preview。
- 修正目录声明不一致项，并加入可复用的 replay fixture，不新增专题分支。

### M291-D：跨入口语义恢复与用户体验

- 将 completeness/clarification/rejection evidence 接入 sync、async、artifact、SQLite/restart 和 HTTP projection。
- 前端以简洁中文展示“计划不完整/需要补充信息/能力不可用”和下一步，详细原因折叠展示。
- 保证语义拒绝永不创建孤儿 execution run，恢复时不改变原始状态和 fingerprint。

### M291-E：集中门禁、显式 live、文档与版本

- 合并运行 replay、catalog consistency、TaskPlan bridge、跨入口 contract、compileall、architecture 和 readiness 门禁。
- 只执行一次有界真实模型验收；按 success、clarification、rejection 或 provider failure 记录脱敏结果，不保存模型原文。
- 更新中文问题日志、milestones、任务账本和恢复快照，提交推送后从产品、架构、数据、模型、部署、体验、测试七个维度规划下一阶段。

## 测试策略

开发期间只做必要的语法/局部检查；M291-B～D 完成后统一运行一组按独立失败模式合并的精简门禁，不按子任务数量重复测试。

## 阶段收口结论

- M291-A～D 已完成：语义完整性、目录绑定、TaskPlan gate、跨入口 evidence 和 Console 用户摘要均已接通。
- M291-E 已完成：Python 合并门禁 **46/46**、新增状态映射回归 **6/6**、Node projection smoke、Docker compileall、architecture strict、生产 readiness 200 通过；真实 Composite 只做一次显式验收并安全澄清。
- 下一阶段 M292 转向“Planner 选择的组件如何向 Domain 传递事实并可恢复澄清”，保持同一 request fingerprint、生命周期和 evidence，不新增专题流程。
