# M290 Provider Deadline 与真实 Composite 完成能力图

## 阶段定位

M289 已补齐跨状态 planning receipt、prepared plan 的跨入口执行 seam 和前端 evidence，但真实 Composite Planner 在 45 秒内超时。M290 处理的是通用 provider deadline、延迟观测和真实 Composite 完成能力，不处理 GIS/Economic 专题逻辑，也不通过增加 repair 或放宽 schema 追求表面成功。

## 七维度盘点

| 维度 | 当前基础 | M290 缺口 | 产出 |
| --- | --- | --- | --- |
| 产品 | timeout 有安全状态 | 用户缺少明确的“模型仍在处理/稍后重试”解释 | 可读 provider latency/deadline 状态 |
| 架构 | client timeout、harness deadline、async lifecycle 分散 | 总 deadline 与 provider timeout 边界需统一 | bounded deadline contract |
| 数据 | Domain catalog/readiness 正常 | 当前 timeout 不能归因于数据或模型 | 保留 context/data/provider 分层 receipt |
| 模型 | strict schema 与 token budget 已有 | 多域计划响应可能超过时间预算 | 显式 live budget 与一次请求证据 |
| 部署 | Docker/live harness 可运行 | worker timeout 后接管/清理边界需确认 | 可恢复 timeout/restart 证据 |
| 体验 | 前端可显示规划状态 | timeout 还没有结论优先的下一步 | timeout/fallback next action |
| 测试 | 精简 planning matrix | deadline、timeout、restart 缺少一组集中 contract | compact deadline + lifecycle gate |

## 不做

- 不增加领域工具、数据下载、RAG、外部搜索或 MCP 依赖。
- 不自动无限等待、重复请求或增加 repair 回合。
- 不把 provider latency 伪装成 schema 成功或执行成功。
