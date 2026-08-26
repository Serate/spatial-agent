# M300 开放问题 Agent 成功率与答案体验规格

## Objective

面向非专业用户，使产品默认入口能够处理未预先写成模板的地理数据问题：理解目标和约束，发现登记能力，选择可执行组合，安全执行，最后用简洁中文回答并给出必要证据。GIS 仍只是 Domain Pack，公共 Runtime 不携带 GIS 专用策略。

## 假设

1. 产品入口继续默认使用 `openai + local`；离线 Rule/Replay 只作为确定性验收和模型不可用时的显式降级。
2. 可用数据必须来自已登记且通过健康检查的数据目录；M300 不引入自由网络搜数或 RAG。
3. 当前 Result、View、Artifact、Evidence、TaskPlan 和 execution binding 契约继续作为公共边界。
4. 真实模型可能超时或返回不合规结构，系统必须安全澄清/失败，不能伪造成功。

## Commands

- Docker build：`docker compose -f docker-compose.prod.yml --env-file .env.production build spatial-agent`
- Docker service：`docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate spatial-agent`
- Compact contract：`docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest ...`
- 静态检查：Docker `python -m compileall -q agent domains scripts tests` 与 `python scripts/architecture_check.py --strict`
- 前端检查：Docker `node scripts/console_result_projection_smoke.js`
- readiness：`Invoke-WebRequest -Uri http://127.0.0.1:8088/health/ready -UseBasicParsing`

## Project Structure

- `agent/runtime_core/`：Planner envelope、TaskPlan、生命周期、证据和公共契约
- `agent/application/`：同步、异步、HTTP、artifact、恢复等应用边界
- `domains/`：可替换 Domain Pack、事实解析、数据适配器和领域工具
- `web/src/`：领域中立的 Result/View/Evidence projection 与交互
- `tests/`：精简契约、跨入口回归和显式验收脚本
- `docs/`、`tasks/`：Spec、Plan、问题记录、阶段日志和恢复快照

## Code Style

新增能力优先使用领域中立的纯 projection 或 boundary seam，并让身份、状态和错误码有界、可序列化、可版本化。例如：

```python
def project_next_action(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "state": str(value.get("state") or "unknown")[:32],
        "message": str(value.get("message") or "")[:240],
    }
```

不在公共 Runtime 中判断 `洪山区`、具体工具名或某个专题；前端消费结构化字段，不依据工具名拼接页面分支。

## Testing Strategy

- 开发中只做必要的静态检查和单一失败模式回归。
- 阶段收口集中运行一次精简 Python contract、Node projection、compileall、architecture strict 和 readiness。
- 用 Rule/Replay 覆盖确定性成功、澄清、数据不可用和恢复；用一次显式 live 覆盖真实 provider 可达、超时或不合规输出。
- 不把真实模型、私有数据或网络依赖放入默认 CI；不保存模型原文、密钥或原始私有数据。

## Boundaries

- Always：经过 Catalog → Workflow → ToolRegistry → TaskPlan → execution binding；保留可读状态、证据和恢复动作；跨入口保持核心 identity 一致。
- Ask first：新增外部依赖、持久化 schema、数据源、CI 触发策略或改变默认 provider。
- Never：绕过 schema/权限/readiness、为固定问句增加硬编码流程、提交密钥或用失败测试删除制造绿色结果。

## Success Criteria

1. 一个未预先定义模板的开放式请求能进入 RequestFacts、能力选择和受控多步 TaskPlan，或返回结构化澄清。
2. 真实模型选择只能引用已登记且 execution-ready 的能力，计划不合规时不创建执行 run。
3. provider timeout、数据不可用、澄清和业务执行失败在状态、证据和用户文案中可区分。
4. provider 失败返回可重试的 `FAILED` planning 状态与 `failure.v1` 证据，不误导用户补充已经具备的事实。
5. 同一请求的同步、异步、artifact/restart 和前端核心结果/证据保持一致。
6. 结果回答优先给结论、关键指标、限制和下一步，详细 trace/evidence 可展开但不暴露思维链。
7. 新增一个可登记能力不需要修改 Runtime 主循环或前端领域分支。

## Answer generation activation

- 当 Composite 结果确实由 LLM Planner 规划且运行环境配置了模型时，默认启用一次结构化答案生成，让模型把已验证结果翻译成面向普通用户的中文。
- Rule、Replay、直接 Composite 执行和未配置模型的路径继续使用确定性回退，不访问网络；部署可通过 `SPATIAL_AGENT_DISABLE_LLM_ANSWER=1` 关闭答案生成。
- 答案生成只能消费 Result/View 的有界事实，失败时回退到结构化摘要并记录状态，不改变事实、计划或执行结果。

## Open Questions

- 真实模型中转的稳定性和延迟仍需显式验收；在 provider 未稳定前不承诺 live 成功率指标。
- 本阶段暂不引入新的外部数据源，优先利用现有目录验证框架的通用性。
