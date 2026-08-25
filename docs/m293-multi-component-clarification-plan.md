# M293 多组件事实协调与可恢复 Composite 续跑 Plan

本阶段依据 [`docs/m293-multi-component-clarification-capability-map.md`](m293-multi-component-clarification-capability-map.md) 和 [`docs/m293-multi-component-clarification-spec.md`](m293-multi-component-clarification-spec.md) 执行。

## 完整能力包（串行）

### M293-A：多组件 handoff 聚合

- 定义 `composite-fact-handoff.v1` 的组件集合、状态、缺失字段和 bounded projection。
- 复用 M292 的 requirements/source/known facts 逻辑，避免复制 Domain 解析；保持组件顺序和 selection fingerprint 稳定。
- 明确“全部 ready / 部分 required / 全部 required”的统一状态映射和未创建 run 规则。

### M293-B：全局 continuation 与重新规划

- 将 continuation 从单组件扩展为按 `component_id` 分组的补充事实，保留 M292 单组件 token 兼容。
- 对组件集合、请求指纹、Planner selection、字段白名单、类型和过期时间做 fail-closed 校验。
- 补充后统一重建 context → 重新选择/规划 → completeness/repair → TaskPlan/DAG；不复用旧计划绕过门禁。

### M293-C：跨入口生命周期接入

- 接入 HTTP `composite_plan` 的 prepare/execute、同步/异步提交和既有 artifact/SQLite/restart 边界。
- 让 planning evidence、continuation safe projection、Composite View 和 Console 共享同一组件状态。
- 前端显示组件名称、缺失字段、补充进度和计划状态，不显示 token、工具 schema 或模型细节。

### M293-D：兼容与集中验收

- 用一个 compact contract 覆盖成功、部分缺失、补充后成功、未知字段/组件和身份不匹配；复用相邻 Planner/TaskPlan 回归，不复制测试例。
- Docker 重建后统一运行 compact contract、相邻回归、compileall、architecture strict、readiness 和一次必要的 HTTP projection 检查。
- 如真实 provider 可用，只做一次有界 live；区分 provider、事实缺失、TaskPlan 和数据后端失败。

### M293-E：阶段交付与全局重规划

- 更新中文问题日志、milestone、短账本、恢复快照、阶段清单和 Goal 执行约束。
- 提交并推送版本，记录本地 commit 与远端 push 两个状态。
- 从产品、架构、数据、模型、部署、体验、测试七个维度重新规划下一阶段，不因单个 Domain 数据问题改变主线。

## 依赖与风险

- M293-A/B 必须先确定公共 identity，C 才能接入跨入口；D/E 统一收口，不拆成更多微阶段。
- 多组件 token 过大风险：限制组件、字段、字符串和总字节预算；不把完整 context 写入 token。
- 模型重新规划可能改变组件集合：默认拒绝集合漂移并保留 lineage，不自动替用户删除或新增组件。

## 验证节奏

开发期间仅做必要快速检查；A～C 完成后集中运行一组 compact contract 和阶段级门禁。测试数量以独立失败模式为上限，不随 A～E 任务数量线性增加。
