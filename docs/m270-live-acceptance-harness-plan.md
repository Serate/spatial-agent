# M270 Plan：真实模型验收 Harness

## 实施顺序

1. 先写 bounded call、heartbeat 和 timeout receipt 的最小契约。
2. 将 `run_live_baseline` 的单个 case 包在 daemon worker 中，以总 deadline 控制，不重写 Runtime。
3. CLI 只负责把安全 progress event 打到标准输出，并提供 deadline/heartbeat 参数。
4. Docker 使用 fake provider 验证成功、超时、回调字段和 summary；真实 provider 只在显式人工验收中启用。
5. 更新中文恢复卡与问题日志，提交并推送 M270 版本，再按全局目标规划真实 LLM 开放式多步验收。

## 不做

- 不修改 `AgentRuntime.run()`、Planner、ToolRegistry、GIS Adapter 或生产 HTTP 默认值。
- 不在超时后自动创建第二个 run。
- 不把中转失败转成成功降级结果。
