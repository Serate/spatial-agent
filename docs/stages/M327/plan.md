# Plan：M327 开放请求能力发现与结果质量

> 顺序：全局重规划 → Capability Map → Spec → 契约冻结 → 实现 → 最小验证 → Docker 验收 →
> 交接更新 → 全局重规划 → 提交推送。单 Agent，最大并发度 1。

## M327-A：能力描述契约

- [ ] 盘点现有 Catalog、Result profile、RequestFacts 和 readiness 字段，确定最小通用描述。
- [ ] 增加版本化 descriptor 投影：输入事实、输出类型、前置条件、证据要求和成本提示。
- [ ] 为未知字段、缺失能力和旧 descriptor 建立 fail-closed/兼容读取边界。
- 验证：一个 GIS 与一个非 GIS 能力的离线契约；不修改 Runtime 生命周期。

## M327-B：能力选择与用户可见解释

- [ ] 让 Planner context 使用有界 descriptor 摘要，而不是固定 workflow 文本。
- [ ] 记录 chosen/candidate/missing facts/selection reason 的脱敏 evidence receipt。
- [ ] 让澄清、拒绝和不可用结果复用同一选择 identity，不暴露 Prompt 或模型原文。
- 验证：开放请求、缺失事实、未知能力各一条紧凑回归。

## M327-C：跨类型结果摘要

- [ ] 定义公共摘要输入：Result completeness、typed sections、Evidence 和限制。
- [ ] 将矢量、栅格、指标和文本结果映射为统一的用户摘要块，不为 GIS 页面增加分支。
- [ ] 答案生成优先输出结论/关键发现/限制/证据来源，保留技术详情可展开。
- 验证：至少三类结果的离线 projection 与答案契约。

## M327-D：跨入口与前端接入

- [ ] CLI、HTTP、Artifact、恢复和 Console 消费同一 capability/result/evidence projection。
- [ ] 前端动态渲染能力选择和结果摘要，保留地图等 Domain View 作为可选 renderer。
- [ ] 对 planning、clarification、partial、blocked、completed 状态保持相同信息层级。
- 验证：一条 sync/async/artifact/restart 对照和一个前端结构化 projection smoke。

## M327-E：Docker 验收与阶段收口

- [ ] Docker 运行受影响紧凑测试、compileall、architecture strict、readiness。
- [ ] 进行一次显式真实模型 + Docker/GIS 开放请求；只记录脱敏成功/失败摘要。
- [ ] 更新交接文档、任务账本、中文问题日志和 document/code index。
- [ ] 从产品、Runtime、Domain、数据、模型、部署、体验和测试七维度重规划下一阶段并提交推送。

## 风险与验证门槛

| 风险 | 控制 | 验证 |
|---|---|---|
| descriptor 变成新 workflow 硬编码 | descriptor 只描述能力，不携带隐式执行分支 | descriptor/plan identity 契约 |
| 模型选择越权 | 选择后仍过 Registry、策略、权限、审批和 readiness | 负向契约 |
| 结果摘要丢失证据 | 摘要只从 typed Result/Evidence 生成 | 三类结果 projection |
| 前端重新出现 Domain 分支 | 先消费公共 block，再挂载可选 View renderer | Node/browser smoke |
| Provider 不稳定 | 默认离线，真实请求单次、有界超时、脱敏 receipt | Docker/live 验收 |
