# M270 能力地图：真实模型验收 Harness

```text
live baseline CLI
  └─ bounded case runner
       ├─ provider/runtime call (daemon boundary)
       ├─ heartbeat callback（仅阶段、耗时、case id）
       ├─ total deadline
       └─ sanitized failure receipt
              ├─ planner/provider/network/timeout 分类
              ├─ no prompt/raw response/key/path
              └─ existing result/evidence summary

offline tests / fake provider ───────────────┘
Runtime、Planner、ToolRegistry、Domain、生产 HTTP 主链路保持不变
```

## 边界

- Harness 只负责显式 live 验收的限时、进度和安全摘要，不改变 Runtime 的业务 deadline。
- 外部调用在 daemon worker 中运行；超时后主线程返回结构化 receipt，不等待卡住的 provider 线程。
- 默认 CI 不启用网络；真实模型、真实 GIS 和浏览器仍是显式路径。
