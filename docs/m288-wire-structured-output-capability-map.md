# M288 Provider Wire-level Structured Output 能力图

## 阶段定位

M287 已完成一次有界 repair，但真实中转仍返回非法组件字段。继续增加 prompt 或 repair 次数不能从根本上解决 provider 对结构化输出协议支持不一致的问题。M288 从 provider wire adapter 和能力协商层处理该缺口，保持 Planner、Runtime、ToolRegistry 和 Domain Pack 不变。

## 七维度全局盘点

| 维度 | 当前状态 | M288 缺口 | 产出 |
| --- | --- | --- | --- |
| 产品 | 失败有结构化 lineage | 用户不知道是 provider 协议能力不足 | 可读的模型结构化输出状态 |
| 架构 | OpenAI-compatible client 支持多 wire API | Composite Planner 没有独立 wire profile/negotiation | provider-neutral structured-output adapter |
| 数据 | context/数据权限正确 | 与数据无关 | 保持数据边界不变 |
| 模型 | json object/JSON schema 兼容性可能不同 | 中转能力未被探测和记录 | 有界 provider capability receipt |
| 部署 | Docker/live probe 有 deadline | 默认配置无法表达 provider profile | 显式 live profile 与安全 fallback |
| 体验 | 可展示 rejection/repair | 缺少下一步提示 | “切换结构化输出模式/稍后重试”状态 |
| 测试 | replay 和 live 分层 | 缺少 wire mode 选择契约 | 少量 mode negotiation/replay |

## 完整任务包

1. 盘点 OpenAI-compatible wire API、`response_format`/schema 参数和现有 provider 配置边界。
2. 建立 provider profile 与结构化输出模式协商，不把 provider 名称写进 Domain/Runtime。
3. 让 Composite Planner 使用协商后的模式，仍以本地 canonical schema、allowlist 和 TaskPlan 为最终门控。
4. 将 mode、fallback、provider readiness 和失败分类接入 evidence、live receipt、HTTP/artifact/前端 projection。
5. 用脱敏 replay 覆盖 strict schema、json object、不可用和未知 profile；阶段末单次真实 live 验收。

## 不做

- 不接受任意模型字段，不删除 schema 校验，不增加 repair 次数。
- 不新增 GIS/Economic 工具、RAG、外部搜索或 MCP 运行时依赖。
- 不把中转 provider 的特殊字段散落在 Domain Pack、Runtime 或前端分支。
