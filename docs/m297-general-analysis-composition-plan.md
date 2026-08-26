# M297 通用分析组合与跨类型结果闭合实施计划

本阶段遵循“全局盘点 → capability map → Spec → Plan → 连续实现 → 集中精简验收 → 文档/提交 → 全局重规划”。最大并发度保持 1；开发中只做必要静态检查，减少重复测试。

## M297-A：目录与类型边界冻结

- 盘点现有 GIS/Economic catalog、workflow、ToolRegistry、Result Registry 和数据 readiness。
- 冻结能力组合所需的公共声明字段、输入/输出 data profile、result_ref 类型规则和 `composition_invalid` reason code。
- 建立不依赖固定问句的 Replay 代表集，覆盖单能力、跨类型和事实不足三种状态。

## M297-B：通用组合校验与引用解析

- 在现有 plan completeness/execution binding seam 上增加组合级 capability、workflow、工具、引用和结果类型校验。
- 统一处理前一步结果引用、公共事实引用和数据集引用，拒绝未声明来源、循环依赖、类型不匹配和越界预算。
- 将组合状态投影到 discovery、planning evidence、View、artifact 和恢复边界。

## M297-C：少量工具的开放式组合闭环

- 优先复用现有查询、记录分析、空间算子、指标趋势和区域比较工具，验证无需新工具即可表达多个开放问题。
- 仅在存在明确通用缺口时新增一个领域中立 seam，并同步 ToolRegistry/schema/workflow/result contract。
- 让 Rule/Replay/LLM 共用同一组合规范化和 TaskPlan bridge，不增加 Domain 专用 Planner 分支。

## M297-D：跨类型 Result/View 与用户答案

- 统一 vector、raster、metrics、timeseries、document_evidence 和 composite 的结果摘要、来源、限制和可视化声明。
- 前端继续通过 projection/renderer registry 动态消费；地图、表格、指标卡、趋势图和文本结果按 data profile 选择，不按领域或工具名分支。
- 复杂结果采用结论优先、证据可展开的布局，兼容部分完成、不可用和需要澄清。

## M297-E：真实数据、恢复与显式模型验收

- 在 Docker 中执行一条 GIS + Economic 跨类型组合，核对同步/异步/artifact/SQLite/restart/HTTP 的 identity 与结果一致性。
- 对字段缺失、时间不匹配、空间范围不匹配和后端不可用各保留一个必要的负向验收，不重复调用真实模型。
- 真实模型只执行一次代表性开放请求；记录安全 receipt，不保存模型原文、prompt、密钥或原始数据。

## M297-F：阶段收口与全局重规划

- 集中运行一轮 compact contract、相邻阶段回归、compileall、architecture strict、readiness、Node/HTTP 和必要 browser/live 门禁。
- 更新中文问题日志、milestones、恢复快照、任务账本和部署/验收说明，提交并推送版本。
- 根据产品、架构、数据、模型、部署、体验、测试七维度决定下一阶段是补通用算子、扩大真实数据覆盖还是提升模型规划稳定性。

## 测试策略

- 开发阶段不为每个小改动重复运行全套测试，只执行语法、静态边界或单个失败模式检查。
- 阶段末保留一轮精简且有代表性的集中门禁；live、GIS、Docker 和浏览器只在验收确实覆盖对应风险时执行。
