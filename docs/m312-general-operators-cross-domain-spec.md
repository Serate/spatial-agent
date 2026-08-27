# Spec：M312 通用分析算子与跨域真实能力闭合

## Objective

面向不使用固定问句的开放式地理分析用户，补齐 M311 之后的真实能力闭合：用户提出
空间、指标或跨域问题时，系统能够依据结构化分析意图和能力目录，选择少量已注册的
通用算子，绑定真实数据，经过既有 TaskPlan/DAG、ToolRegistry 和 execution binding
执行，并返回可读的 Result/View/Evidence。

本阶段不重写 Runtime，不把经济或 GIS 逻辑搬进公共层，也不把“支持更多问题”实现为
不断增加关键词分支。

## Assumptions

1. 现有 Docker 镜像是 Python、GIS、测试和 live 验收的统一环境。
2. M311 的 `analysis-intent.v1`、Result Contract、View/Evidence 和生命周期接口继续
   作为公共边界。
3. 当前项目已有真实武汉数据或数据目录；数据不足时必须返回结构化不可用/澄清，而不
   生成估计结论。
4. 使用现有 GIS 库和适配器优先；新增第三方库、数据采集范围或部署配置需要另行确认。
5. 当前按串行方式实施，阶段收口只运行一次合并后的精简验证集和一次显式真实模型验收。

## Tech Stack

- Python 3.11、现有 Agent Runtime、Domain Pack、TaskPlan/DAG、ToolRegistry、SQLite/artifact。
- Docker 内已有 rasterio、GDAL/PROJ、GeoPandas、Shapely、pyogrio 和 Fiona。
- 现有 Node Console projection；不引入 React 或新的前端框架。

## Commands

```text
Build:
docker compose -f docker-compose.prod.yml --env-file .env.production build spatial-agent

Contract:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m unittest tests.test_m312_general_operators -v

Static:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m compileall -q agent domains tests scripts
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python scripts/architecture_check.py --strict

Frontend:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent node scripts/console_result_projection_smoke.js

Live/local GIS:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python scripts/live_http_acceptance.py --allow-live --base-url http://host.docker.internal:8088 --planner rule --backend local
```

真实模型验收最多显式执行一次，并只保留脱敏 receipt。

## Project Structure

- `agent/analysis_intent.py`：M311 公共意图契约，M312 只扩展必要的绑定 seam。
- `agent/`：公共能力发现、Result Contract、Planner、TaskPlan/DAG、ToolRegistry 和生命周期。
- `domains/gis/`：通用空间算子、真实 GIS 数据和 Domain workflow。
- `domains/economic/`：指标查询、趋势、比较、来源证据和真实数据目录。
- `web/src/`：按结构化 Result/View/Evidence 投影用户界面。
- `tests/test_m312_general_operators.py`：合并后的 M312 契约和失败矩阵。
- `docs/`、`tasks/`：Spec、Plan、中文问题日志和恢复账本。

## Code Style

能力声明使用稳定 operation id、输入/输出 data profile 和事实要求；不要在公共 Runtime
中按自然语言关键词分支。例如：

```python
{
    "id": "vector_operation",
    "analysis_operations": ["spatial_operation"],
    "input_profiles": [{"kinds": ["vector"]}],
    "output_profiles": [{"primary": "vector", "kinds": ["vector"]}],
    "request_requirements": {"fields": ["source", "operation"]},
}
```

所有输入在 Domain 边界归一化，所有工具调用继续经过 ToolRegistry；公共投影只传递
稳定字段、有限列表和安全的来源证据。

## Testing Strategy

- M312 精简契约：覆盖 operation → capability/result profile 绑定、空间算子 schema、
  Economic query/trend/compare/evidence、缺数据/字段/CRS/时间范围和非法能力。
- 跨域闭合：至少一条 GIS 和一条 Economic 请求走同一 Planner/TaskPlan/ToolRegistry/
  Result/View/Evidence 语义；必要时用 Replay/Rule 复现，不能冒充 live 模型。
- Docker 静态门禁：compileall、architecture strict、Node projection、Service/readiness。
- 真实验收：真实本地 GIS 和真实 Economic 数据各至少一次；同步、异步、artifact、
  SQLite/restart 对照只比较公共 identity。
- 真实模型：阶段最多一次；结果可以是成功、澄清或 provider failure，必须记录实际状态。

## Boundaries

- Always：使用 M311 意图契约、能力目录、Domain resolver、TaskPlan/DAG、ToolRegistry、
  Result/View/Evidence 和统一生命周期；输出可追溯来源和可恢复状态。
- Ask first：新增第三方依赖、扩大数据下载范围、修改 CI/部署、改变公共 schema 兼容策略。
- Never：为洪山区、固定问句或单一文件增加专用流程；模型直调工具；绕过 schema/preview/
  binding；用工具名称猜结果类型；提交密钥、prompt、模型原文或完整私有数据。

## Success Criteria

1. M311 支持的每类通用操作至少能映射到一个已注册 capability，并验证输入/输出 profile。
2. GIS 的 clip、buffer、intersect、distance（或目录中实际可用的同等通用算子）经过
   ToolRegistry 和既有执行闭合，不修改 Runtime 主循环。
3. Economic Domain 能用真实、可追溯数据支持指标查询、趋势、区域比较和来源证据；缺失
   指标、区域、时间或数据源时返回结构化澄清/不可用状态。
4. GIS 与 Economic 的同步、异步、HTTP、View、artifact 和 restart 对公共 Result/Evidence
   identity 一致；前端不依赖工具名或领域页面分支。
5. 新增一个同类 capability 只需扩展 Domain catalog、schema、workflow 和 Result profile，
   不修改 Runtime 核心流程。
6. Docker 精简门禁、真实 GIS/Economic 数据验收和一次显式真实模型验收完成；默认测试
   不访问私有数据和外部模型。

## Open Questions

- M312 不决定是否改用 ReAct；只有在通用能力执行闭合和 provider 成功率有基线后，才评估
  受控 ReAct 循环是否能带来可验证收益。
- React 前端迁移在公共 HTTP/View/Evidence 契约稳定后另立阶段，不与本阶段算子建设耦合。
