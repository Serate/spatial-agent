# M282 开放式请求解析能力图

## 阶段目标

把现有 Domain Pack 的 RequestFacts、能力发现和 Composite Planner 接成一条公共入口，让用户提出未预定义的跨领域问题时，系统能够先理解请求、发现候选能力，再决定执行、澄清或拒绝；不为某个地区、专题或问句新增专用流程。

## 能力边界

| 模块 ID | 责任 | 依赖 |
|---|---|---|
| `request-context` | 聚合各 Domain 的 RequestFacts、实体、任务、数据需求和约束，生成有界公共上下文 | Domain Pack contract |
| `capability-matching` | 将请求上下文与已注册能力、数据就绪和工作流候选关联，生成可读候选/缺失事实 | `request-context`、Capability Catalog |
| `planner-gateway` | 让 Rule/LLM Planner 消费同一上下文并输出 canonical Composite Plan；保留澄清、拒绝和有限 repair | `capability-matching`、Composite Planner |
| `open-query-acceptance` | 验证自然语言开放请求经过 CLI/HTTP/异步/artifact/前端得到一致计划、状态、答案和证据 | `planner-gateway`、M278/M281 |

构建顺序：`request-context` → `capability-matching` → `planner-gateway` → `open-query-acceptance`。

## 全局不变量

- Runtime、ToolRegistry、生命周期和 Composite Result 不因请求解析而重写。
- 模型只能选择能力目录中的 `domain_id/capability_id`，不能发明工具、数据集、字段或事实。
- RequestFacts 是 Domain-owned extraction 的结果；公共层只做有界聚合，不增加 `gdp`、`road` 等专题字段。
- 缺少信息、多个候选、数据不可用和模型异常都返回结构化状态，不静默猜测。
- 默认测试离线精简；真实模型、真实 GIS、Docker 和 browser 只作为显式验收路径。
