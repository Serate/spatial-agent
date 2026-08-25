# M288 Provider Wire-level Structured Output Spec

## Objective

为 OpenAI-compatible provider 建立可替换、可观测的结构化输出模式协商，使 Planner 能选择明确支持的 wire mode；无论 mode 如何，返回结果都必须经过相同的 canonical schema、能力 allowlist、TaskPlan bridge 和 Runtime gate。

## Provider Profile

```json
{
  "schema_version": "spatial-agent.provider-structured-output.v1",
  "wire_api": "chat_completions|responses",
  "structured_mode": "json_schema|json_object|unavailable",
  "schema_enforced": true,
  "source": "config|probe|default",
  "reason_code": "..."
}
```

`structured_mode` 是 provider 能力事实，不是模型输出授权；`json_object` 只能作为明确 profile 的兼容模式，不能因此放宽应用层 `additionalProperties=false` 和 allowlist。

## Negotiation

- 配置优先；显式 live probe 可更新本地脱敏 capability receipt，不保存响应原文。
- strict `json_schema` 是默认首选；只有 profile 明确声明支持时才使用其他模式。
- 协商失败返回结构化 provider capability unavailable，不自动切换到自由文本解析。
- Planner evidence 记录 `wire_api`、`structured_mode`、`schema_enforced`、source 和有限 reason code。

## Failure and Recovery

provider transport、mode unavailable、JSON parse、schema invalid、capability invalid 和 TaskPlan policy 必须分层；只有 schema structural error 才允许 M287 的一次 repair。wire mode 失败不创建 execution run，不重复隐式探测。

## Acceptance

1. fake/replay 可验证 strict schema、json object、unavailable 三种 mode 的选择和 fail closed。
2. HTTP、async、artifact、restart 和前端看到相同 provider structured-output evidence。
3. Docker contract、compileall、architecture strict、readiness 通过。
4. 一次真实 live probe 记录 provider mode 和 Planner 结果；失败也必须安全、可解释、无 run。
