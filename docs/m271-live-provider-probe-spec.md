# M271 Spec：真实模型 Provider Probe

## 目标

在运行昂贵的 GIS/经济多步 live 验收前，用一次最小的、结构化 JSON 请求确认 provider、模型、wire API 和响应解析链路可用。Probe 只验证外部模型接入，不把 provider 可达性误判为 Runtime、Planner、ToolRegistry 或 GIS 能力已经验收。

## 范围

- 复用现有 `OpenAIPlannerClient` 和 `load_openai_config()`，不新增第二套 HTTP 客户端。
- 通过显式 CLI 运行，默认测试、quick/stage/CI 不联网。
- 单次请求、`max_retries=0`、可配置连接超时和有界输出；失败返回稳定分类，不抛出原始 provider 异常。
- Receipt 只保留 provider/model/wire_api、状态、错误分类、延迟、token 使用和响应 shape；不保留 prompt、请求头、key、模型原文、URL 查询串或宿主路径。

## 非目标

- 不证明模型能理解 GIS 请求、选择能力、生成合法 TaskPlan 或完成真实数据分析；这些仍由 live baseline 的后续 case 验收。
- 不修改 Runtime 默认 planner、Domain Pack、ToolRegistry schema、数据目录或前端。
- 不在 provider 失败时自动切换直连、中转或另一个模型；路径差异必须由用户显式配置并分别记录。

## Receipt 契约

```json
{
  "schema_version": "spatial-agent.live-provider-probe.v1",
  "execution_mode": "live_model_probe",
  "status": "READY",
  "error_class": "none",
  "response_shape_valid": true,
  "metrics": {
    "provider_error": {"class": "none"},
    "latency": {"status": "valid"},
    "token_usage": {"total_tokens": 0}
  }
}
```

`status` 只有 `READY` 或 `FAILED`；`error_class` 使用现有安全 taxonomy（如 `timeout`、`network`、`rate_limited`、`provider_transient`、`response_shape`、`none`）。

## 验收

1. fake client 返回规定 JSON 时，receipt 为 READY，且 metrics 经过现有脱敏投影。
2. fake client 阻塞/抛出 provider 异常时，在 probe timeout 内返回 FAILED，不泄露异常内容。
3. 非 object、缺少 `status=ready` 或多余字段的响应归类为 `response_shape`。
4. CLI 只有显式 `--allow-network` 和 `SPATIAL_AGENT_LIVE_OPENAI=1` 才运行；退出码与 receipt 状态一致。
5. Docker 运行 M271 定向测试、M270 相邻测试、compileall、architecture strict 和 quick/stage；不调用真实网络。
