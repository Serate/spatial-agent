# M269 Spec：通用记录分析能力

## Objective

为已登记、已授权且已通过数据校验的结构化记录提供领域中立的筛选、聚合、时间序列和区域/分组比较能力。目标是让真实 Economic 指标与真实 GIS 事件记录共享同一分析核心、Result Contract、View、Artifact、Evidence 和 Runtime 生命周期。

用户不需要知道内部工具名；Planner 只能从当前 Domain Pack 声明的能力、数据目录和 ToolRegistry schema 中选择数据集与字段。未知字段、缺失数据和无效条件必须返回结构化、可恢复状态。

## Assumptions

1. 本阶段数据已经由 Domain Provider 读取为有界 mapping records；核心不负责文件或网络 I/O。
2. 记录中的字段名由数据集 schema/Provider 校验，核心不猜测业务字段。
3. `timeseries` 使用调用方指定的 `time_field`，不把“年份/季度”等词写入公共核心。
4. `compare` 是带分组维度的聚合，不承诺统计显著性或因果结论。
5. 默认执行上限为 10,000 个输入记录、256 个输出行、128 个分组；超限返回截断/降级证据而不是无限扩大内存。
6. 真实 Docker 数据验收不改变默认离线 CI，也不提交真实数据、私密配置或模型原文。

## Interface

### RecordAnalysisEngine

核心对外只保留一个主要接口：

```python
result = engine.analyze(
    records,
    operation="aggregate",
    filters=[{"field": "mag", "operator": "gte", "value": 2.5}],
    group_by=["place"],
    aggregations=[
        {"field": "mag", "function": "mean", "alias": "mean_mag"},
        {"function": "count", "alias": "event_count"},
    ],
    time_field=None,
    limit=256,
)
```

接口必须满足：

- 只接受 mapping records 和显式参数，不创建 Provider、文件句柄或网络客户端。
- 支持条件 `eq/neq/gt/gte/lt/lte/in`。
- 支持聚合 `count/sum/mean/min/max`；需要数值的函数遇到非数值字段返回 `field_mismatch`。
- `filter` 返回脱敏、有界 rows；`aggregate` 返回 groups；`timeseries` 按 `time_field` 稳定排序；`compare` 返回分组聚合结果。
- 对空数据、缺字段、非法操作、非法聚合函数和超出预算分别返回稳定 code、status、retryable 和 bounded warnings。
- 结果不携带 geometry、文件路径、凭据、原始异常或未限制的记录内容。

### Result Contract

通用结果使用 `record_analysis_result`，并至少包含：

```json
{
  "schema_version": "spatial-agent.record-analysis.v1",
  "status": "ready",
  "result_type": "record_analysis_result",
  "operation": "aggregate",
  "dataset": "earthquakes_wuhan",
  "rows": [],
  "metrics": {
    "input_count": 10,
    "output_count": 3,
    "group_count": 3,
    "filtered_count": 6
  },
  "data_profile": {"schema_version": "spatial-agent.data-profile.v1", "primary": "metrics", "kinds": ["metrics"]},
  "provenance": {},
  "warnings": []
}
```

`data_profile` 的 primary/kinds 按操作映射：

- `filter` → `metrics`（记录摘要）或由 Domain 叠加 `vector`/`document_evidence`；
- `aggregate`/`compare` → `metrics` 或 `composite`；
- `timeseries` → `timeseries` 与 `metrics`。

几何、官方来源和完整原始记录继续走已有 Artifact/Evidence/Domain View seam，不嵌入通用 rows。

## Domain 适配

- GIS：新增一个受 ToolRegistry schema 约束的通用 `record_analysis` 工具；文件型矢量适配器读取非 geometry 属性，支持 `earthquakes_wuhan` 等已登记 ready 数据集，不增加地震专用 Runtime 分支。
- Economic：`IndicatorAnalysisEngine` 的公共筛选/分组/排序语义改为委托或复用 `RecordAnalysisEngine`；既有 `economic_indicator_query` 和 source evidence 工具保持结果兼容。
- Indicators：同样复用核心；demo fixture 仍明确标注为 demo，不伪装成真实数据。
- Result Registry：三个 Domain 都登记 `record_analysis_result`，使用 generic/table/chart View，不增加前端领域分支。

## Commands

所有 Python/GIS 命令在 Docker 中执行：

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker exec <container> python -m unittest tests.test_m269_record_analysis -v
docker exec <container> python scripts/architecture_check.py --strict
docker exec <container> python scripts/test_profile.py --profile quick
```

真实验收另使用一次性只读数据挂载，并显式设置 Economic 数据配置和地震 DatasetCatalog；不改变默认生产挂载。

## Project Structure

- `agent/analysis/record_analysis.py`：核心深模块。
- `agent/analysis/record_contract.py`：请求/结果/状态常量和有界规范化。
- `agent/analysis/indicator_core.py`：保留兼容入口，内部复用核心。
- `domains/gis/adapters/`：记录投影和工具适配。
- `domains/economic/`、`domains/indicators/`：Provider/目录兼容接线。
- `tools/schema/tool-definitions.json`：GIS ToolRegistry schema。
- `docs/m269-generic-record-analysis-{map,spec,plan}.md`：阶段文档。
- `tests/test_m269_record_analysis.py`：精简核心/跨 Domain contract。

## Code Style

核心使用小而稳定的接口，Provider 负责适配：

```python
engine = RecordAnalysisEngine(dataset_id="events")
result = engine.analyze(
    records,
    operation="timeseries",
    group_by=["region"],
    time_field="period",
    aggregations=[{"field": "value", "function": "mean", "alias": "mean_value"}],
)
```

核心不导入 `domains.*`，不检查 `roads`、`water`、`gdp` 或任何区域名称；所有异常转为稳定的结构化结果。

## Testing Strategy

- 核心 contract：空集、条件运算、聚合、时间排序、比较、缺字段、预算和敏感字段投影。
- Provider contract：Economic 真实记录和 GIS 地震真实记录均调用同一核心；既有 Economic/Indicators 回归保持通过。
- Runtime/HTTP：至少验证 planner → ToolRegistry → result/view/evidence 的标准链路，不复制 Runtime。
- Docker live：显式执行，不进入默认 CI；记录数据源、状态、结果类型、行数和 evidence，不记录 API key 或模型原文。

## Boundaries

- Always：通过 ToolRegistry；校验 dataset/schema/字段；保留 provenance 和降级 code；使用 Docker 验收；更新中文记忆。
- Ask first：改变已有 result_type 语义、删除旧工具、引入外部网络数据源或新增运行时依赖。
- Never：提交真实原始数据、密钥、绝对宿主路径、未脱敏模型上下文；让模型执行未注册工具或自由生成查询代码。

## Success Criteria

1. GIS 地震记录与 Economic 指标记录可通过同一核心完成至少一项 filter/aggregate/timeseries/compare，核心不导入 Domain。
2. 两个 Domain 的 Result/View/Evidence 仍通过统一 Runtime、ToolRegistry、Artifact 和 HTTP contract。
3. 缺字段、数据不可用和超限均返回结构化可恢复结果。
4. LLM Planner 的 context 显示已注册通用工具和结果类型，Rule Planner 不新增专题专用分支。
5. Docker 精简回归、compileall、architecture strict 和真实数据验收均有证据。

## Open Questions

- 未来是否将 Economic/Indicators 的领域工具完全收敛为 `record_analysis`，本阶段只保留兼容包装，待 M269 验收后全局重规划。
- 未来是否需要更丰富的时间语义（季度/月份/日期），本阶段由 Provider 规范化为可排序字段，不在核心内引入日历知识。
