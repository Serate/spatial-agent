# Spec：M309 真实模型开放组合与默认 Agent 体验

## Objective

让 Agent 在真实模型可用时表现为“先理解和规划，再执行和解释”的通用系统：用户提出未写成固定模板的空间或跨领域问题后，模型基于 RequestFacts、Capability Catalog、数据 readiness 和工具 schema 形成 3 个或更多已登记能力的候选计划；Runtime 负责校验、有限修复、执行、恢复和证据发布。模型不可用或计划不可信时，系统必须返回明确、可重试或可澄清的状态，不创建未经验证的执行 run。

用户主要看到阶段进度、结论、限制、证据和下一步；计划细节与执行轨迹可展开查看。答案只能改写结构化事实，不能创造事实或改变执行状态。

## Assumptions

1. M308 已验证 3+ 组件的 Rule/Replay/真实 Docker 执行和跨入口 identity；M309 不重写公共 Runtime。
2. 当前模型服务配置可由部署环境提供；测试和日志不读取或保存密钥、prompt、模型原文。
3. Docker 是 Python、GIS、HTTP 和 live 验收的统一环境；默认回归保持离线、精简、可重复。
4. 当前阶段串行推进；每个阶段任务包覆盖契约、实现、集成、文档和交付准备，测试在阶段收口集中执行。

## Tech Stack

- Python 3.11、现有 Agent Runtime、Composite Planner、TaskPlan/DAG、ToolRegistry、Domain Pack。
- Docker Compose 生产镜像；真实模型仅作为显式验收依赖。
- `unittest` 精简契约、既有 HTTP/artifact/restart acceptance、Node projection smoke。

## Commands

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production build spatial-agent
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate spatial-agent
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest tests.test_m309_real_model_agent_experience -v
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m compileall -q agent domains production_api.py serve_api.py
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/architecture_check.py --strict
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent node scripts/console_result_projection_smoke.js
Invoke-WebRequest -Uri 'http://127.0.0.1:8088/health/ready' -UseBasicParsing
```

真实模型命令只在阶段门禁通过后显式执行一次，使用有界 deadline 和 0 重试；具体命令与脱敏验收结果记录在阶段计划，不写入模型原文或密钥。

## Project Structure

- `agent/composite_planner.py`、`agent/runtime_core/planner_envelope.py`、`agent/runtime_core/plan_completeness.py`：模型输出到受控计划的公共边界。
- `agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/execution_binding.py`：TaskPlan/DAG 到可执行 binding 的门禁。
- `agent/application/composite_planning.py`、`agent/application/composite_runs.py`：规划、澄清、修复和运行生命周期。
- `agent/answer_generation.py`、`agent/composite_view.py`、`web/src/console_result_projection.js`：结构化事实到答案和前端投影。
- `tests/test_m309_real_model_agent_experience.py`、`scripts/`：精简契约和显式验收。
- `docs/`、`tasks/`：能力图、Spec、Plan、问题日志和恢复账本。

## Code Style

规划边界先生成有界 receipt，再把唯一可信对象交给 TaskPlan bridge；不要在 HTTP 或前端重新解释模型输出：

```python
envelope = planner_envelope.project(context, stage="selection")
proposal = provider.plan(envelope)
canonical = normalize_and_validate(proposal, catalog=catalog)
task_plan = composite_taskplan.from_canonical(canonical)
binding = execution_binding.bind(task_plan)
```

- 所有外部输入先 schema 校验，再进入业务对象。
- 失败使用稳定的状态、错误码、`retryable` 和下一步动作；异常文本仅留在受控日志，不进入公开投影。
- 前端仅消费 Result/View/Evidence，不根据 domain、tool 或固定问句猜测布局。

## Testing Strategy

- 阶段契约：覆盖真实模型响应可回放的 3+ 组件成功、澄清、非法计划、有限修复和 provider failure；校验 run 创建边界。
- 跨入口：保留一组代表性 sync/async/HTTP/View/artifact/SQLite restart identity 对照。
- 门禁：Docker 中集中运行本阶段契约、相邻 Composite 回归、compileall、architecture strict、Node projection、Service smoke 和 readiness。
- Live：离线门禁通过后最多一次真实模型 + 真实 GIS/Docker 验收；超时、非法输出或澄清都按真实结果记录，不以 Replay 代替 live 成功。

## Boundaries

- Always：模型输入使用阶段化且有界的 Planner Envelope；计划必须通过 catalog、schema、TaskPlan/DAG、ToolRegistry、workflow 和 execution binding；答案必须来自结构化事实。
- Ask first：改变公共契约、增加模型供应商/运行时依赖、引入 RAG/联网数据、修改默认部署或 CI 策略。
- Never：把 provider 成功当作可执行成功；绕过校验直接执行模型输出；让答案模型补造数据；提交 key、prompt、模型原文或私有数据。

## Success Criteria

1. 一个开放请求可由真实模型或脱敏 replay 形成 3+ 组件合法计划，并在校验通过前不创建 execution run。
2. 非法能力、缺失事实、依赖错误、超时和结构化输出失败分别返回稳定且可恢复的状态；有限 repair 保留 lineage 且不超过预算。
3. 默认 Agent 阶段、答案、限制、下一步和详细证据由同一结构化投影派生，普通用户不需要理解内部模块名。
4. sync、async、HTTP、View、artifact 和 restart 的核心结果、答案事实、计划/binding identity 和 evidence 一致。
5. Docker 精简门禁通过，并完成一次明确标注结果类别的真实模型 + 真实 GIS 验收，或记录有界、可诊断的 provider 阻塞。
6. 中文问题日志、恢复账本、里程碑、Spec/Plan 和阶段版本完整更新，并依据产品、架构、数据、模型、部署、体验、测试七个维度规划下一阶段。

## Open Questions

- 当前无须阻塞实现的开放问题。真实模型的延迟或中转可达性若不稳定，按 provider/harness 失败记录，不改变执行安全边界。
