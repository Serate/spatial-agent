# Plan：M326 开放式 ReAct 稳定交付

> 顺序：全局重规划 → Spec → 依赖审计 → 公共 Runtime 实现 → 最小契约验证 → Docker/live 验收 →
> 交接更新 → 版本提交。单 Agent，最大并发度 1。

## M326-A：ReAct 增量动作与 workflow 策略解耦

- [x] 追踪真实 run 中合法首动作与后续动作被拒绝的完整公共边界，不读取模型原文。
- [x] 将开放式 ReAct 的增量计划校验改为使用通用 Execution Policy 与 Domain 能力 allowlist；
  workflow/template 仅在明确选择时施加蓝图约束。
- [x] 保留 ToolRegistry schema、依赖、权限、审批、数据 readiness、结果类型和动作预算门禁。
- [x] 增加一个最小契约，证明合法多步增量可执行、策略错误仍 blocked。

## M326-B：统一部分结果与停止原因

- [x] 为 ReAct evidence 和公共 Result 投影增加完成范围、已完成动作数、停止原因和可重试性。
- [x] 统一模型规划失败、动作校验失败、工具失败和数据不可用的部分/阻塞映射。
- [x] 保证 SQLite、artifact、轮询和 SSE 恢复不丢失停止原因与 evidence。

## M326-C：答案质量与用户可读性

- [x] 更新答案生成输入投影，使其能识别完整、部分和阻塞结果。
- [x] 完整结果输出简洁结论；部分结果列出已完成事实和缺失范围，不使用“已完成全部分析”等误导语。
- [x] 前端只消费结构化完整性与限制字段，默认展示结论，详情区展示证据和停止原因。

## M326-D：跨入口与真实验收

- [x] CLI、HTTP、异步、SSE、轮询、artifact、SQLite 重启和前端使用同一 Result/Evidence 投影。
- [x] Docker 离线运行受影响紧凑契约、compileall、architecture strict 和 readiness。
- [x] 显式真实模型 + Docker/GIS 运行一个多步请求和一个不同输出形态请求；只记录安全摘要。

## M326-E：收口与重规划

- [x] 更新 `docs/agent-work-state.md`、`tasks/current-state.md`、`tasks/task-progress.md`、中文问题日志
  和本阶段 handoff。
- [x] 更新 document/code index；不重复运行无关历史测试。
- [x] 阶段验收后从产品体验、Runtime 架构、Domain 扩展、数据、模型、部署和测试七个维度重规划。
- [x] 提交并推送一个阶段版本；不提交真实数据、密钥、Prompt 或模型原文。

## 最小验证矩阵

| 风险 | 验证 |
|---|---|
| ReAct 增量校验 | M320/M326 紧凑契约 |
| 搜索与工具边界 | M321/M322 受影响契约 |
| 状态与恢复 | M323/M324 受影响契约 + artifact/restart |
| 代码边界 | compileall + architecture strict |
| 真实链路 | 显式 Docker/GIS/live，仅一次或按失败原因决定 |
