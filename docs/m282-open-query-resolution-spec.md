# Spec: M282 开放式请求解析与受控 Composite Planner

## Objective

让 Agent 面对未预定义的问题时，能够从自然语言进入统一的请求上下文和能力发现流程，再由 Rule/LLM Planner 选择已注册能力，形成可校验的 Composite Plan；信息不足时给出用户可理解的澄清，能力冲突或不可用时安全拒绝。

用户与成功结果：用户只需提出一个开放式空间/指标问题；系统返回候选能力、已识别事实、缺失信息和下一步状态，或者生成合法 Composite Plan。系统不把“调用过模型”当作成功，也不把固定问句匹配当作通用能力。

## Assumptions

1. Domain Pack 已实现 `extract_request_facts()`、`discover()` 和 capability catalog；本阶段复用这些接口。
2. M279 Composite Planner 的 canonical request/plan schema 与 M278 lifecycle 不变，只增加公共 planner context 的版本化投影。
3. 不引入 RAG、外部搜索、实时抓取、自动生成工具或新的 GIS/Economic 专用工具。
4. 当前 goal 串行实施；真实模型输出不稳定时必须保留安全澄清/拒绝，不扩大任意字段兼容面。

## Public Contract

新增 `spatial-agent.composite-request-context.v2`，至少包含：

- `request_fingerprint`、有界 `request_summary`；
- `domain_contexts[]`：Domain ID、facts 摘要、discovery 状态、候选能力、workflow 候选和数据就绪状态；
- `capability_index[]`：可选能力的稳定 ID、结果类型、数据 profile、可用性和缺失数据；
- `clarification`：`not_required/required/ambiguous/unavailable`、缺失事实和用户可读提示；
- `evidence`：来源为 `domain_facts/catalog/discovery` 的脱敏摘要和 context fingerprint。

公共上下文不包含原始模型响应、prompt、密钥、绝对路径、完整几何、原始异常或未选中能力的私有字段。

## Commands

```text
Docker build:
docker compose -f docker-compose.prod.yml --env-file .env.production build spatial-agent

Focused tests:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest tests.test_m282_open_query_resolution tests.test_m279_composite_planner tests.test_m281_dynamic_composite -v

Verification:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent sh -lc "python -m compileall -q agent production_api.py serve_api.py && python scripts/architecture_check.py --strict"
```

## Project Structure

- `agent/composite_request_context.py`：公共上下文 builder 与 schema/预算校验。
- `agent/application/composite_planning.py`：接入 context builder，保持 resolve/plan/validate/clarify/submit 生命周期。
- `agent/composite_planner.py`：Rule/LLM 共用 context 和 canonical plan contract。
- `tests/test_m282_open_query_resolution.py`：facts、候选、缺失信息、不可用和跨入口契约。
- `docs/`、`tasks/`：Spec、Plan、账本和阶段证据。

## Code Style

公共层使用显式版本化 mapping 和小型纯函数；Domain 通过既有接口提供事实，公共层不按领域 ID 分支：

```python
context = builder.build(request, planner="rule", backend="memory")
if context["clarification"]["state"] != "not_required":
    return clarification_response(context)
return planner.plan(request, context=context)
```

所有字符串、列表、嵌套对象和 JSON 字节数都必须有预算；未知 schema、未注册能力和不安全字段 fail closed。

## Testing Strategy

- 单元/契约：fake Domain Pack 验证多领域 facts 聚合、候选去重、缺失事实、数据不可用、未知能力和预算。
- 回归：M279 Planner 与 M281 Projection 必须保持通过；规则、fake LLM 和 provider failure 分层测试。
- HTTP：FastAPI/stdlib 只比较 semantic response 的 status、context fingerprint、clarification、plan 和 evidence，不复制规划逻辑。
- Docker：compileall、architecture strict、精简定向回归；真实模型/GIS/browser 只显式运行，不进入默认 CI。

## Boundaries

- Always：先构建有界上下文；能力选择必须经过 catalog/allowlist；澄清和拒绝不创建 execution run；记录 context evidence。
- Ask first：新增公共 schema 版本、修改 Domain contract、增加依赖或改变默认 Planner 选择。
- Never：把请求关键词硬编码成跨领域流程；让模型发明工具/数据；保存 prompt/原始响应/密钥；为通过 live case 绕过校验。

## Success Criteria

1. 多领域 fake Domain Pack 能生成稳定 `composite-request-context.v2`，同一输入 fingerprint 一致。
2. 未知问句能够返回候选能力或结构化澄清，不因没有固定模板而直接静默失败。
3. 缺失范围、指标、时间或数据可用性时，澄清字段来自 Domain 声明，不由公共层写死专题字段。
4. Rule/LLM/fake planner 使用相同 context 和 canonical plan contract；未知能力不会创建 execution run。
5. FastAPI/stdlib/异步 prepare 结果在核心状态、context fingerprint、plan fingerprint 和 evidence 上一致。
6. Docker 定向回归、compileall、architecture strict 通过；至少一条真实模型或真实数据验收被显式记录，失败也保留安全 receipt。

## Deferred

- RAG、联网搜索、实时数据发现、自动工具生成。
- 将所有 Domain 的事实抽取统一为一个 LLM；Domain Pack 仍拥有领域事实解析策略。
- 复杂语义排序模型；先使用 catalog 声明、Domain discovery 和有界 Planner。
