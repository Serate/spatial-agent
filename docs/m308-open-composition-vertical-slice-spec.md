# Spec：M308 开放式多组件纵向链路与用户答案质量

## Objective

让 Agent 的核心能力在真实使用路径中可感知：面对未固定成模板的开放请求，系统根据能力目录和请求事实组合三个或更多已登记能力，经过 canonical Composite request、TaskPlan/DAG、ToolRegistry、workflow 和 execution binding 后执行，并把混合类型结果生成简洁、口语化、带限制说明和证据引用的答案。

用户看到的是“正在发现能力 → 检查数据 → 生成计划 → 执行分析 → 汇总结论”的阶段进度和清晰结果；详细计划、证据、artifact 和轨迹保持可展开。内部推理不展示。

## Assumptions

1. M306 已证明真实模型可以形成 2 组件跨域计划；M308 只扩展组合验收和结果表达，不重写 Runtime 或公共 schema。
2. 三个或更多组件使用现有 GIS/Economic/Indicators 能力和真实 Docker 数据；验收不得依赖某一个固定地区才能成立。
3. 答案生成器只能改写结构化事实，不得新增事实、改变数值、修改组件状态或越过证据边界。
4. 默认门禁离线、精简、可重复；真实模型仅在离线门禁通过且确实需要验证 provider 行为时显式调用一次。

## Tech Stack

- Python 3.11、现有 Agent Runtime、Composite Planner、TaskPlan/DAG、ToolRegistry 和 Domain Pack。
- Docker Compose 生产镜像作为 Python/GIS/live 验收环境。
- `unittest` 精简契约、既有 HTTP/artifact/restart acceptance、Node projection smoke。

## Commands

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build --force-recreate spatial-agent
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest tests.test_m308_open_composition_vertical_slice -v
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m compileall -q agent domains production_api.py serve_api.py
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/architecture_check.py --strict
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent node scripts/console_result_projection_smoke.js
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/smoke_check.py
Invoke-WebRequest -Uri 'http://127.0.0.1:8088/health/ready' -UseBasicParsing
```

## Project Structure

- `agent/composite_planner.py`、`agent/application/composite_planning.py`：受限开放组合规划。
- `agent/application/composite.py`、`agent/application/composite_runs.py`：组合执行、恢复和跨入口生命周期。
- `agent/answer_generation.py`、`agent/composite_view.py`：结构化事实到答案和 View 的公共 seam。
- `web/src/console_result_projection.js`：通用结果投影，不按领域或工具名分支。
- `tests/test_m308_open_composition_vertical_slice.py`：本阶段精简契约。
- `docs/`、`tasks/`：能力图、Spec、Plan、问题日志和恢复账本。

## Code Style

答案生成接收安全事实投影，返回结构化答案契约；事实和呈现职责分离：

```python
answer = answer_generator.generate(
    request=request,
    objective=objective,
    facts=project_safe_result_facts(result),
)
result.answer = validate_answer_without_changing_facts(answer, result)
```

- 组件身份、依赖和结果引用使用 canonical contract；不在答案层重建计划。
- 数值、统计单位、限制和来源由结构化 Result/Evidence 提供；缺失字段使用可读降级。
- 前端只消费 View/Evidence projection，不读取工具名、内部 ID 或模型原文来决定布局。

## Testing Strategy

- 组合契约：用脱敏 replay 验证 3+ 组件混合 profile、依赖排序、非法计划和部分失败。
- 答案契约：验证答案不能改变 Result 事实，模型失败时 fallback 仍可读，未知结果类型安全降级。
- 跨入口：只保留一组代表性 sync/async/HTTP/artifact/restart/Console identity 对照。
- 阶段收口：Docker 中集中运行本阶段契约、相邻 Composite 回归、compileall、architecture strict、Node projection、Service smoke、readiness 和必要 live；不重复无关全量测试。

## Boundaries

- Always：能力必须来自 catalog，计划必须通过 canonical DAG/TaskPlan/ToolRegistry/workflow/execution binding；答案必须来自结构化事实；阶段状态和 evidence 可恢复。
- Ask first：新增领域数据源、改变公共 Result/Answer schema、引入 RAG/联网搜索、修改 CI 触发策略或增加运行时依赖。
- Never：按单一区域或固定问句硬编码；让模型直接执行未注册工具；让答案模型补造事实；提交 key、prompt、模型原文、私有路径或完整原始数据。

## Success Criteria

1. 一个不依赖固定模板的开放请求可通过 replay/必要 live 形成 3+ 组件合法 canonical DAG，并通过 TaskPlan、ToolRegistry、workflow 和 execution binding。
2. 三个或更多组件的混合 `vector/raster/metrics/timeseries` 结果能够统一组合，组件失败或数据不足时保留局部结果和明确限制。
3. 答案由结构化 Result/Evidence 生成，面向非专业用户简洁表达结论、关键数值、限制和下一步，不泄漏内部技术字段。
4. sync、async、HTTP、Console、artifact 和 restart 的核心结果、evidence identity 和答案事实一致。
5. Docker 精简契约、相邻回归、静态/架构/前端/服务门禁通过；必要时完成一次真实模型 + 真实 GIS/Economic 验收。
6. 阶段文档、中文问题日志、恢复账本、版本和全局重规划完整。

## Open Questions

- 当前无阻塞问题；若现有真实数据无法支撑 3+ 组件，将记录为数据 readiness 限制，不为验收添加区域专用分支。
