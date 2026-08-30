# Spec：M333 受控公共网页模式与网页正文读取

## Objective

面向通用 Agent Runtime 增加受控公共网页能力，使“最近的 AI 新闻”“某公开政策页面的要点”等开放请求能够在配置允许时得到基于网页证据的回答。系统必须在网络不可用、页面不适合读取或地址不安全时返回明确降级，而不是声称获取成功。

## Tech Stack

- Python 标准库 `urllib`、`html.parser`、`socket`、`ipaddress`。
- 现有 ToolRegistry、ReAct、Result、SQLite/Artifact、SSE 和 Docker Compose。
- 不引入浏览器自动化，不执行 JavaScript，不新增运行时网络依赖。

## Configuration

- `SPATIAL_AGENT_WEB_MODE=off|allowlist|public`，默认 `allowlist`。
- `off`：不注册网络工具。
- `allowlist`：保持现有行为，仅访问服务端配置的 Provider 和域名白名单。
- `public`：允许服务端配置的 Provider 和被授权的 HTTPS 公共来源，但仍阻断私网、回环、链路本地、保留地址、IP 字面量、认证 URL 和危险重定向。
- `SPATIAL_AGENT_WEB_ALLOWED_DOMAINS` 在 `allowlist` 中继续作为来源边界；`public` 不要求预先列出所有来源域名，但 Provider 仍必须由服务端配置。
- `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 由容器网络栈处理；安全地址判断不能因为代理配置而关闭。

## Project Structure

- `agent/network/web_policy.py`：网络模式、URL 和地址策略深模块。
- `agent/network/web_search.py`：已有搜索适配器，迁移到共享策略。
- `agent/network/web_fetch.py`：网页抓取、HTML 正文提取和 `web_fetch` 工具。
- `agent/runtime_factory.py`：按模式登记工具。
- `agent/react/`、`agent/runtime_core/`、`agent/answer_generation.py`：安全地传递临时网页上下文。
- `tests/test_m333_web_public.py`：紧凑离线契约测试。
- `docs/stages/M333/`：能力地图、规格、计划和交接。

## Public Interface

### `WebAccessPolicy`

策略接口接收候选 URL 和来源上下文，返回已规范化的 URL 或结构化拒绝原因。它不发起网络请求。策略必须检查 scheme、凭据、端口、域名/IP、DNS 解析结果和模式边界。

### `web_fetch`

```json
{
  "name": "web_fetch",
  "input_schema": {
    "type": "object",
    "required": ["url"],
    "properties": {"url": {"type": "string", "maxLength": 2048}},
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["schema_version", "status", "result_type", "url", "reason_code"]
  }
}
```

成功时返回有界标题、正文预览、正文长度和哈希；正文全文由当前运行上下文暂存，不进入持久化 evidence。

## Safety Boundaries

- Always：所有模型 URL 经过 ToolRegistry schema 校验和 WebAccessPolicy；只发起 GET；限制超时、响应字节、正文字符、重定向次数和单次来源数；输出安全 reason code。
- Ask first：新增依赖、放宽协议、允许登录/Cookie、改变默认模式、把正文写入持久化存储。
- Never：访问 `file://`、`http://`、私网/回环/保留地址、IP 字面量或认证 URL；执行 JS、解析 PDF、下载附件、发送 Cookie/Authorization；把完整网页正文、Prompt 或模型原文写入 SQLite、Artifact、Trace 或公开 evidence。

## Testing Strategy

- 默认只运行 `tests/test_m333_web_public.py` 和受影响的 M321/M320 契约测试。
- 使用 fake opener、fake DNS resolver 验证成功、越界、重定向、超限和 HTML 提取；不依赖外网。
- Docker 只做阶段门禁和配置/服务 smoke；真实模型+真实公网页面为显式验收，不进入默认 CI。

## Success Criteria

1. 默认 `allowlist` 行为和 M321 回归保持一致。
2. `public` 模式能读取允许的 HTTPS HTML 页面，并拒绝 SSRF、凭据 URL、危险重定向和超限响应。
3. ReAct 能看到并调用已登记的 `web_fetch`，失败时保留结构化降级，不伪造来源。
4. 最终答案能使用当前运行的网页正文，但持久化结果只包含安全投影。
5. CLI、HTTP、SSE、恢复和 Docker 对网络状态的核心结果一致。

## Open Questions

- 首版不承诺任意搜索 Provider 可用；Provider 仍由服务端配置，网络不可达时必须显示可理解的降级。
