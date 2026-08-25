# M292 Planner 组件事实交接与可恢复澄清：全局能力图

## 阶段定位

M291 证明模型可以选出结构合法的组件，但 Domain preview 仍可能因组件所需事实不足而请求澄清。M292 处理 Planner → Domain 的事实交接、组件级澄清和同一请求的恢复续跑，目标是让开放式多领域请求从“能选能力”推进到“能以最小补充信息继续执行”。

## 七维度盘点

| 维度 | 当前基础 | M292 缺口 | 阶段产出 |
| --- | --- | --- | --- |
| 产品 | 已有结构化澄清和全局 request facts | 用户不知道缺少的是哪个组件的什么事实 | 组件级、可操作的中文澄清 |
| 架构 | Context、Planner、TaskPlan、Domain workflow 已分层 | preview 重新推断事实，交接字段不够明确 | versioned fact-handoff contract |
| 数据 | Domain 自己提取事实并检查 readiness | Planner 选择后的约束未统一传入 Domain | 有界事实/约束投影 |
| 模型 | LLM 选择已登记 capability | 模型无法可靠知道每个组件需要补充的字段 | capability/workflow requirements projection |
| 部署 | sync/async/restart/evidence 可恢复 | 澄清后续请求可能丢失原 fingerprint 或组件选择 | clarification continuation receipt |
| 体验 | 前端能展示需要补充信息 | 缺少组件、字段、来源和下一步的分层展示 | 通用澄清 View |
| 测试 | 已有 planning matrix 与跨入口 contract | 缺少“澄清→补充→同一计划继续”的集中验收 | compact continuation gate |

## 不做

- 不增加专题数据、RAG、外部搜索、MCP 或模型 repair 回合。
- 不把 Domain 私有字段或原始 prompt 直接暴露给 Planner/前端。
- 不为经济、GIS 或某个行政区增加专用澄清分支。
