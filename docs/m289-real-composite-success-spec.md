# M289 真实 Composite Planner 纵向成功链路 Spec

## 目标

在现有公共边界上验证一个开放式、多域请求能否由真实 LLM Planner 生成合法 Composite 计划，并在 GIS/Economic local Docker 数据上完成执行、答案组合和证据恢复；若模型或数据不满足条件，返回可解释的澄清/拒绝/降级状态。

## 公共契约

1. Planner 输入只包含版本化 Request Context、能力目录、数据就绪摘要和有限请求文本。
2. Planner 输出必须经过 provider normalization、Composite schema、能力 allowlist、依赖/DAG、TaskPlan bridge 和 Runtime 权限门控。
3. 真实成功、澄清、拒绝和 provider failure 使用同一 planning evidence；wire profile 只记录模式和状态，不携带响应原文。
4. 同一 canonical request 在同步、异步、artifact 和 SQLite 重启接管后，核心 Result、Answer、View、Artifact、Evidence 保持一致。
5. 前端只消费 Composite View/Result/Planning Evidence，展示结论、组件状态、数据边界和下一步；不暴露内部思维链。

## Live case

使用一个明确但跨域的开放问题，要求模型从现有目录选择 GIS 与 Economic 已注册能力。case 必须同时声明：

- 空间范围和分析目标；
- 需要的 GIS 结果与经济指标结果；
- 允许的时间范围或在不足时触发澄清；
- 结果需要摘要、证据和可恢复 artifact。

case 的具体自然语言可在 harness 中配置，不能在 Runtime 中增加固定问句分支。live receipt 只保存状态、错误码、组件数、wire profile、token/耗时摘要、run 是否创建和恢复摘要。

## 失败语义

- context 缺失或数据未就绪：`NEEDS_CLARIFICATION` 或结构化 unavailable，不调用 execution。
- provider transport/wire 失败：保留 provider error evidence，不创建 run。
- schema/未知字段：最多复用现有一次 repair，仍失败则拒绝。
- 未知能力、非法工具、非法 DAG 或权限失败：拒绝，不通过兼容层猜测。
- 单组件数据失败：保留部分结果/降级说明，其他独立组件按现有 Coordinator 规则执行。

## 验收标准

1. 离线 replay 覆盖合法两域 DAG、缺失事实澄清、未知能力拒绝三类路径。
2. Docker 中至少有一条真实 LLM + local GIS/Economic planning/execute case，或在真实模型不稳定时留下明确安全失败 receipt；不能把 provider probe 当作 Composite 成功。
3. 同一 case 的 sync、async、artifact 和 restart evidence 通过统一 projection 对照。
4. 前端能显示用户可读的答案摘要、组件结果类型、限制和 planning/provider evidence 摘要。
5. 默认 CI 仍离线、精简且不依赖私有数据；live 仅显式运行一次。
