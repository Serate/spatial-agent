# M321 白名单网络搜索能力图

## 目标

让默认开启的 ReAct 能够在已有本地能力不足时，受控地搜索公共网页并把来源作为
`document_evidence` 返回。网络是可替换能力，不改变 Runtime 生命周期、Result、Trace、
Artifact、SSE 或前端展示契约。

## 能力边界

| 能力 | 所属 | 输入 | 输出 | 安全边界 |
| --- | --- | --- | --- | --- |
| `web_search` | Runtime network adapter | query、可选 domains、max_results | `document_evidence` | 只允许查询；来源域名必须命中服务端白名单 |
| ReAct `search` | `agent/react` | 结构化 search action | 一个已登记的 `web_search` step | 仍经动作、参数、权限、网络策略和 ToolRegistry 门禁 |
| 来源证据 | Result/Evidence | 标题、摘要、域名、受控 URL | 有界文档来源列表 | 不保存页面全文、Prompt、密钥或模型原文 |

## 数据流

```text
ReAct search action
  -> decision schema
  -> Runtime action validation
  -> ToolRegistry.web_search
  -> SearchAdapter(query)
  -> search provider + allowlisted fetch
  -> bounded document_evidence
  -> StepRun / Result / evidence / answer
```

## 配置与降级

- `SPATIAL_AGENT_WEB_SEARCH_ENABLED` 控制能力策略，默认开启。
- `SPATIAL_AGENT_WEB_ALLOWED_DOMAINS` 是服务端白名单；请求中的 domains 只能缩小范围，
  不能扩展范围。
- `SPATIAL_AGENT_WEB_SEARCH_URL` 指定可替换搜索适配器的公共搜索入口；不配置或不在
  搜索提供方允许范围内时返回结构化 unavailable，不发起请求。
- 请求超时、重定向到非白名单、响应过大、解析失败或没有可用来源，都返回 bounded
  degraded/unavailable 结果，不把网络异常升级为任意 URL 访问。

## 不在 M321

- 不实现自动生成工具、沙箱 Python、人工审批或 MCP。
- 不把网络结果写入 GIS 专用前端分支。
- 不允许模型携带任意 URL、HTTP method、请求头、脚本或页面全文。

## 验收面

1. 允许域名可以产生有界 `document_evidence`，并保留来源摘要。
2. 非白名单域名、重定向、过大响应和网络关闭均 fail closed。
3. ReAct search 通过 ToolRegistry 形成 StepRun，并可继续下一轮或 finish。
4. 搜索失败保留结构化 degradation，不泄露 URL 之外的响应原文。
5. 默认离线契约、compileall 和 architecture strict 保持通过。
