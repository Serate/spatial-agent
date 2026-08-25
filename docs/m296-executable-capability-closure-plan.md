# M296 通用能力可执行闭合与真实跨域成功链路实施计划

本阶段按一个完整能力包串行实施，合并契约、实现、集成、显式验收、文档和交付准备；开发中减少重复测试，阶段收口统一验证。

## M296-A：全局基线与 execution-readiness 契约冻结

- 从产品、架构、数据、模型、部署、体验、测试七个维度盘点 M295 receipt 到实际 execution 的缺口。
- 复用 discovery、TaskPlan completeness、ToolRegistry、workflow catalog 和 execution binding；只定义一个新的 readiness seam，避免第二套生命周期。
- 固定 readiness 状态、reason code、fingerprint、预算和脱敏投影；为当前任务建立恢复账本和明确文件清单。

## M296-B：Catalog → Workflow → ToolRegistry 闭合

- 让已发现 candidate 的 workflow、允许工具、输入 schema、result type 和 plan mode 可以被统一验证。
- Domain Pack 只通过声明补齐可执行闭合；公共层不识别 GIS/Economic 能力 ID。
- 区分 answer-only、workflow-unbound、data-unavailable 和 schema-invalid，不把 catalog 命中当作执行许可。

## M296-C：Planner / TaskPlan / binding 纵向接入

- Rule、Replay、LLM 共用 readiness 结果；完整请求进入同一个 TaskPlan/DAG/completeness/binding 链。
- 对事实不足和 readiness 失败复用 M293 continuation；对计划修复保持一次有界回合和 repair lineage。
- 确认 Planner 不会因重试、恢复或不同入口重新选择另一组能力。

## M296-D：真实 Docker 跨域成功与可恢复降级

- 使用现有真实 GIS 与可追溯 Economic 数据构造事实完整的跨域验收请求，不把文件名或地区判断写进公共流程。
- 验证同步、异步、artifact、SQLite/restart、HTTP 和前端 View 的结果/evidence/binding parity。
- 对数据缺失、readiness unknown、字段不匹配和后端不可用分别执行一次必要的显式对照；不重复调用 live provider。

## M296-E：前端连续阶段与观测交付

- 将 readiness、计划闭合、执行、结论、限制和证据投影到通用 Console projection；不新增领域面板。
- 只显示结论优先的用户信息，计划和工具细节放在可展开 evidence；不显示 prompt、模型原文、token 或私有路径。
- 更新 HTTP/CLI/Artifact/恢复文档，使验收者能复现一条完整链路。

## M296-F：阶段收口与全局重规划

- 集中运行一个 compact contract、相邻 M295/M294 回归、compileall、architecture strict、readiness、必要 Node/HTTP 和一次显式 Docker/live 验收。
- 更新中文问题日志、milestones、任务账本和恢复快照，提交并推送版本。
- 根据七维度证据决定下一阶段是扩展通用算子组合、补 Economic 数据链路还是提升真实模型成功率，不按单个数据细节决定方向。

## 验证节奏

实现期间只运行局部语法/静态检查；M296-B～E 合并后统一执行阶段门禁。默认测试保持离线、精简、可重复；真实模型、GIS、Docker、HTTP 和浏览器只在验收风险确实涉及时显式执行。
