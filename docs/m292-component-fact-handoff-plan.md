# M292 Planner 组件事实交接与可恢复澄清 Plan

## 完整能力包（串行）

### M292-A：事实交接契约与来源模型

- 固化 `component-fact-handoff.v1`、字段类型、来源、敏感字段过滤和 continuation identity。
- 盘点现有 RequestFacts、workflow constraint specs、capability requirements 和 clarification projection 的重叠边界。
- 让 Planner context 只消费有界公共 requirements，不把 Domain 私有实现扩散到 Runtime。

### M292-B：组件级 requirements 与 preview 交接

- 将已选 capability/workflow 的公共必需字段投影到 component handoff。
- Domain preview 优先消费 handoff 中的已知约束，缺失时返回可定位的组件字段，而不是重新猜测。
- 保持所有结果进入同一 canonical TaskPlan/DAG 和 ToolRegistry gate。

### M292-C：澄清 continuation 生命周期

- 建立 clarify → user supplement → re-resolve → re-plan → validate 的统一 continuation seam。
- 校验原 fingerprint、组件身份、字段类型和版本；过期或篡改 continuation fail closed。
- sync/async/HTTP/artifact/restart 复用同一状态和 evidence，不创建孤儿 run。

### M292-D：前端与跨入口用户体验

- 前端按组件显示“缺什么、为什么需要、怎么补充”，隐藏内部 schema、工具和模型信息。
- 结果 projection 同时保留原计划摘要、补充事实、下一步和限制；补充后清晰显示计划是否重新验证。
- 为多组件部分澄清设计有界的交互状态，不复制领域页面分支。

### M292-E：集中门禁、显式 live、文档与版本

- 合并运行 continuation、fingerprint、TaskPlan gate、跨入口 projection、compileall、architecture 和 readiness 门禁。
- 仅执行一次有界真实模型验收；区分模型澄清、Domain 数据不可用和用户事实缺失。
- 更新中文问题日志、milestones、恢复账本并提交推送，再从全局七维度规划下一阶段。

## 测试策略

开发期间只做必要的局部检查；M292-B～D 完成后按独立失败模式合并为一组 compact continuation contract，阶段收口统一执行，不因子任务增多而增加重复测试轮次。
