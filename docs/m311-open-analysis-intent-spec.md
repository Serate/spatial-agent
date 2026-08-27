# Spec：M311 通用分析意图与跨域开放链路

## Objective

面向提出开放空间或区域分析问题的用户，建立一个版本化、领域中立的分析意图契约。
系统应能识别有限的通用操作及其组合，并把它们交给现有 Capability Catalog、数据目录、
Domain resolver、Planner 和 ToolRegistry 完成闭合。用户不需要记住工具名；数据或条件不足时
得到结构化澄清，不能由模型臆造数据、能力或工具。

本阶段基于已批准的项目 Goal 和 M310 结果推进，默认假设如下：

1. Python、GIS、真实数据和集成测试继续在 Docker 中运行；默认测试离线且精简。
2. 现有 `vector/raster/metrics/timeseries/document_evidence/composite` Result Contract
   继续作为唯一输出分类，不新增第二套结果协议。
3. 现有 Planner、TaskPlan/DAG、ToolRegistry 和生命周期接口保持稳定；只在其公共 seam
   增加必要的结构化字段。
4. 本阶段最多执行一次显式真实模型验收；真实模型可以返回澄清或 provider failure，必须
   如实记录。

## Tech Stack

- Python 3.11、现有 Agent Runtime、Domain Pack、ToolRegistry、SQLite/artifact。
- 现有 Docker 镜像中的 rasterio、GDAL/PROJ、GeoPandas/Shapely 等 GIS 依赖。
- 现有 Node projection smoke；不为本阶段引入新的前端框架或第三方依赖。

## Commands

```text
docker compose -f docker-compose.prod.yml --env-file .env.production build spatial-agent
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m unittest tests.test_m311_open_analysis_intent -v
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m compileall -q agent domains tests scripts
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent node scripts/console_result_projection_smoke.js
```

阶段收口再执行必要的跨入口、真实 GIS 和最多一次真实模型验收；不重复运行无独立失败
模式的历史全量测试。

## Project Structure

- `agent/`：领域中立的意图、能力目录、Planner Envelope、TaskPlan 和 Result Contract。
- `domains/`：GIS、Economic 等 Domain Pack 的能力、数据、workflow 和 ToolRegistry adapter。
- `tests/`：M311 精简契约及必要相邻回归。
- `scripts/`：阶段级 Docker/live 验收 harness，只输出脱敏 receipt。
- `web/src/`：消费结构化 Result/View/Evidence 的通用投影。
- `docs/`、`tasks/`：Spec、Plan、中文问题日志和恢复账本。

## Code Style

意图契约只表达可验证语义，不保存模型原文：

```python
intent = normalize_analysis_intent({
    "operations": ["query", "trend", "evidence"],
    "data_kinds": ["metrics", "timeseries", "document_evidence"],
})
assert intent["schema_version"] == "spatial-agent.analysis-intent.v1"
```

字段使用小写稳定 id；列表有上限；未知操作、未知数据类型、冲突别名和缺少必需事实
必须 fail closed 或返回结构化澄清。公共模块不导入 GIS 或 Economic 专用策略。

## Testing Strategy

- 契约测试：验证意图归一化、操作组合、未知/冲突输入、数据类型和能力绑定边界。
- Planner 回归：验证 LLM/replay 输出只能引用目录能力，并保持 canonical plan、workflow、
  TaskPlan 和 binding identity。
- 跨域验收：至少覆盖一个 GIS 请求和一个 Economic 请求，比较 Result/View/Evidence 的
  公共字段，不保存模型原文或完整真实数据。
- Docker 静态门禁：compileall、architecture strict、Node projection 和 readiness。
- 显式验收：真实 GIS/Docker 必须执行；真实模型最多一次，结果可为澄清或 provider failure。

## Boundaries

- Always：通过公共契约、Capability Catalog、Domain resolver 和 ToolRegistry；保持证据、
  artifact、异步和恢复语义一致；对输入和输出做 schema/预算校验。
- Ask first：新增第三方依赖、修改 CI/部署方式、改变公共 schema 兼容策略或扩大真实数据
  采集范围。
- Never：提交密钥；保存 prompt/模型原文/私有路径；让模型直接调用未注册工具；绕过
  TaskPlan、ToolRegistry、execution binding；为单一区域或固定问句添加流程分支。

## Success Criteria

1. `analysis-intent.v1` 能表达 query、filter、aggregate、trend、compare、spatial_operation
   和 evidence，并能安全表达多个操作的顺序/依赖。
2. Planner Envelope 能把意图、所需数据类型和目录候选传给模型；模型输出只能引用已注册
   capability、workflow 和 result type。
3. 信息不足、未知操作、数据类型冲突、字段不匹配和不可用数据源会返回结构化澄清或可恢复
   不可用状态，不创建未经验证的 execution run。
4. GIS 与 Economic 至少各有一条开放请求通过同一意图、Result/View/Evidence 和生命周期
   契约；新增操作不需要修改 Runtime 主循环或前端领域分支。
5. 同步、异步、HTTP、artifact 和 restart 的公共结果 identity 保持一致。
6. Docker 精简门禁和真实 GIS 验收通过；阶段唯一真实模型调用按实际成功、澄清或 provider
   failure 记录。

## Open Questions

- M311 不决定是否采用 ReAct；受控多步决策循环保留为后续阶段候选，前提是当前 Goal 的
  通用能力与跨域开放链路先完成。
