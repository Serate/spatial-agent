# Spec: M279 自然语言 Composite Planner

## Objective

为 M278 的可恢复 Composite 生命周期增加一个领域中立的规划入口：给定自然语言请求，系统投影已登记 Domain 的能力、数据就绪摘要和结果类型，使用 Rule 或真实 LLM Planner 产生候选组件 DAG；候选计划必须在本地通过 Composite request contract、Domain allowlist、依赖和预算校验后，才可交给 `CompositeRunApplication`。

用户不需要预先写 `components`。未能安全确定 Domain、能力、数据范围或输出目标时，返回统一的结构化澄清/拒绝，而不是猜测或直接执行模型输出。

## Scope

### Required

1. 建立跨 Domain 的有界 capability projection，至少包含 Domain ID、capability/workflow ID、输入事实、所需数据集 readiness、结果类型和可用 View；过滤路径、原始异常、模型原文和敏感字段。
2. 建立 Planner port，Rule Planner 与 LLM Planner 都产出同一 canonical Composite request；LLM 只接收 projection 和用户请求，不接收任意运行时对象。
3. 复用 `normalize_composite_request` 校验组件 ID、Domain ID、依赖 DAG、最大组件数、请求长度和 JSON 预算；再通过 `DomainRuntimeHost` allowlist 检查。
4. 新增 transport-neutral `CompositePlanningApplication`，负责 resolve/catalog → plan → validate/clarify → submit 的生命周期投影，并把合法计划交给 M278 `CompositeRunApplication`。
5. HTTPApplication 提供一个语义命令供 CLI/HTTP/前端调用；FastAPI 和 stdlib 只做 URL 胶水。计划模式不改变 M278 已有 run/detail/recovery 语义。
6. 记录有界 `planner_source`、capability IDs、plan fingerprint、validation/clarification reason 和 repair lineage；不记录 prompt 或模型原文。

### Explicitly deferred

- LLM 自动创建新工具、修改 ToolRegistry 或绕过 Domain allowlist。
- RAG、外部搜索、实时数据抓取和新增专题算法。
- 前端专用 Composite 页面；前端只消费现有结构化 result/views，动态面板在后续阶段做完整验收。

## State and failure semantics

| 阶段 | 成功 | 可恢复失败 |
|---|---|---|
| resolve | 找到可用 catalog | `NEEDS_CLARIFICATION`：缺少范围/目标或 Domain 有歧义 |
| plan | 得到候选 Composite request | `NEEDS_CLARIFICATION`：Planner/provider 不可用或输出不完整 |
| validate | request/DAG/allowlist 全部通过 | `REJECTED` 或一次有限 repair；保留 lineage |
| submit | 返回稳定 run identity | 复用 M278 的 async/idempotency/artifact/restart |

LLM provider 失败不得伪装成规划成功；Rule fallback 只有在显式 planner 配置允许时启用，并在 evidence 中标注来源。

## Public contracts

- Input: `spatial-agent.composite-planning-request.v1`，包含自然语言 `request`、session、planner/backend、可选 bounded spatial/time context 和 execution mode。
- Candidate: bounded internal projection，包含 `components` 候选和 planner evidence；不得直接作为执行参数。
- Output: `spatial-agent.composite-planning-response.v1`，包含 status、planner source、plan/validation projection、clarification 或 `run_id`；成功时链接到 M278 detail/observability/evidence。
- Existing execution: `spatial-agent.composite-request.v1`、`composite_result.v1` 和 M278 lifecycle 保持兼容。

## Acceptance criteria

1. fake LLM 对一个同时需要 `gis` 与 `economic` 已登记能力的开放请求生成合法 DAG，并由 M278 coordinator 执行；不添加领域专用分支。
2. invalid Domain、未知 capability、依赖环、超出组件预算和缺少必需事实都在执行前结构化拒绝/澄清。
3. Rule 与 LLM planner 的合法输出经过同一 normalize/allowlist/Result/Evidence 边界。
4. provider timeout/非法 JSON 不泄露原文，能返回有限 clarification/repair lineage；M278 run 不会被创建。
5. HTTP semantic test、Docker 定向测试、compileall、architecture strict、CI/stage 通过；真实模型只做显式 live acceptance。

## Boundaries

- Always：能力目录是模型上下文唯一来源；执行只接受 canonical normalized request；每个 component 使用稳定 session/run identity。
- Ask first：新增公共 schema 版本、改变现有 Composite request/result 或引入网络/RAG。
- Never：在 Planner、HTTP 或前端复制 Composite worker；把固定自然语言样例写成业务分支；保存密钥、prompt、模型原文或未校验工具参数。
