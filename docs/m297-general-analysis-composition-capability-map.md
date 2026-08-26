# M297 通用分析组合与跨类型结果闭合能力图

## 阶段定位

M296 已证明“能力发现 → execution readiness → TaskPlan/binding → Docker 执行”可以跨 GIS 与 Economic 闭合。M297 的全局目标是把这条链路从“已登记能力可以执行”推进到“开放问题可以组合少量通用能力”，让 LLM 的灵活性体现在能力选择、数据类型判断和步骤组合上，而不是继续增加固定问句分支。

本阶段不新增第二套 Runtime、Planner 或生命周期，也不引入 RAG。GIS、Economic 仍只是验收载荷；公共层只处理声明、事实、引用、结果形态和生命周期。

## 七维度全局盘点

### 产品

- 用户可以围绕区域、时间、对象和目标提问，不需要知道工具名称或预设模板名称。
- 系统能把“查数据、筛选、聚合、比较、空间关系、趋势”组合成一条可读的分析过程。
- 输出先给结论和关键数据，再按需展开数据来源、方法、限制和完整证据。

### 架构

- 继续复用 RequestFacts、Discovery、TaskPlan/DAG、ToolRegistry、execution binding 和统一生命周期。
- 能力目录声明 requirements、输入/输出 data profile、workflow 和 evidence 需求；公共 Runtime 不识别领域 ID。
- 结果引用必须显式声明来源和类型，禁止通过工具名称或字符串约定隐式传递。

### 数据与分析

- 优先盘点并复用现有 `range_query`、`record_analysis`、`spatial_operation`、指标趋势/比较等少量工具。
- 只在现有工具无法表达通用组合时增加领域中立的分析 seam；不为单一区域、单个数据集或 GDP 写专用算子。
- 数据集 manifest、字段、时间范围、空间参考和覆盖状态通过 bounded readiness/evidence 进入规划。

### 模型工程

- Rule/Replay/LLM 共享同一能力目录和计划契约；模型只能选择已注册且 execution-ready 的能力。
- 模型负责提出组合和依赖，Runtime 负责事实补全、schema 校验、引用解析、权限和执行绑定。
- 失败时区分事实不足、能力不可用、引用/类型不匹配、provider 失败和执行失败；不依赖增加 repair 次数制造成功。

### 部署与恢复

- 同一组合计划在同步、异步、artifact、SQLite/restart 和 HTTP 中保持 request/discovery/plan/binding identity。
- Docker 继续作为 GIS、真实数据、compile、architecture 和 readiness 的默认验收环境；生产镜像变更后必须 build/recreate。

### 体验

- Console 只消费通用 Result/View/Evidence projection，按 vector、raster、metrics、timeseries、document_evidence、composite 等形态动态展示。
- 阶段轨迹显示“理解 → 发现 → 规划 → 校验 → 执行 → 总结 → 证据”，不暴露 prompt、模型原文、私有路径或内部推理。
- 结果缺失或部分完成时，明确告诉用户缺什么、影响什么以及如何继续。

### 测试与交付

- 阶段按完整能力切片组织多个连续实现任务；开发中只做静态检查，阶段收口集中运行一次 compact contract、相邻回归和必要 Docker/HTTP/live/browser 门禁。
- 默认测试保持离线、精简、可重复；真实模型与真实 GIS 只做显式验收，不进入 CI。

## 本阶段边界

- 不引入 RAG、知识库问答、自由联网搜索或未登记数据下载。
- 不复制 GIS/Economic 的生命周期，不在 Runtime 或前端增加领域分支。
- 不以增加工具数量为目标；先证明现有少量通用工具可以被目录和 Planner 组合。
