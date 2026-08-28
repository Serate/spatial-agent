# Spec：M321 白名单网络搜索

## Objective

为受控开放 Agent 增加一个可替换的公共网页搜索能力。真实模型能够选择 `search`，
Runtime 将其物化为已登记的 `web_search` 工具调用，并把有限的来源证据交给后续决策和
最终答案。所有网络副作用都位于适配器内，默认 CI 不访问网络。

## Public contract

### Tool

工具名：`web_search`。

输入 schema：

- `query`：非空字符串，最多 512 字符。
- `domains`：可选字符串数组，最多 8 项；服务端与请求域名取交集。
- `max_results`：可选整数，范围 1～8。

输出 `document_evidence`：

```json
{
  "result_type": "document_evidence",
  "status": "ok|degraded|unavailable",
  "query": "bounded query",
  "sources": [
    {
      "title": "bounded title",
      "url": "https://allowlisted.example/path",
      "domain": "allowlisted.example",
      "snippet": "bounded snippet"
    }
  ],
  "source_count": 1,
  "allowed_domains": ["allowlisted.example"],
  "reason_code": "search_completed"
}
```

`url` 只保留 HTTPS 且已通过白名单校验的 URL；不返回 HTML、响应头、Cookie 或页面全文。

## Policy

- Provider URL 和来源 URL 均需要 HTTPS，并且 hostname 必须命中静态/环境白名单。
- 禁止 localhost、回环、链路本地、私有地址、IP literal、非 GET 请求、跨白名单重定向。
- 单次请求有连接超时、读取超时、最大响应字节数、最大来源数和总 URL 数限制。
- `domains` 是用户/模型的筛选条件，不是授权条件；空白名单或无交集直接返回
  `search_allowlist_empty`。
- 搜索结果只进入 StepRun、ReAct history 的安全摘要和 Result evidence；不进入 Prompt
  原文、运行日志或持久化的网络响应缓存。

## Runtime integration

- Runtime factory 创建可替换 `WebSearchAdapter`，通过 `ToolRegistry.register_tool()` 登记
  `web_search`；没有网络适配器时不伪造工具成功。
- ReActLoop 接收可选 `execute_search` seam。未提供时保留 M320 的结构化不可用行为，保证
  离线 fake/replay 兼容。
- `search` action 在 accepted 前校验 query、domains、max_results 和网络策略；执行使用
  `web_search` 的普通 StepRun，复用已有 retry、cancel、timeout、evidence 和结果组合。

## Testing

- Adapter contract：白名单命中、非白名单、重定向、超大响应、解析失败和网络关闭。
- ReAct contract：search → result reference/history → finish，以及 adapter unavailable。
- Runtime contract：search 只通过 ToolRegistry，事件/evidence 不含页面全文或敏感字段。
- 阶段收口只运行上述紧凑契约、相邻 ReAct/ToolRegistry 回归、compileall 和 architecture
  strict；真实公共网页只在显式 live 验收执行一次。

## Acceptance criteria

1. 真实模型可选择搜索时，能够形成合法 `web_search` StepRun。
2. 白名单来源可进入结构化 Result/evidence，非白名单永不抓取。
3. 网络不可用时返回可读、可恢复的 degraded/unavailable 结果。
4. CLI、HTTP、异步、artifact、SQLite 和前端继续消费同一 Result 契约。
