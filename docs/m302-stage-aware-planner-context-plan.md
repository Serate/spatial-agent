# M302 分阶段 Planner 上下文与开放问题成功链路实施计划

## A：全局基线与阶段字段矩阵

- 盘点现有 Planner Envelope、selection evidence、component fact handoff、TaskPlan bridge 和答案生成调用点。
- 冻结四类 projection stage 的必需字段、可选字段、预算和失败状态。
- 建立一个代表性开放请求矩阵，覆盖成功、无关事实缺失、选中组件缺事实、不可用数据和 provider failure。

## B：阶段感知 Envelope

- 在公共 Runtime 增加 stage-aware projection seam；保留现有默认 Envelope 兼容读取。
- 把仅供 Runtime 诊断的完整 discovery/consistency 明细留在内部 evidence，不默认发给模型。
- 为每个阶段增加最小预算测量和私有字段过滤，超限 fail closed。

## C：选择到执行的纵向闭合

- 让 LLM/Rule/Replay 经过同一候选选择、组件事实交接、TaskPlan/DAG 和 binding 门禁。
- 对选中组件缺事实生成有界 continuation，补充后只重建必要上下文。
- 验证不相关 Domain 缺事实不会改变合法候选的执行路径。

## D：结果答案与前端投影

- 统一结构化结果、evidence 和答案引用，减少程序化模板摘要。
- 前端按阶段和结果类型展示用户可读信息，详细技术证据默认折叠。
- 保持未知结果类型和 provider failure 的通用降级，不增加领域页面分支。

## E：集中验收与交付

- Docker 集中运行阶段 contract、生命周期/binding 回归、compileall、architecture strict、Node projection 和 readiness。
- 只做一次显式 live 验收，记录脱敏状态、请求次数、重试次数、是否创建 run 和错误分类。
- 更新中文问题日志、milestones、任务账本、恢复快照和部署记忆，提交并推送阶段版本。
- 以产品、架构、数据、模型、部署、体验、测试七维度重新规划下一阶段。

## 风险控制

- 阶段投影不能成为第二套生命周期；所有执行仍由现有 binding 门禁授权。
- 为节省 token 不能删除候选 identity、事实缺口、readiness、workflow 或 result profile 等决策必需字段。
- 真实模型不稳定时记录 provider failure，不放宽 schema、不增加无界重试。

## 当前进度

- A/B 已完成：Envelope 声明并校验四类阶段；Context Builder 保存 discovery 投影；LLM 初次规划/一次结构修复分别使用 selection/repair；execution 与已有 selected component 只保留选中闭合信息。
- 已验证：阶段切换不改变 request fingerprint；readiness、workflow、result profile 和私有字段过滤保持；已有 Envelope 可安全规范化；repair 在尚未形成可信选中项时保留有界候选以支持一次结构修复。
- 下一步：C 验证 selected-component fact handoff、TaskPlan/DAG、execution binding 与阶段投影的身份一致性；随后集中完成 D/E。
