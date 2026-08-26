# M301 Planner-first 开放问题解析规格

## Objective

当产品同时启用多个 Domain 时，某个无关 Domain 的缺失事实不得在 Planner 选择能力之前阻断整个请求。系统应先完成领域中立的候选发现和受控规划；只有选中的组件缺少执行必需事实时，才生成字段级澄清。

## 术语与状态

每个 Domain 的事实投影增加有界 readiness 语义：

- `complete`：当前 Domain 声明的候选要求已满足。
- `partial`：已有可用于候选选择的事实，但至少一个候选的可选/后置字段缺失。
- `missing`：没有足够事实判断该 Domain 的候选，但仍可将安全的目录摘要提供给 Planner。
- `unavailable`：Domain 或数据目录明确不可用，不能被 Planner 当作可执行能力。

上下文预算分为两层：内部 Composite Context 默认上限为 256 KiB，用于执行校验、恢复和证据；provider-facing Planner Envelope 默认上限为 96 KiB，只携带规划所需的有界投影。两者不得因为共享一个常量而互相阻断。

顶层 `clarification.state=required` 只在没有任何可供安全选择的候选，或用户已选组件的必需事实缺失时产生。仅因为未选 Domain 的事实缺失，不得返回顶层 `request_facts_missing` 阻断。

## 处理契约

1. Context Builder 继续调用 Domain-owned `extract_request_facts`、`discover` 和 requirements projection；不在公共层解析领域词。
2. Context Builder 将每个 Domain 的 readiness、候选和缺失字段放入安全 envelope；候选不足时可返回有界目录摘要，但必须保留 `available/execution_ready`。
3. Planner 可以选择已登记且 `available=true` 的候选；选择不要求所有启用 Domain 都是 `complete`。
4. Planner 选择后，TaskPlan bridge、component fact handoff、workflow、ToolRegistry schema 和 execution binding 继续执行现有严格门禁。
5. 若所选组件事实不足，返回 `component_facts_required`/等价版本化澄清与 continuation；不得创建 execution run。
6. 若 provider 失败，返回 M300 定义的 planning `FAILED`、`failure.v1` 和重试动作；不得伪装成事实澄清。
7. 同一 request fingerprint、component identity、binding fingerprint 和 evidence 在同步、异步、artifact、重启和前端 projection 中保持一致。

## 安全边界

- `partial`/`missing` 是给 Planner 的观察事实，不是执行授权。
- 内部 Context 可以保留恢复和证据所需的重复投影，但模型 Envelope 不应默认携带仅用于诊断的完整 binding、违规明细或运行时原文；后续可按 discovery、selection、execution 阶段进一步裁剪。
- 不把模型选择的 capability ID、workflow ID 或工具名直接作为用户主文案。
- 所有 readiness、缺失字段、next action 和错误码均有长度/数量上限，并过滤私有路径、密钥和模型原文。
- 默认测试和 CI 保持离线精简；真实模型、真实 GIS、Docker、浏览器只走显式验收。

## 验收标准

1. GIS 请求在 GIS + Economic 同时启用时，不因 Economic 无关事实缺失而在 Planner 前失败；最终只执行已选且 ready 的能力。
2. Economic 请求在同样的多领域配置下具有对称行为；不得写 GIS/Economic 特判。
3. 真正缺少已选组件必需事实时，返回结构化澄清、缺失字段和 continuation，且不创建 run。
4. 完整跨领域请求仍能生成合法多组件 TaskPlan/DAG，并经过同一 execution binding。
5. 不可用数据、provider 失败、事实澄清和执行失败在状态、证据和用户动作上可区分。
6. Docker 精简 contract、compileall、architecture strict、Node projection、readiness 和一次显式 live receipt 能证明上述边界。
