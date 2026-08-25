# M279 Composite Planner 能力图

## 阶段目标

让开放式自然语言请求可以在不写专题分支的前提下，发现已登记 Domain 能力，生成一个受约束的 Composite DAG，并交给 M278 的 `CompositeRunApplication` 执行。模型只提出候选计划，公共边界负责校验、拒绝和降级。

## 能力分层

```text
自然语言请求
  -> 有界请求事实与跨 Domain 能力目录
  -> Rule/LLM Composite Planner
  -> Composite request/DAG schema 校验与 allowlist
  -> CompositeRunApplication
  -> Composite Result / View / Evidence / lifecycle
```

| 能力 | 所有者 | 复用边界 |
|---|---|---|
| 跨 Domain catalog projection | application | `DomainRuntimeHost`、Domain catalog、capability/workflow schema |
| Composite 计划生成 | planner adapter | Rule 与 LLM 输出同一 canonical request |
| 计划安全校验 | contract/application | `normalize_composite_request`、Domain allowlist、数量/依赖预算 |
| 执行与恢复 | `CompositeRunApplication` | M278，不复制 worker、SQLite 或 artifact 状态机 |
| 结果展示 | Result/View consumer | Composite result 的动态 views，不识别 GIS/Economic 专题名 |

## 不在本阶段

- 不为某个区域、固定问句或经济/GIS 组合增加硬编码 planner 分支。
- 不保存 prompt、模型原文、密钥或未校验的工具参数。
- 不把模型内部思维链展示给用户；只保留计划来源、能力 ID、校验结果和有限 lineage。
- 不在本阶段扩展大量空间算子或引入 RAG；数据发现继续消费已有 Domain catalog/readiness。
