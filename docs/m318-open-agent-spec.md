# Spec：M318-M325 受控开放 Agent Runtime

## Objective

让真实模型能够处理未预定义表达的开放式问题：先产生经过校验的结构化动作，再按中间结果
继续调用已登记工具、搜索公共网页、请求澄清或结束任务。所有动作都必须经过 Runtime、
ToolRegistry、权限、数据就绪和 Result Contract 门禁。

用户可见的是阶段进度、当前动作、来源、结果和通俗答案；不可见的是 Prompt、模型原文和
隐藏思维链。模型生成的新工具只能进入沙箱验证和人工审批流程，不能自动执行或注册。

## Public contracts

### Execution Policy

版本：`spatial-agent.execution-policy.v1`。

必需语义：`mode`、`allowed_tools`、`allowed_result_profiles`、`max_actions`、
`requires_confirmation`、`network_enabled`、`tool_proposals_enabled`。

### ReAct Decision

版本：`spatial-agent.react-decision.v1`。

动作限定为 `call_tool`、`search`、`ask_clarification`、`propose_tool`、`finish`、
`reject`。每轮只允许一个动作；动作中不能携带任意代码、未登记工具或未授权 URL。

### Evidence and events

- 沿用 `run-event.v1`，增加 ReAct 轮次事件和有限字段。
- 新增 `react-evidence.v1`，只记录动作类型、轮次、校验状态、引用、恢复和安全摘要。
- 网络输出使用 `document_evidence` Result Profile。
- 工具提案使用 `tool-proposal.v1` 和 `tool-approval.v1`。

## Product behavior

- 真实模型请求默认先进入 ReAct；简单请求可一轮结束。
- ToolRegistry 是所有工具调用的唯一入口。
- workflow 是可选执行策略；高风险 Domain 可强制 workflow 或审批。
- 网络搜索启用但受公共域名白名单、请求方法、大小、重定向、超时和总预算限制。
- Python 提案启用但先经过 Docker 无网络沙箱，审批前不能进入 Registry。
- 网络、数据、Provider 或沙箱不可用时，返回结构化 degraded/unavailable 结果。

## Project structure

```text
agent/runtime_core/       # 执行策略、生命周期和公共门禁
agent/react/              # ReAct 决策、循环和 evidence
agent/network/            # 搜索、网页抓取和来源证据
agent/tooling/            # 提案、静态校验和沙箱适配器
agent/application/        # HTTP 语义和跨入口应用接口
domains/                  # 可替换 Domain Pack 和数据适配器
tests/                    # 精简契约和阶段集成测试
scripts/                  # Docker/live/browser 显式验收脚本
docs/                     # Spec、Plan、交接和问题日志
```

## Commands

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m compileall -q agent domains scripts
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/architecture_check.py --strict
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/test_profile.py --profile ci
```

真实模型、网络搜索、真实 GIS、浏览器和工具审批只使用显式验收命令，不进入默认 CI。

## Testing strategy

- 开发期间只运行受影响的契约或静态检查。
- 阶段收口集中运行一次 Docker 精简门禁。
- Runtime、ToolRegistry、HTTP、SQLite、SSE 和恢复必须保留针对性测试。
- 真实模型每次验收最多提交一次；超时后查询已有 Run，不重复提交。
- 测试不得保存 API key、Prompt、模型原文、隐藏思维链或私有原始数据。

## Boundaries

- Always：结构化校验、权限门禁、结果类型校验、预算限制、证据脱敏、更新交接文档。
- Ask first：新增外部依赖、改变 CI、改变公开契约、改变数据挂载或审批策略。
- Never：任意网络访问、未审批工具执行、自动修改生产代码、提交密钥、删除失败测试。

## Success criteria

- 真实模型默认使用 ReAct，简单问题不会产生无意义循环。
- 未预定义问题可以组合已有能力或返回结构化澄清。
- 白名单搜索能够返回带来源的文档证据。
- 工具提案必须经过沙箱和人工确认。
- CLI、HTTP、前端、SSE、artifact 和重启恢复的核心结果与证据一致。
- 至少完成一条真实模型 + Docker/GIS 的复杂端到端验收。
