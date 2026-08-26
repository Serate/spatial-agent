# M302 分阶段 Planner 上下文与开放问题成功链路规格

## Objective

为 Planner 建立阶段感知的最小上下文边界：模型在发现能力、选择能力、绑定执行和有限修复时，分别获得完成当前决策所需的字段；Runtime 仍保留完整 Context 用于校验、恢复、证据和跨入口一致性。

## 契约

1. provider Envelope 必须版本化并声明 `projection_stage`，至少支持 `discovery`、`selection`、`execution`、`repair`。
2. 所有阶段共享 request fingerprint、候选 identity、readiness、workflow/result profile 和安全预算；阶段变化不得改变请求或执行 binding 身份。
3. discovery 阶段提供请求事实、候选摘要和数据/能力可用性；不携带完整 workflow binding 诊断。
4. selection 阶段提供候选对应的最小执行闭合信息；不重复发送未被候选引用的 workflow 或诊断明细。
5. execution/repair 阶段只提供已选组件、必要事实缺口、允许的修复边界和结果契约；不得让模型修改既有事实或执行结果。
6. 任何阶段超出 provider 预算必须 fail closed，并返回结构化 provider failure；不得静默截断身份、readiness 或安全约束。
7. selected-component fact handoff、TaskPlan、ToolRegistry、workflow 和 execution binding 继续使用现有严格门禁。
8. 答案生成只能引用结构化 Result/Evidence，模型不得创建事实、空间几何或统计值。

## 验收标准

1. 同一开放请求在 discovery → selection → execution 阶段的 request identity 稳定，Envelope 体积小于预算且不含私有字段。
2. 未选 Domain 的缺失事实仍为 advisory；已选组件缺事实返回 continuation，不创建 execution run。
3. 完整候选可生成合法 TaskPlan/DAG，并通过统一 execution binding。
4. Rule、Replay 和 LLM 入口共享同一阶段投影和结果契约；离线模式不访问网络。
5. 同步、异步、artifact、SQLite/restart、HTTP 和 Console 保持相同的选择、结果与 evidence identity。
6. Docker 中完成一次真实模型 + 真实 GIS/Economic 的显式验收；provider timeout、结构化澄清和成功执行分类记录。
