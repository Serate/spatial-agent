# Plan：M333 受控公共网页模式与网页正文读取

> 单 Agent，最大并发度 1；每个子任务先更新热状态，代码修改优先，测试遵循最小充分原则。

## M333-0：阶段初始化

- [x] 建立 capability map、Spec、Plan、handoff。
- [x] 切换 `docs/agent-work-state.md`、`tasks/current-state.md` 和任务账本。
- [x] 固定默认 `allowlist`、显式 `public`、不持久化正文和沙箱无网络约束。

## M333-A：网页策略与配置

- [x] 新增 `WebAccessPolicy`，统一 `off/allowlist/public` 模式和安全 URL 投影。
- [x] 增加 DNS 地址解析检查，阻断私网、回环、链路本地、保留地址和 IP 字面量；检查显式端口和凭据。
- [x] 让 `web_search` 复用共享策略，保持 M321 旧配置兼容。
- [x] 增加设置和 `.env.example`/生产 Compose 的公共模式、代理说明。
- 验证：M333 公共策略离线契约测试 + M321 搜索回归通过。

## M333-B：网页读取与安全投影

- [x] 新增 `WebFetchAdapter` 和 `web_fetch` ToolRegistry 定义。
- [x] 只允许用户明确 HTTPS URL 或当前搜索结果来源；只读 HTML，限制正文大小、字符数、重定向和内容类型。
- [x] 使用标准 HTMLParser 提取标题和正文，移除 script/style/noscript/form 等非正文节点。
- [x] 输出安全投影和临时正文句柄；不写入 SQLite、Artifact、Trace 或 evidence。
- 验证：成功 HTML、来源边界、SSRF、危险重定向、超限和不可读页面的紧凑测试通过。

## M333-C：Runtime、ReAct 和答案集成

- [x] 将 `web_fetch` 登记到 Factory、通用能力目录和 ReAct 工具目录。
- [x] 让搜索结果来源可安全地成为下一步 fetch 输入；模型上下文只携带有界临时正文和来源元数据。
- [x] 答案生成优先使用网页证据，声明来源范围和过期/不可用限制；恢复时重抓失败必须结构化降级。
- [x] 保证 HTTP/CLI/SSE/轮询/Artifact 的持久化投影不包含正文。
- 验证：离线 ReAct 多步搜索、读取、回答、恢复和事件投影回归通过；答案上下文存在绝对大小兜底。

## M333-D：Docker、真实验收与交付

- [x] 使用 Docker 验证代理环境变量、`public` 配置、服务 readiness 和沙箱无网络边界。
- [x] 执行一次真实模型 + 真实公共 HTML 页面验收；只记录脱敏状态、来源域名、字符数和哈希。
- [x] 更新中文问题日志、模块索引、当前状态、阶段 handoff 和文档索引。
- [x] 运行最小阶段门禁，提交并推送版本，进行产品/Runtime/Planner/Domain/部署/测试全局重规划。

## 阶段验收记录

- 本机：M333 紧凑回归 `11/11`。
- Docker：M333 + M321 + M320 紧凑回归 `43/43`；`compileall`、`architecture_check.py --strict`、服务 readiness `200` 通过。
- 真实验收：Docker `public` 模式 + 真实模型 + 真实公共 HTML 页面为 `COMPLETED`；1 个 `web_fetch` 步骤完成，规划和答案生成成功。
- 安全边界：网页正文只保留在当前 Run 临时上下文；SQLite、Artifact、HTTP 结果和 RunEvent 仅保留结构化安全投影。

## 风险与回退

- 搜索 Provider 不可用：返回 `unavailable`，不伪造网页证据；仍允许模型回答不依赖实时事实的问题。
- DNS 解析异常：fail-closed；不以域名白名单替代地址安全检查。
- 正文提取质量不足：保留标题、URL、摘要和失败原因，答案明确说明正文不可用。
- 重启后临时正文消失：允许在同一策略 URL 上重新抓取，失败则返回可恢复的部分结果。
