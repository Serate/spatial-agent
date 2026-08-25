# M263 真实经济分析 Domain Spec

状态：已完成

本阶段遵循：全局重规划 → Spec → Plan → 实现 → Docker 集成验收 → 文档/证据 → commit/push → 全局重规划。

## Objective

在不复制 Agent Runtime、Planner、ToolRegistry、生命周期、HTTP 或前端主流程的前提下，新增一个可替换的 Economic Domain Pack，使系统能够处理：

> 武汉市洪山区最近经济发展状况如何？

当真实数据已配置时，系统应通过结构化请求事实、能力发现、计划编排、ToolRegistry 执行和来源证据生成可读结论；当指标、时间范围、区域层级或数据源不足时，必须返回结构化澄清或可恢复的不可用状态，不能以演示数字冒充真实结论。

本阶段的重点不是为这一句问法增加规则，而是验证后续人口、教育、就业、产业等专题可以复用同一套指标/表格分析能力。

## Capability Map

| 模块 | 职责 | 依赖 |
|---|---|---|
| economic-catalog | 指标、区域层级、期间和数据集目录 | 公共 Capability Catalog |
| economic-provider | 真实数据读取、字段校验和来源绑定 | economic-catalog |
| economic-workflows | 发现、最新值、趋势、区域比较和证据工作流 | economic-catalog、economic-provider |
| economic-domain | Domain Pack 适配、答案和 View 投影 | 上述模块、公共 Runtime |
| economic-acceptance | CLI/HTTP/Docker/Artifact 一致性验收 | economic-domain |

构建顺序：`economic-catalog → economic-provider → economic-workflows → economic-domain → economic-acceptance`。

## Scope

### 必须支持

1. 指标目录发现：返回指标 ID、中文名称、单位、区域层级、可用期间、数据集和来源摘要。
2. 指标查询：支持 latest、trend、compare 三种有限操作。
3. 区域与时间事实：识别武汉市、洪山区、区域层级和“最近/近年”等时间意图；信息不足时澄清，不擅自选择指标。
4. 来源证据：每条结果至少绑定来源名称、来源 URL、数据版本/发布日期、检索时间、许可或使用边界、字段与区域层级说明。
5. 数据状态：区分 ready、unavailable、field_mismatch、region_unavailable、time_range_unavailable 和 source_unverified。
6. 结构化结果：使用公共 `metrics`、`timeseries`、`composite` 和 `document_evidence` 数据形态，不新增经济专用 Runtime 结果协议。
7. 入口一致性：规则 Planner、LLM Planner、CLI、HTTP、前端 workspace、artifact 和 SQLite/restart 使用同一核心结果与证据。

### 不在本阶段

- 不编造或硬编码一组武汉/洪山经济数字作为“真实数据”。
- 不引入 RAG、向量数据库或新闻舆情分析。
- 不实现 GDP 预测、因果推断、经济模型或法定统计解释。
- 不修改公共 Runtime 生命周期，不增加经济专用 HTTP 路由和前端领域分支。
- 不把来源未核验的第三方下载站数据标成官方数据。

## Data Contract

Provider 的规范化观测至少包含：

```json
{
  "dataset": "wuhan_economic_indicators",
  "indicator": "<stable-id>",
  "label": "<中文指标名>",
  "region_id": "<stable-region-id>",
  "region": "洪山区",
  "geography_level": "district",
  "period": "2024",
  "value": 0,
  "unit": "<unit>",
  "source": {
    "name": "<first-party source>",
    "url": "https://<source>",
    "published_at": "<date or null>",
    "retrieved_at": "<date>",
    "version": "<source version>",
    "license": "<known boundary>",
    "field": "<source field or table>",
    "geography_level": "district"
  }
}
```

Provider 必须先验证必需字段、数值类型、区域层级、期间格式和来源完整性，再向 ToolRegistry 返回结果。数据文件采用外部配置路径；默认离线测试只能使用明确标注的 fixture，不得与真实验收混淆。

## Runtime Integration

Economic Domain 只实现现有 DomainPack seam：

- `tool_provider()`：注册少量经济工具并交给 ToolRegistry；
- `capability_catalog()`：声明指标发现、查询、趋势、比较和来源能力；
- `extract_request_facts()` / `request_understanding_guidance()`：领域事实词汇；
- `workflow_template_catalog()` / `validate_workflow_plan()`：有限、可校验的工作流；
- `result_registry()` / `views.py`：公共 Result/View 投影；
- `evidence_provider()`：发布和运行来源证据；
- `answer_composer()`：只负责缺省/规则模式的用户表达，真实模型模式继续使用公共答案生成边界。

Planner 可以选择已声明的工具，但不能创建新工具、虚构指标或绕过数据状态门控。Economic Domain 不导入 GIS backend，不读取公共 Runtime 的私有状态。

## Commands

默认验证均在 Docker 中执行：

```powershell
docker compose --env-file .env.production build spatial-agent
docker compose --env-file .env.production up -d spatial-agent
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m263_economic_domain -v
docker exec ai-agent-spatial-agent-1 python scripts/architecture_check.py --strict
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains scripts tests
```

真实数据验收必须显式设置外部数据路径和 live 标志，不进入默认 CI；密钥、`.env.production`、原始数据和本机绝对路径不得提交。

## Project Structure

```text
domains/economic/                         # 新增 Economic Domain Pack
  catalog.py                              # 能力、数据集和工具 schema
  provider.py                             # 可替换真实数据 Provider
  request_understanding.py                # 经济事实词汇
  workflow_templates.py                   # 声明式工作流
  planner.py                              # 规则兜底 Planner
  evidence.py                             # 来源证据
  composer.py                             # 规则/降级答案
  views.py                                # generic metrics/chart/table View
  domain.py                               # DomainPack 适配
config/economic-data.example.json         # 外部数据配置示例，不含真实密钥/私有数据
docs/data-source-research-economic-wuhan.md
tests/test_m263_economic_domain.py        # 精简契约与 provider 状态测试
```

若后续多个专题共享同一表格/指标数据形态，应把共享读取与校验逻辑继续下沉为领域中立 Adapter；本阶段不提前抽象未被真实链路证明的接口。

## Code Style

数据状态必须显式、稳定、可序列化：

```python
return {
    "status": "unavailable",
    "code": "economic_region_unavailable",
    "retryable": False,
    "dataset": dataset_id,
    "requested": {"indicator": indicator, "regions": regions},
    "source": source_summary,
}
```

工具入口只接受 schema 已声明的参数；Provider 内部使用小函数校验字段和来源，禁止在请求解析器中直接写入统计数字。

## Testing Strategy

- 单元/契约：目录、schema、事实提取、工作流编译、字段/来源/区域/期间状态。
- 集成：Economic Domain → ToolRegistry → Runtime，验证结果类型、evidence 和回答。
- Docker：compileall、architecture strict、精简定向测试、HTTP/artifact/restart 核心一致性。
- 真实验收：显式配置真实官方数据，至少验证一条洪山指标查询和一条趋势/比较路径；记录来源和数据状态，不进入默认 CI。
- LLM：使用脱敏回放或真实模型显式验收，模型只能产出已注册工具的 TaskPlan。

## Boundaries

- Always：先校验来源和字段；所有工具经 ToolRegistry；结果带 data profile 和 evidence；Docker 验证；中文文档记录决策。
- Ask first：引入新的外部数据许可、修改公共 Result Contract、修改默认 CI/部署配置、提交大体量数据。
- Never：提交 API key；将 fixture 标为真实；绕过澄清/数据状态；为单一问句添加 Runtime 分支；把第三方来源当作官方来源。

## Success Criteria

1. `economic` Domain 可被注册、发现和选择，且不改公共 Runtime 主流程。
2. 完整请求在指标/区域/期间齐全且数据 ready 时，能生成 `metrics + timeseries/composite + document_evidence` 的结构化结果。
3. “武汉市洪山区最近经济发展状况如何”在缺少指标或数据不完整时返回结构化澄清/不可用状态，而不是演示答案。
4. 真实数据路径配置后，至少一条洪山真实指标查询经过 ToolRegistry，结果包含可追溯来源。
5. CLI、HTTP、artifact 和重启恢复的核心结果/evidence 一致。
6. 现有 GIS、indicators、Text Domain 回归不受影响，架构守卫不允许 Economic Domain 反向依赖 GIS 或 Runtime 私有实现。

## Open Questions

- 官方源优先采用武汉市统计局/洪山区统计公报、统计年鉴还是国家统计局可核验接口；需以实际可下载、字段完整且许可清晰者为准。
- 如果官方来源只提供 PDF/HTML 表格，是否在本地生成带原始 URL、页面/表格定位和提取时间的规范化 JSON；本阶段允许，但必须保留提取证据。
- “最近经济发展”默认应包含哪些指标，需要通过目录发现或用户澄清解决，不能由代码私自选定。
