# M306 通用开放请求与多组件组合实施计划

## A：全局基线与能力缺口

- 以 M305 的 planner/canonical receipt 为基线，盘点现有 RequestFacts、Capability Catalog、Data Profile、workflow 和 Result Registry 的组合缺口。
- 冻结模块边界、组件图字段、typed input reference、结果合并规则和状态动作矩阵；不扩充专题工具菜单。

状态：已完成。公共组合契约拒绝非布尔 required、后置依赖和内部 Result 路径；组件输入只允许受支持的 data kind。

## B：请求事实到能力候选

- 压缩 Planner-facing 能力和 readiness 投影，保留候选选择所需信息，过滤诊断、路径和无关 Domain 细节。
- 让候选缺口能定位到组件和事实字段，并与既有 continuation/fingerprint 交接；provider 失败仍走 provider failure。

状态：已完成。候选级缺失事实不会跨候选合并，discovery 和 Planner Envelope 保留安全的候选/字段定位。

## C：开放组件图与 canonical 执行闭合

状态：已完成。

- 统一 Rule/Replay/LLM 的组件图规范化、typed input、依赖排序和一次 repair 边界。
- 使用真实 `CompositeTaskPlanBridge`、TaskPlan/DAG、ToolRegistry policy、Workflow 和 `CanonicalPlanReceipt` 做合法/非法矩阵。

结果：组件图在进入 TaskPlan 物化前再次通过公共 composition 校验；required、依赖顺序、输入引用和组件身份均 fail closed，未创建第二套执行授权。

## D：通用结果组合与用户投影

状态：已完成。

- 将多组件 Result/Data Profile/Evidence 合并成结构化但简洁的答案、限制、View 和 artifact 引用。
- 同步、异步、HTTP、Console 和 restart 只消费公共 evidence；前端不新增领域或工具名判断。

结果：复用既有 Composite Result/View/Answer/Evidence 链路，结构化结果保持单一事实来源，未知或部分结果安全降级。

## E：Docker 阶段验收

状态：已完成。

- 重建并强制重启 Docker，集中运行 M306 契约、相邻 Composite/lifecycle 回归、compileall、architecture strict、Node projection、Service smoke、生产 HTTP、artifact/restart。
- 离线门禁全部通过后，最多进行一次真实模型 + 真实 GIS/Docker 验收；固定 deadline/0 retry，不因 timeout 重发。

## F：文档、版本和全局重规划

状态：已完成。

- 更新中文问题日志、milestones、历史恢复卡、任务账本、快照和 README/部署引用（如有需要）。
- 阶段完成后提交并推送一个版本；基于七个全局维度重新决定下一阶段，不陷入单一数据集调参。

结果：M306-E Docker 门禁、真实数据跨入口和唯一一次真实模型验收均通过；本阶段记录已收口，下一阶段为 M307 Runtime 生命周期与传输边界收敛。

## 交付顺序

`A → B → C → D → E → F`

开发中只做必要的静态/契约检查；测试按独立失败模式合并到 E，避免每个小任务重复执行完整回归。并行任务保持当前串行执行设置。
