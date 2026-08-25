# M264 指标分析公共核心 Spec

状态：已完成

## Objective

在 M251 指标 Domain 和 M263 Economic Domain 已证明同一类分析模式后，抽取一个领域中立的指标/表格分析模块，消除两个 Provider 中重复的目录聚合、期间筛选、latest/trend/compare、统计指标和来源去重实现。

目标不是创建新的 Runtime 链路，也不是把经济策略搬到公共层，而是让后续人口、教育、就业等专题可以通过“规范化观测 + 数据适配器 + 目录声明”接入。

## Public interface

新增 `agent.analysis.indicator_core.IndicatorAnalysisEngine`，接口只接收：

- 已完成基本字段校验的 numeric observation records；
- dataset ID 和 bounded provenance；
- 结果类型前缀、状态码和输出预算等策略配置。

接口提供：

1. `list_indicators()`：返回指标、单位、区域层级、期间类型、期间和区域目录。
2. `query(arguments)`：执行 `latest`、`trend`、`compare`，返回公共 `metrics`、`timeseries` 或 `composite` profile。
3. `source_evidence(arguments)`：按同一筛选语义返回去重后的来源条目。

核心模块不读取文件、不访问网络、不导入任何 Domain Pack，不负责请求事实提取、Planner 或用户文案。

## Compatibility

- `economic` 保留真实来源字段校验、数据路径发现、`ready/unavailable/field_mismatch/region_unavailable/time_range_unavailable` 语义和 `economic_*_result` 命名。
- `indicators` 保留 demo fixture、`indicator_*_result` 命名和无匹配时的 `ToolError` 兼容行为。
- 所有工具仍通过原有 ToolRegistry；不新增工具，不改 Runtime 生命周期，不增加 HTTP 或前端分支。
- 结果字段新增只能是兼容性扩展；核心 `rows`、`metrics`、`data_profile`、`provenance` 和 source evidence 语义保持稳定。

## Commands

所有 Python 命令在 Docker 中执行：

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml build spatial-agent
docker compose --env-file .env.production -f docker-compose.prod.yml up -d spatial-agent
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m264_indicator_core -v
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m251_indicators tests.test_m263_economic_domain -v
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains scripts tests
docker exec ai-agent-spatial-agent-1 python scripts/architecture_check.py --strict
```

## Project structure

```text
agent/analysis/__init__.py
agent/analysis/indicator_core.py
domains/indicators/provider.py       # source/loading adapter + compatibility mapping
domains/economic/provider.py         # source/loading/validation adapter + compatibility mapping
tests/test_m264_indicator_core.py
```

## Testing strategy

- core contract：用小型、明确的年度/半年观测验证目录、期间排序、三种操作、source evidence 和空结果状态。
- adapter regression：M251 和 M263 原有契约继续通过，确认公共模块没有吞掉领域状态或改变 ToolRegistry 工具名。
- architecture：严格检查公共核心不导入 `domains.*`，两个 Domain 只反向依赖公共核心。
- Docker/live：默认只运行离线 fixture；真实 Economic HTTP、artifact、SQLite/restart 和模型验收继续作为显式阶段路径。

## Boundaries

- Always：只接收规范化记录；保留单位、区域层级、期间和来源；结果使用公共 profile；在 Docker 中验证。
- Ask first：修改公共 Result Contract、改变已有 Provider 错误码、引入外部依赖或提交真实数据。
- Never：在核心模块写经济/GIS 关键词分支、抓取网页、选择默认业务指标、提交密钥或原始数据。

## Success criteria

1. Economic 与 indicators 两个 Provider 共享同一个 indicator-core 实现。
2. latest/trend/compare 的核心统计和期间排序在两个 Domain 保持一致，领域结果类型和错误码仍保持兼容。
3. 来源证据由同一套去重/筛选语义生成。
4. 公共 Runtime、Planner、ToolRegistry、HTTP 和前端主流程无修改。
5. 新增一个指标类专题只需实现数据适配和目录/术语声明，不复制 Provider 分析算法。
6. Docker 中 M264 定向、M251/M263 回归、compileall 和 architecture strict 全部通过。

## Open questions

- 更高层的声明式 workflow/catalog 工厂是否值得抽取，留到 indicator-core 被第三个专题验证后决定。
- 指标发现和来源目录是否最终需要独立数据目录服务，本阶段不提前引入。
