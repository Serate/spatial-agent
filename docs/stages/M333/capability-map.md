# M333 能力地图：受控公共网页模式

## 目标

让通用 Agent Runtime 能在用户要求实时公开资料时，按服务端策略搜索并读取有限的 HTTPS 网页正文，同时保持可审计、可恢复和不持久化敏感网页内容的边界。

## 能力模块

| 模块 | 职责 | 依赖 | 交付边界 |
|---|---|---|---|
| `web-policy` | 解析模式、校验 URL、解析地址、阻断 SSRF 和危险重定向 | 设置 | `off/allowlist/public`、代理兼容、限额 |
| `web-fetch` | 通过受控 GET 获取 HTML 并提取正文 | `web-policy` | `web_fetch` 工具、正文临时上下文、安全结果投影 |
| `web-evidence` | 组合搜索来源、正文摘要和模型上下文 | `web-search`、`web-fetch` | 不把正文写入 Result、SQLite、Artifact 或公开 trace |
| `web-integration` | 接入 ReAct、答案生成、恢复、HTTP/SSE、前端和 Docker | 前三个模块 | 入口一致、失败可恢复、显式真实验收 |

## 构建顺序

`web-policy` → `web-fetch` → `web-evidence` → `web-integration`

## 统一接口

- 搜索仍返回版本化 `document_evidence` 来源记录。
- `web_fetch` 接收一个 HTTPS `url`，可选 `source`，只允许用户请求中的明确 URL 或当前 `web_search` 返回的来源 URL。
- 工具结果保存 `status`、`reason_code`、`url`、`title`、`content_hash`、`content_length`、`content_type` 和有界 `text_preview`；完整正文只进入当前进程的模型上下文。
- 所有网络效果都经过 ToolRegistry 和 WebPolicy；模型不能提供方法、请求头、Cookie、代理或任意重定向策略。
