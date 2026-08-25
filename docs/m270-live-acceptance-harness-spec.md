# M270 Spec：真实模型验收 Harness

## 目标

让真实模型验收在中转不可用、连接挂起、provider 超时或模型响应迟迟未返回时，能够在有界时间内返回可读的失败摘要和阶段心跳。该能力只改善验收可观测性，不把外部网络问题伪装成 GIS 或 Runtime 代码问题。

## 约束

1. 只在显式 live 命令生效，默认测试不联网。
2. 只输出 case、phase、elapsed、deadline、provider/model 的非敏感身份和稳定错误分类；禁止 prompt、请求头、API key、模型原文、完整异常和宿主路径。
3. 一个 live case 最多占用总 deadline；超时后返回 `timeout` receipt，不隐式重试或重复提交模型请求。
4. 使用 daemon worker 隔离不可控的 provider 阻塞；不修改 Runtime/Planner/ToolRegistry 生命周期，也不承诺强制终止第三方网络线程。
5. 成功结果继续使用现有 `run_live_baseline` evidence；超时结果也必须可进入 summary、error_classes 和阶段日志。

## 接口

`run_live_baseline()` 增加可选参数：

- `deadline_seconds`：整个 baseline 的有界时限；默认 180 秒；`None` 仅供兼容测试，不用于 CLI 默认。
- `heartbeat_seconds`：运行中进度回调间隔；默认 10 秒。
- `progress_callback(event)`：接收 `started/heartbeat/completed/timeout` 事件；事件只含有界安全字段。

CLI 增加：

- `--deadline-seconds`
- `--heartbeat-seconds`

## Timeout Receipt

```json
{
  "status": "FAILED",
  "error_class": "timeout",
  "phase": "case_runtime_call",
  "deadline_exceeded": true,
  "metrics": {"attempts": 1, "retries": 0},
  "passed": false
}
```

## 验收

- fake runtime 立即成功：既有 live baseline 契约不变。
- fake runtime 阻塞：在 deadline 内返回 `timeout`，主进程不继续等待。
- callback 只收到安全事件，不能看到 prompt、key、路径或模型原文。
- Docker 中运行 M270 定向、M269 相邻回归、quick/stage、compileall；不调用真实网络。
