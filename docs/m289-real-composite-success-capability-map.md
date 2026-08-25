# M289 真实 Composite Planner 纵向成功链路能力图

## 阶段定位

M288 已证明 provider wire-level structured output 能力可被显式描述、严格请求并安全记录，但简单 provider probe 成功不等于真实模型能够生成合法的多域 Composite 计划。M289 从全局目标出发，验证并补齐一条真实的开放式纵向链路：自然语言请求 → 能力/数据上下文 → LLM Composite Planner → canonical DAG/TaskPlan → GIS 与 Economic 执行 → 结果组合、答案和证据恢复。

本阶段不新增针对洪山区、固定问句或单一数据集的流程，不修改 Runtime、ToolRegistry 和生命周期核心边界；新增行为只能落在 Planner adapter、能力目录投影、验收 harness 或公共 Result/Evidence seam。

## 七维度盘点

| 维度 | 当前基础 | M289 缺口 | 阶段产出 |
| --- | --- | --- | --- |
| 产品 | 可提交开放式 Composite 请求，能安全澄清/拒绝 | 用户还缺少一条稳定的真实多步成功体验 | 结论优先的真实 Composite case 与失败说明 |
| 架构 | Rule/Replay/LLM 共享 context、canonical plan、TaskPlan bridge | 真实 Planner 到执行的成功/澄清/拒绝矩阵尚未作为统一验收 | provider-neutral planning harness 与跨入口契约 |
| 数据 | GIS/Economic Domain Pack、local Docker 数据和 readiness 已存在 | 需要证明模型只选择已就绪能力，数据不足可恢复 | 数据目录、能力身份、readiness evidence |
| 模型 | wire profile、schema 校验和一次 repair 已有 | 真实多组件输出仍可能非法或选择未知能力 | 一次 live Composite probe，失败分类不放宽门控 |
| 部署 | Docker、SQLite、artifact、HTTP、异步和 readiness 已有 | 缺少同一真实计划的 sync/async/restart 对照 | 可重复的 Docker acceptance harness |
| 体验 | Composite View、前端动态 projection 和可读答案已有 | provider/planner 证据与用户结论的关联需要确认 | 前端显示结构化计划/证据摘要，不显示模型原文 |
| 测试 | 离线 replay 和阶段门禁精简 | 成功、澄清、拒绝和恢复需要一个集中矩阵 | 一个 compact contract + 一个跨入口验收 + 一次 live |

## 能力依赖

```text
真实请求与 Domain context
        ↓
provider wire profile + LLM Composite Planner
        ↓
response/schema/allowlist/TaskPlan gates
        ↓
GIS + Economic canonical DAG
        ↓
sync / async / artifact / SQLite restart
        ↓
Composite Result / View / Answer / Evidence
```

## 不做

- 不增加 RAG、外部搜索、新数据下载或 MCP 运行时依赖。
- 不通过增加 repair 次数、接受未知字段、猜测能力或绕过 TaskPlan 来追求 live 成功。
- 不把真实模型 prompt、原文响应、密钥、私有路径或原始数据写入仓库。
