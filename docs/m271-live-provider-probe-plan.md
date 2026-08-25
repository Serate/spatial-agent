# M271 Plan：真实模型 Provider Probe

## 实施顺序

1. 先复用 `sanitize_provider_metrics()`，定义小接口 `run_provider_probe(client_factory, ...) -> receipt`，把请求、校验、错误分类和安全投影收在 evaluation seam。
2. 用一个稳定的 JSON schema 做最小 probe；通过 `OpenAIPlannerClient` 发送，不改变 Planner 的 TaskPlan 解析入口。
3. 增加 `scripts/live_provider_probe.py`，从本地配置读取 provider 设置，仅在显式 live 开关下运行；设置 `max_retries=0`，避免 probe 重复消耗 token。
4. 添加 fake client 的 3—4 条精简契约测试，覆盖 READY、timeout/provider error、shape error 和参数边界。
5. Docker 验证后更新恢复卡、中文问题日志、milestones，提交并推送阶段版本。

## 设计决定

- Probe 是一个独立验收 Module，不进入 `AgentRuntime.run()`；它的深度来自“最小请求接口后隐藏配置、异常、metrics 脱敏和响应校验”。
- Probe 只回答“provider 是否可用”，开放式规划仍必须通过已有 live baseline 单独验收，避免把两个失败面混在一个结论中。
- 默认保持离线；真实中转与直连不自动互换，避免产生不可审计的 provider 选择。
