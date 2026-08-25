# M274 Spec：Domain Selector Provider 兼容性与自动路由

## 目标

让自动 Domain 路由在 OpenAI-compatible 中转上可用，同时保持“模型只能选择已注册身份”的安全边界。Provider 只负责返回 JSON object；Domain Selector 在应用侧继续校验状态、Domain、capability 和候选数量。

## 范围

- `OpenAIDomainSelectorAdapter` 复用现有结构化客户端，但不强制 provider 使用复杂 `json_schema` 响应格式；传输层使用兼容性更高的 JSON object 模式。
- `ModelDomainSelector` 继续对模型输出执行完整的 allowlist、状态和请求指纹校验；provider 不能通过未注册身份。
- Economic Domain 的请求提示由 Domain 自己声明指标别名，使离线 catalog fallback 能区分 Economic 与通用 Indicators。
- 复用现有 `DomainRoutingApplication`、DomainRuntimeHost、Runtime、Result 和 Evidence；不增加工具，不修改公共生命周期。

## 验收

1. 默认离线 selector 对包含 `gdp_total`/GDP 别名和明确经济语义的请求选择 `economic`；只有语义不足时才返回结构化 ambiguity，不误执行 `indicators`。
2. Model selector adapter 向结构化客户端传递 schema 供应用校验，但以兼容 JSON object 方式调用 provider；未知身份、坏状态和 provider 错误仍安全 fallback。
3. Docker 中真实模型、全新 session、`--domain auto` 的 Economic 请求选择 `economic`，完成已有 Economic 工具链并保留 routing evidence。
4. 真实 provider 失败时不会暴露响应体、密钥或请求内容；fallback reason 仍是有界错误码。
5. 默认测试、quick、stage 和 architecture guard 离线通过；真实自动路由只通过显式 live 命令验收。

## 非目标

- 本阶段不实现一次请求同时执行 GIS 与 Economic 的 Composite Domain；该问题需要独立的跨 Domain 计划/结果生命周期设计。
- 不为某个固定问句添加 Runtime、Planner 或前端分支；指标别名只属于 Economic Domain 的声明式请求提示。
