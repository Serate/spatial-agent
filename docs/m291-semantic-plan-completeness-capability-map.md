# M291 Planner 语义完整性与能力计划完整性：全局能力图

## 阶段定位

M290 已确认 provider structured output 可用、deadline receipt 可追踪，且真实中转模型在“success 但组件为空”时会被安全拒绝。M291 不通过放宽 schema 或增加请求次数追求 live 表面成功，而是把“语义结果完整性”与“能力声明可物化”提升为通用 Agent Runtime 的明确契约。

## 七维度盘点

| 维度 | 当前基础 | M291 缺口 | 阶段产出 |
| --- | --- | --- | --- |
| 产品 | 已有澄清/拒绝状态和可读答案 | 用户难以区分 provider 语义不完整、能力不可物化和事实不足 | 统一的状态、原因和下一步 |
| 架构 | Planner、Domain workflow、TaskPlan bridge 已分层 | success、component、workflow、TaskPlan 的完整性检查分散 | 版本化 plan completeness contract |
| 数据 | GIS/Economic catalog 可发现并带 readiness | capability 声明可能缺 workflow、工具或结果类型 | catalog consistency receipt |
| 模型 | strict wire schema 与一次 repair 已有 | 模型可返回结构合法但语义不完整的 success | bounded semantic validation |
| 部署 | Docker/live probe 与 planning receipt 已有 | 语义拒绝需在 sync/async/artifact/restart 一致 | 跨入口安全 evidence |
| 体验 | 前端显示 planner/provider 摘要 | 空组件 success 的提示不够用户化 | 简洁澄清/拒绝和下一步 projection |
| 测试 | 现有 planning matrix、TaskPlan 和 provider contract | 缺少 capability→workflow→TaskPlan 的整体一致性门禁 | 一组集中 compact contract + 一次显式 live |

## 本阶段目标

- 明确 success、clarification、rejection、failure 与空组件之间的语义关系。
- 确保每个公开 capability 都能解析到已登记 workflow，并能在同一 allowlist 下物化为合法 TaskPlan。
- 对结构合法但语义不完整的 Planner 输出执行有限校验；无法修复时返回结构化澄清或拒绝，不创建 execution run。
- 保持 Rule、Replay、LLM 共享同一语义校验和 TaskPlan gate。

## 不做

- 不增加 GIS/Economic 专题工具、RAG、外部搜索或 MCP 依赖。
- 不接受未知 capability、未知 workflow、未知工具或未知结果类型。
- 不增加无限 repair、隐式重试或放宽 provider schema。
- 不把模型原文、prompt、密钥、私有路径或原始数据写入证据。

## 阶段结果

M291 已把“结构合法”与“可执行完整”分离：目录可报告 task-plan、answer-only 和 unbound；成功计划必须物化全部组件并通过统一 TaskPlan gate；组件事实不足时返回结构化澄清。真实 Composite 仍未跨域执行成功，但失败被正确保留为可恢复状态。
