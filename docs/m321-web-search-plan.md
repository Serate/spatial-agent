# M321 白名单网络搜索实施计划

状态：已完成。恢复入口为 [`docs/agent-work-state.md`](agent-work-state.md)，短账本为
[`tasks/task-progress.md`](../tasks/task-progress.md)。

## 任务包

### M321-A：契约与配置

- [x] 建立能力图、Spec、Plan 和 M321 交接入口。
- [x] 固定 `document_evidence` 输出、网络配置和结构化降级码。
- [x] 增加环境变量示例，保持默认网络策略与 CI 隔离。

### M321-B：搜索适配器

- [x] 实现标准库搜索/网页解析适配器和 allowlist URL 校验。
- [x] 加入超时、响应大小、来源数量、HTTPS、重定向和私网地址保护。
- [x] 只投影标题、摘要、域名、URL 等有界来源证据。

### M321-C：Runtime/ReAct 接入

- [x] 通过 ToolRegistry 登记 `web_search`，让 search action 物化为 StepRun。
- [x] ReActLoop 注入 `execute_search` seam；保持未提供适配器时的离线降级。
- [x] 复用现有 Execution Policy、取消、重试、Trace、Result 和 SQLite/artifact。

### M321-D：紧凑验证与交付

- [x] 增加 adapter、ReAct、Runtime 和安全投影的最小契约测试。
- [x] Docker 集中运行 M321、相邻回归、compileall、architecture strict 和 readiness。
- [x] 保留显式真实公共网页验收入口；本阶段因白名单/Provider 未配置未出网，已验证空白白名单 fail closed。
- [x] 更新交接、任务账本、中文问题日志（仅记录新问题），提交推送并全局重规划 M322。

## 阶段结果

- `WebSearchAdapter` 使用标准库完成 HTTPS、域名白名单、私网/IP literal、重定向次数、
  响应字节、来源数量和 HTML/JSON 解析限制；输出只保留 `document_evidence.v1` 来源摘要。
- Runtime factory 在构造 Planner 前登记 `web_search`，真实模型能看到该工具契约；ReAct `search`
  经由普通 `web_search` StepRun 执行，继续复用取消、重试、事件、Result 和恢复边界。
- Docker M321 + M320 + M318 **30/30**，compileall、architecture strict、smoke、readiness **200** 通过。
- 未配置白名单时实际 opener 调用次数为 0；未执行真实公共网页请求，也未保存网页全文、Prompt、
  模型原文、密钥或私有路径。真实联网验收留到配置明确后的 M325。

## 固定约束

- 单 Agent、最大并发 1；实现和测试使用 Docker。
- 默认允许 search action，但服务端白名单是授权边界；无白名单不得网络访问。
- M321 不实现工具生成、审批或 MCP；不新增 GIS 专用分支。
