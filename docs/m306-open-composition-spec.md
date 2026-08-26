# Spec：M306 通用开放请求与多组件组合

## 目标

在现有 Agent Runtime 生命周期和 M305 provider receipt 不变的前提下，提升开放式请求形成合法多组件计划的成功率。用户可以提出未预定义的跨数据类型问题；系统应从已登记能力中选择、分解、建立 typed 依赖并在信息不足时返回结构化澄清。

## 用户与成功行为

- 用户不需要知道工具名、workflow ID 或内部领域实现。
- 对明确请求，Planner 能返回一个由已登记能力组成的有界组件图；每个组件有稳定 identity、请求、依赖、输入引用和 required 状态。
- 对信息不足请求，系统指出缺失事实和受影响组件，不创建 execution run。
- 对未知能力、非法依赖、数据不就绪或不满足结果契约的计划，系统 fail closed，并保留可读原因和有限恢复动作。
- 对合法计划，所有入口都使用同一 TaskPlan/DAG、ToolRegistry policy、workflow 和 execution binding；结果按结构化 Data Profile/Evidence 汇总为简洁答案。

## 公共契约

1. `RequestFacts`、能力候选、数据 readiness、组件图和 `typed input reference` 必须保持版本化、可投影和可恢复。
2. 组件输入只能引用已声明的上游 `component_id` 与受支持的 Result/Data Profile；不能引用 prompt、路径、任意字段或模型原文。
3. canonical component graph 必须满足唯一 ID、无环依赖、依赖先行、required 语义和组件数量上限。
4. 所有组件必须通过能力目录、Domain workflow、TaskPlan/DAG、ToolRegistry 和 execution binding；未闭合组件图不得创建 run。
5. `CanonicalPlanReceipt` 只在完整执行闭合后为 `executable`；`PlannerAttemptReceipt` 继续记录阶段、预算、repair 和用户动作。
6. Result composition 只消费 Result Registry 的结构化结果和 Evidence，不按 GIS、Economic 或工具名写前端分支。

## 组件边界

### request-capability-bridge

输入是请求事实、数据就绪和能力目录；输出是候选能力、缺口、选择原因和最小 Planner context。缺失事实区分 `required`、`advisory` 和 `unavailable`，不能将 provider failure 伪装为事实缺失。

### component-composition

输入是 Planner 的受限结构化候选；输出是 canonical component graph。模型可以选择能力和声明依赖，但不能返回 workflow、工具参数、任意路径或执行授权。结构错误最多进行一次 repair。

### execution-closure

以已有 Domain preview/Workflow 和公共 TaskPlan bridge 物化每个组件，验证 DAG、allowlist、Result type 和 binding identity；失败在创建 run 前结束。

### result-composition

消费多组件 Result、Data Profile、ViewSpec 和 Evidence，按组件状态汇总成功、部分完成和失败，保留来源与限制；用户答案简洁，详细 trace/receipt 可展开。

## 状态与恢复

| 情况 | 状态 | 创建 execution run | 恢复动作 |
| --- | --- | --- | --- |
| 候选充分且组件图合法 | `PLANNED` | 通过全部闭合后才创建 | 提交/确认执行 |
| 某组件事实不足 | `NEEDS_CLARIFICATION` | 否 | 补充事实后按 fingerprint 续接 |
| 未知能力、非法图或不支持输入 | `REJECTED` | 否 | 调整问题 |
| provider/预算/结构化响应失败 | `FAILED`（planning） | 否 | retry 或检查配置；不自动重复 live |
| 已创建 run 后部分组件失败 | `PARTIAL`/`FAILED`（execution） | 是 | 查看已完成结果并恢复 |

## 测试策略

- 默认 Docker 测试保持精简：新增契约覆盖合法单组件、合法多组件、typed input、澄清、非法图、Result composition 和安全投影。
- 阶段收口统一运行相邻 Composite/lifecycle 回归、compileall、architecture strict、Node projection、Service smoke、生产 HTTP/artifact/restart 对照。
- 真实 GIS/Economic 数据只用于显式验收；真实模型最多一次，固定 deadline/0 retry，不保存 key、prompt、模型原文或私有路径。

## 边界

- 始终：先经 canonical contract 和 Registry，再进入执行；所有跨入口共享结构化结果和 evidence。
- 需要确认：新增外部依赖、改变既有 schema 语义、修改默认 provider 或扩展数据下载范围。
- 禁止：提交密钥、绕过 ToolRegistry/binding、为单一区域或固定问句添加流程分支、用 replay 结果伪装真实模型成功。

## 验收标准

1. 至少一个未预定义的跨数据类型请求可由 Planner 形成合法多组件图，并通过 TaskPlan/DAG、ToolRegistry、workflow 和 binding。
2. 同一 canonical 计划经 CLI/HTTP/同步/异步/artifact/restart 后，组件 identity、结果类型、Evidence 和动作一致。
3. 缺失组件事实、未知能力、非法依赖和不支持输入分别产生结构化状态，且不创建错误的 execution run。
4. 多种 Result/Data Profile 可被动态汇总，前端不依赖 GIS 专用分支，用户先看到简洁结论与限制。
5. Docker 离线门禁通过，并有一条显式真实模型 + 真实 GIS/Docker 验收；live 的 success、clarification 或 provider failure 均如实记录。

## 未决项

- 下一阶段实现前，具体选择哪一个已有 GIS + Economic/record 能力组作为最小多组件验收样本；不影响公共契约和模块边界。
