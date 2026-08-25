# M263 真实经济分析 Domain Plan

状态：已完成

## 执行原则

本 Plan 对应 `docs/m263-economic-domain-spec.md`。实施顺序为：

`全局盘点 → Spec → Plan → 真实来源核验 → Provider → Domain Pack → 跨入口验收 → 文档/提交 → 全局重规划`

第一条经济链路用于证明边界；后续专题优先复用其中的数据目录、Provider 校验、指标工作流和证据模型，不复制 Runtime。

## 任务清单

### 1. 来源与数据契约

- [x] 调研武汉市统计局、洪山区政府/统计部门、湖北省统计局和国家统计局的一手来源。
  - 验收：每个候选来源有 URL、发布机构、指标/区域/期间、字段或表格定位、发布日期、许可边界和当前可用性。
  - 验证：写入 `docs/data-source-research-economic-wuhan.md`，不把待核验来源标为 ready。
- [x] 确定首批最小指标集合和外部数据 JSON 规范。
  - 验收：至少能表达指标 ID、名称、单位、区域层级、期间、值和逐条来源。
  - 验证：配置示例能通过 Provider schema 校验。

### 2. Economic Provider

- [x] 新增 `domains/economic/provider.py`。
  - 验收：支持外部配置路径、来源校验、latest/trend/compare 查询和结构化 unavailable/field_mismatch/region/time 状态。
  - 验证：无配置、字段错误、区域不存在、期间越界和 ready fixture 各有一个精简用例。
- [x] 新增 `config/economic-data.example.json`。
  - 验收：只含 schema/示例或明确标注 fixture，不含密钥和未授权原始数据。
  - 验证：Provider 可加载并拒绝不完整来源。

### 3. Economic Domain Pack

- [x] 新增 catalog、request understanding、workflow、planner、evidence、composer、views 和 domain 适配。
  - 验收：所有工具经 ToolRegistry；Result Registry 使用公共 data profiles；Planner 不能选择未注册工具。
  - 验证：Economic Domain 注册、catalog、clarification、workflow compile 和 result view 契约。
- [x] 将 `economic` 注册到 DomainRegistry。
  - 验收：不改 Runtime 生命周期；GIS/indicators/Text Domain 仍可选择。
  - 验证：domain catalog、architecture strict 和跨 Domain 回归。

### 4. 纵向链路与答案

- [x] 打通规则 Planner 的真实数据链路。
  - 验收：完整事实返回结构化结果与来源证据；事实不足进入澄清。
  - 验证：`build_runtime("rule", "local", domain_id="economic")` 的精简端到端用例。
- [x] 接入公共答案生成边界和用户视图。
  - 验收：规则回答简洁可读，真实模型只接收有界工具事实；前端 generic metrics/chart/table 能展示。
  - 验证：Result/View/HTTP/artifact 核心契约，不增加经济专用前端分支。

### 5. Docker 与真实验收

- [x] 在 Docker 中执行 compileall、architecture strict、quick/stage 和 M263 定向测试。
- [x] 配置真实数据路径，显式执行至少一条洪山指标查询和一条趋势/比较验收。
  - 验收：结果、source evidence、data readiness 和失败状态可复核。
- [x] 对 CLI、HTTP、artifact、SQLite/restart 做最小一致性抽查。

### 6. 阶段收口

- [x] 更新 `docs/agent-context-resume.md`、`docs/milestones.md`、`docs/agent-development-issues.md` 和数据来源文档。
- [x] 运行 `git diff --check`、查看提交范围、commit/push。
- [x] 根据产品、架构、数据、模型、部署、体验、测试七个维度全局重规划下一阶段。

## 依赖与风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 官方数据不可下载或许可不清 | 无法完成真实 ready 验收 | 保留 source_unverified/unavailable；不伪造数字；寻找另一官方一手源 |
| PDF/HTML 表格字段难以稳定提取 | Provider 结果不可审计 | 保存原始 URL、发布日期、表格定位和提取版本；先支持人工规范化 JSON |
| 指标和区域层级语义不一致 | 结果误导 | 将 geography_level、unit、period 和 source.field 作为必需校验 |
| 新专题复制经济代码 | 后续扩展成本继续增长 | 先沉淀通用指标/表格 Provider seam，再添加专题声明 |
| LLM 生成未注册计划 | 执行不安全 | Capability Catalog、schema、workflow 和 ToolRegistry 四层校验 |

## 验证检查点

1. Provider 能单独报告 ready/unavailable 和来源证据。
2. Domain 能被发现，工具和 workflow 能通过 schema/计划校验。
3. Runtime 规则链路能完成或结构化澄清，不出现领域分支错误。
4. Docker 中公共回归和 M263 定向测试通过。
5. 真实数据验收证据完整后才提交阶段版本。

## 阶段验收证据

- Docker 中 `tests.test_m263_economic_domain`：**7/7**。
- Docker 中跨 Domain/HTTP/架构回归：**16/16**；`compileall`、`architecture_check.py --strict`、quick 和 stage 均通过。
- Provider 真实数据健康状态：`ready`，31 条观测，0 个字段校验问题。
- 真实 HTTP 比较：`COMPLETED`，`economic_comparison_result`，覆盖洪山区与武汉市，2 个工具步骤，来源证据保留；容器重建后 SQLite run detail 仍可读取。
- artifact 读取：HTTP 200，结果 `composite`，证据索引保留 8 条 entry。
- 显式真实模型验收：`COMPLETED`，Planner 选择 `economic_indicator_query` 和 `economic_source_evidence`，结果为 `economic_timeseries_result`；不把该路径纳入默认 CI。
- 本阶段发现的测试问题已记录到 `docs/agent-development-issues.md`，并修复旧测试对领域列表的硬编码和固定 SQLite 会话污染。
