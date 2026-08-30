# Agent 任务进度账本

> 当前账本只保留恢复所需的当前任务和最近交付。完整历史见
> `docs/archive/task-progress-history.md`，默认恢复不读取历史账本。

<!-- document-control: {"schema_version":"spatial-agent.document-control.v1","role":"active-ledger","archive_target":"docs/archive/task-progress-history.md","archive_block_prefix":"archive-block"} -->

## 使用规则

- 每个子任务开始、完成或暂停时，更新 `tasks/current-state.md`，再在本文件追加一条精简记录。
- 同步 `docs/agent-work-state.md` 时只更新当前状态，不复制历史过程。
- 记录目标、状态、修改文件、验证、阻塞和下一步；不记录 API key、Prompt、模型原文、完整私有数据或敏感异常。
- 阶段任务覆盖完整能力链；测试按独立风险合并，避免每个小改动重复全量回归。
- 上下文恢复默认只读热快照、当前状态和当前阶段 handoff；本文件只在明确需要进度历史时读取。

## 当前进行中

### code-index-semantic-coverage — 已完成

- 目标：将源码索引从“文件/符号可查”补强为“每个源码文件都有可恢复的层、职责和稳定性语义”，并让新增源码缺少分类时可被校验发现。
- 当前任务：扩展索引生成器的路径语义规则，并生成 `agent/` 全量职责地图；保留关键文件的精确 override，不读取或保存源码正文。
- 修改范围：`scripts/build_code_index.py`、`scripts/build_agent_module_map.py`、`scripts/validate_code_index.ps1`、`docs/code-index-overrides.json`、`docs/code-index.json`、`docs/agent-module-responsibilities.md`、恢复文档。
- 验证：索引生成、职责地图生成、语义覆盖率检查、索引校验、文档索引校验已通过；业务测试不因文档索引变更重复运行。
- 阻塞：无。M323 审批实现暂时不继续收口。
- 下一步：根据职责地图审计导入图和公共 seam，单独规划物理目录分类；不直接机械移动。

### agent-module-responsibility-map — 已完成

- 目标：一次性列出 `agent/` 下 168 个源码文件的当前职责、语义层、稳定性、阶段、导出数量和验证入口。
- 修改范围：`scripts/build_agent_module_map.py`、`docs/agent-module-responsibilities.md`、`docs/code-index-guide.md`、`docs/architecture-map.md`、`docs/document-index.json`、`docs/agent-work-state.md`。
- 验证：Docker 服务 healthy；本地生成器输出 168/168 职责覆盖；`validate_code_index.ps1`、`validate_document_index.ps1` 通过。
- 结论：职责盘点已完成，物理分类延后到下一阶段，需结合依赖图和 seam 再决策。

### agent-physical-layout — 规划完成

- 目标：将已盘点职责落实到 canonical 物理目录，保持公共导入和 Runtime 行为不变。
- 修改范围：新增 `docs/stages/agent-physical-layout/` capability map、Spec、Plan、handoff；更新文档索引与当前总计划。
- 首批：Application 支撑 → Persistence → Provider Integration；公共契约、Runtime 门面和稳定入口暂不机械移动。
- 验证：规划阶段仅完成文档索引校验；代码迁移后按批次运行 Docker compileall、canonical/legacy import smoke、architecture strict 和受影响契约。
- 阻塞：等待执行 P0/P1；M323 按用户要求暂停。
- 下一步：读取 P1 清单的导入关系，执行第一批 canonical move 与兼容 facade 收敛。

### agent-physical-layout-p0-domain-isolation — 已完成

- 目标：修复架构 strict 暴露的 GIS 根模块越界，让 GIS 数据与 demo adapter 归入 Domain Adapter。
- 修改范围：`agent/analysis_ready_binding.py`、`agent/release_evidence.py`、`agent/runtime_capabilities.py`、`agent/tools.py`、`domains/gis/adapters/`、GIS/脚本入口和架构清单。
- 发现：P1 将 `agent/artifact_store.py` 改为直接导入 `agent.application.service_async` 时触发 Application 包 eager import 循环，已改为 Application 包 lazy exports，host import smoke 通过。
- 验证：主机与 Docker compileall、architecture strict、canonical/legacy import smoke 通过；P0/P1 受影响契约 31/31 通过。
- 阻塞：无。
- 下一步：进入 P2 Persistence canonical move。

### agent-physical-layout-p1-application-support — 已完成

- 目标：将 Application Service 异步、格式化、会话和状态实现归入 `agent/application/`。
- 修改范围：四个 canonical 文件、四个根路径兼容 facade、Application 生产引用、惰性包导出、索引与守卫。
- 验证：Docker compileall、architecture strict、canonical/legacy import smoke 和受影响契约 31/31 通过。
- 备注：Application 包从 eager exports 改为 lazy exports，消除 `artifact_store → application.service_async → application.__init__ → run → artifact_store` 循环。
- 下一步：P2 Persistence。

### agent-physical-layout-p2-persistence — 进行中

- 目标：将 Artifact、SQLite、Memory 实现归入 `agent/persistence/`，保持旧导入可用。
- 修改范围：`agent/artifact_access.py`、`artifact_manifest.py`、`artifact_reference.py`、`artifact_store.py`、`artifact_viewer.py`、`memory.py`、`sqlite_store.py` 及其调用方。
- 验证：完成迁移后只运行 persistence/restart 紧凑契约、canonical/legacy import smoke、Docker compileall、architecture strict 和 readiness。
- 阻塞：无。
- 下一步：审计 P2 引用并迁移。

### agent-physical-layout-p2-persistence — 已完成

- 目标：将 Artifact、SQLite、Memory 实现归入 `agent/persistence/`，保持旧导入可用。
- 修改范围：新增 `agent/persistence/` canonical 实现与 `agent/` 根路径兼容 facade；Application、Runtime、HTTP 使用 canonical persistence 路径；离线 artifact HTTP 测试显式固定 `rule + memory`。
- 验证：Docker compileall、`architecture_check.py --strict`、Persistence/SQLite/artifact/restart 紧凑契约 28/28、canonical/legacy import smoke、生产 readiness HTTP 200 全部通过。
- 发现与处理：HTTP artifact 测试此前因继承真实模型产品默认值而超时，测试边界已固定离线 planner/backend，未改变产品默认真实模型。
- 阻塞：无。
- 下一步：进入 P3 Provider Integration，先审计四个 provider 实现及其调用图。

### agent-physical-layout-p3-provider-integration — 进行中

- 目标：将 Provider Integration 实现归入 `agent/integration/`，保持配置读取、结构化输出、provider runtime evidence 和旧导入语义不变。
- 当前任务：四个实现已迁入 `agent/integration/`；正在更新 code-index override 和 architecture compat 分类。
- 发现：canonical 包初始化文件的三引号生成错误导致 compileall/index 失败；仅修正该文件后再验证。
- 修改范围：暂限 `agent/openai_config.py`、`agent/provider_runtime.py`、`agent/provider_structured_output.py`、`agent/model_evidence.py` 及直接调用方/文档索引。
- 验证：迁移后运行 provider config/structured-output 紧凑契约、offline fake smoke、Docker compileall、architecture strict 和 readiness。
- 阻塞：无。
- 下一步：完成依赖审计后创建 canonical package 和单向兼容 facade。

### agent-physical-layout-p3-provider-integration — 已完成

- 目标：将 Provider config、structured output、runtime evidence、model evidence 归入 `agent/integration/`，保留根路径兼容入口。
- 修改范围：新增 `agent/integration/` 四个 canonical 实现和 lazy package；更新 Planner、Application、环境探测、HTTP 入口及 provider 验收脚本的 canonical imports；更新 architecture compat 清单和 code-index 规则。
- 验证：Docker compileall、`architecture_check.py --strict`、Provider 配置/结构化输出/runtime/model evidence 定向回归 48/48、canonical/legacy identity smoke、readiness 200、code-index 314/314 与语义覆盖 100% 全部通过。
- 发现与处理：Docker 生产环境的 `OPENAI_STRUCTURED_OUTPUT_MODE=json_object` 会污染验证 client 默认值，M288 单测已显式隔离该环境变量，生产配置优先级保持不变。
- 阻塞：无；未调用真实模型。
- 下一步：进入 P4 全局依赖重规划，审计 result/evidence/planning 的物理下沉收益与循环风险。

### agent-physical-layout-p4-global-replan — 已完成

- 目标：基于 P0～P3 迁移后的全局依赖图，决定 result/evidence/planning 是否存在值得实施的 canonical 物理 seam。
- 当前任务：P4 evidence canonical package 已完成，文档和最终交接已同步。
- 修改范围：`agent/evidence/`、根目录兼容 facade、code-index、architecture map、compatibility matrix、document-index 和阶段交接。
- 验证：Evidence 定向契约 23/23、Docker compileall、architecture strict、canonical/legacy import smoke、索引校验和 readiness 200 均通过；未调用真实模型。
- 阻塞：无。
- 决策：Evidence 迁移；Result Registry、Planning、Answer Generation 暂不迁移，避免公共/反向依赖风险。
- 下一步：阶段门禁通过后标记物理归类阶段完成，按全局目标重规划后再决定是否恢复 M323。

### M323：人工审批、持久化和 Registry 治理 — 实施中

- 目标：已验证的 M322 提案经过显式人工决策后，才能进入版本化 ToolRegistry；审批、拒绝、过期、撤销和重启恢复均可审计。
- 当前任务：M323-A，冻结 approval record、状态机、receipt fingerprint、版本和 HTTP 语义。
- 必要文件：`docs/document-index.json`、`docs/stages/M323/`、`scripts/resume_context.ps1`、`agent/tooling/proposal.py`、`agent/tools.py`、`agent/sqlite_store.py`、`agent/application/http.py`。
- 验证：文档索引和恢复脚本的 PowerShell/JSON/路径检查已通过；归档脚本 dry-run、真实归档和重复执行已通过；源码索引覆盖 299 个文件（260 Python、39 JavaScript）并通过 `validate_code_index.ps1`；代码变更后只运行受影响契约、compileall、architecture strict 和 readiness。
- 阻塞：无。不得自动批准、执行未经批准源码、绕过 ToolRegistry 或保存敏感模型数据。
- 下一步：读取现有 proposal/registry/SQLite/HTTP seam，随后实现 M323-A。

### M323-A-approval-state — 已完成

- 目标：冻结 approval record、状态转换、receipt fingerprint、版本和有界 decision receipt。
- 修改范围：先读取 `agent/tooling/proposal.py`、`agent/tools.py`、`agent/sqlite_store.py`、`agent/application/http.py` 的现有 seam；实现前不改 Runtime 主循环。
- 验证：Docker 中 M323-A 定向契约 6/6；M322 回归 7/7；语法检查通过。
- 阻塞：无。
- 下一步：接入 ServiceState/Runtime 的持久化与 approved Registry gate。

### M323-B/C-approval-publish — 已完成

- 目标：让等待审批的 ReAct 提案创建持久 approval record，批准后只通过 Registry 的受控 publish seam，撤销时移除绑定。
- 修改范围：`agent/service_state.py`、`agent/runtime.py`、`agent/runtime_factory.py`、`agent/tools.py`、`agent/tooling/approval.py`。
- 验证：M323 定向契约 11/11、M322 回归 7/7 通过；SQLite 重启恢复、过期筛选、Registry gate 和 stdlib HTTP contract 均覆盖。
- 阻塞：无。
- 下一步：进入 M323-D 收口和 M324 全局规划。

### M323-D-closure — 已完成

- 目标：完成共享 HTTPApplication 查询/批准/拒绝/撤销语义、最小验证、Docker 门禁和阶段交接。
- 修改范围：`agent/tooling/approval.py`、`tests/test_m323_tool_approval.py`、M323 交接/计划/文档索引及当前状态。
- 修复：测试使用独立临时 SQLite；恢复记录保留有界 Registry definition；SQLite expired 状态筛选包含到期 pending 行。
- 验证：Docker M323 11/11、M322 7/7；compileall、architecture strict、document-index、readiness 200 已通过。
- 阻塞：无；未调用真实模型，未保存源码、Prompt 或敏感信息。
- 下一步：全局规划 M324 前端/SSE/恢复/跨入口一致性。

### M323-A-source-index — 已完成

- 目标：完成 Python/JavaScript 文件、导出符号和本地导入的 compact code index，并接入恢复查询。
- 修改范围：`scripts/build_code_index.py`、`scripts/validate_code_index.ps1`、`docs/code-index.json`、`docs/code-index-overrides.json` 及交接索引文档。
- 验证：Docker 生成 299 个文件；`validate_code_index.ps1`、`validate_document_index.ps1` 和 `resume_context.ps1 -Topic RuntimeReactExecution` 通过；未运行全量业务测试。
- 阻塞：无。不得索引或提交密钥、Prompt、模型原文和私有数据。
- 下一步：进入 M323-A approval record 和状态机实现。

### M324-tool-governance — 已完成

- 目标：让 approved 动态工具在服务重启后受控再绑定，并在 Console 显示审批状态与允许动作。
- 已完成：M324-A～C 实现；新增 `agent/tooling/rehydration.py`、审批可见投影、Console 治理卡和
  精简后端/Node smoke；Registry 继续是唯一发布边界。
- 修改范围：`agent/tooling/rehydration.py`、`agent/tooling/approval.py`、`agent/tools.py`、
  `agent/runtime.py`、`agent/service.py`、`web/src/console_tool_approvals.js`、`web/src/console_app.js`、
  `web/src/index.html`、`web/src/styles.css`、M324 测试和 smoke。
- 验证：Docker M324 契约 6/6、M323/M322 回归 18/18、Node projection smoke、compileall、
  architecture strict、code/document index 和 readiness 200 全部通过。
- 阻塞：无；本阶段未调用真实模型，未保存源码、Prompt、模型原文或密钥。
- 下一步：进入 M325 真实模型 + Docker/GIS + 白名单搜索纵向验收。

### M325-global-planning — 已完成

- 目标：基于全局目标验证已有 ReAct、白名单搜索、真实 GIS、ToolRegistry 治理和实时交付链路，
  不为单一问句增加硬编码流程。
- 修改范围：新增 `docs/stages/M325/` 的 capability map、Spec、Plan 和 handoff；同步总计划、
  document index、工作快照和当前状态。
- 验证：文档结构已建立；M324 阶段门禁作为 M325 基线通过。
- 阻塞：无。M325-A 待执行真实 provider probe，配置值不输出。
- 下一步：在有界超时和显式开关下运行一次真实 provider probe，随后执行 Docker/GIS 与 ReAct 验收。

### M325-A-react-invalid-response — 进行中

- 目标：将真实模型 `call_tool` 缺少工具名且有限恢复仍无效的情况，稳定归类为规划阶段的 `invalid_model_response`。
- 必要文件：`agent/llm_planner.py`、`agent/errors.py`、`tests/test_m320_react_runtime.py`、`agent/runtime_core/run_lifecycle.py`。
- 当前发现：别名归一化和一次紧凑恢复均不应猜测工具名；最终 `ReactDecisionError` 未携带规划错误元数据，被生命周期按普通异常处理。
- 验证：先运行单个新增回归测试确认当前代码为红，再修复并重跑该测试与 M320 紧凑回归。
- 阻塞：真实复杂请求暂缓重试，避免重复消耗 provider；不保存模型原文、Prompt、密钥或私有数据。
- 下一步：修复错误边界，随后重新执行 Docker 中一次真实 ReAct + GIS 纵向验收。

### M325-A-react-invalid-response — 已完成

- 目标：将真实模型 `call_tool` 缺少工具名且有限恢复仍无效的情况，稳定归类为规划阶段的 `invalid_model_response`。
- 修改范围：`agent/llm_planner.py`、`tests/test_m320_react_runtime.py`、当前状态与交接记录。
- 修复：缺少必需 `tool_name`/`arguments` 时，在一次紧凑恢复仍失败后抛出不含模型原文的 `PlanningError`；策略拒绝和未注册工具仍保持原有 `ReactDecisionError` 语义，不猜测工具。
- 验证：Docker 回归 `M320ReactDecisionAdapterTests 8/8`、`tests.test_m320_react_runtime 17/17`；真实复杂请求随后已成功生成合法 `get_dataset_health_report` 动作。
- 阻塞：无。未保存 Prompt、模型原文、密钥或私有数据。
- 下一步：M325-B 使用一次性 Docker 容器显式挂载真实 `D:\dataset\agent` 和 Linux 容器数据配置，执行 GIS 健康与真实 ReAct 纵向验收。

### M325-B-docker-gis-readiness — 进行中

- 目标：确认真实 GIS 数据和依赖在 Docker 容器中可读取，避免将默认演示数据缺失误判为代码或模型问题。
- 发现：默认生产容器 `/data` 仅挂载项目 `data/`，其中只有经济示例文件；镜像默认配置要求 `湖北省_县.geojson`、analysis-ready DEM/土地利用和 `wuhan-osm.gpkg`，因此健康工具返回 `backend_initialization_unavailable`。
- 必要文件：`docker-compose.prod.yml`、`Dockerfile`、`config/datasets.container.earthquakes.example.json`、`domains/gis/domain.py`、`scripts/live_http_acceptance.py`。
- 验证：已确认 `D:\dataset\agent` 包含边界、analysis-ready DEM/土地利用、OSM GeoPackage、分析报告和 manifest；下一步只运行一次性 `docker compose run --no-deps` 显式数据卷验收。
- 阻塞：无；默认配置不改为私有宿主路径，不把真实数据复制进仓库。
- 下一步：启动 8090 临时 GIS 容器，执行真实 HTTP 请求并记录安全摘要；完成后清理临时容器，保留默认服务。

## 最近完成

<!-- archived-block-ref:document-index-restructure -->
### document-index-restructure — 已归档
- 详情：docs/archive/task-progress-history.md（归档块 document-index-restructure）

### M322：Python 工具提案与 Docker 沙箱 — 已完成

- 结果：完成 AST 校验、无网络 Docker sidecar、待审批 receipt；提案不会自动注册或在主进程执行。
- 验证：Docker M322 7/7；M318-M322 合并契约 43/43；compileall、architecture strict、smoke、readiness 200、sidecar socket 和 SQLite receipt 恢复通过。
- 交付：提交 `1b0bcdc` 已推送。

### M325：真实模型、Docker/GIS、白名单搜索与 ReAct 纵向验收 — 已完成

- 结果：真实模型 + Docker + `D:\dataset\agent` 本地 GIS 请求完成；一次真实请求在后续动作校验失败时，
  通过 `react_action_validation_recovery_finish` 基于已完成证据安全收束为部分结论，未伪造未执行步骤。
- 修复：`agent/react/loop.py` 对非策略类动作校验失败记录 blocked evidence 后执行有界部分恢复；
  权限、审批、执行策略和澄清/拒绝仍保持 fail closed。新增 M320 回归覆盖恢复和策略不恢复。
- 白名单：M321 搜索边界契约 **8/8**，覆盖成功来源、空白名单、越权来源、重定向、超大响应、HTML 投影、
  Registry 注册和 ReAct search executor；本阶段未访问外网。
- 验证：Docker M320 ReAct **21/21**、M325 Domain **1/1**、compileall、architecture strict、readiness
  **200** 通过；真实 async/artifact/polling/evidence 对比通过；SSE 事件 1～180 单调回放，
  `Last-Event-ID:100` 从 101 续传；容器重启后 run/artifact/evidence 恢复通过。
- 交付约束：真实数据仅以一次性只读卷挂载，未提交数据、密钥、Prompt、模型原文或完整私有结果。
- 下一步：M325 收口提交后，进行 M326 全局规划，优先解决真实模型多步计划完整性与开放请求的稳定交付，
  不增加单一区域或固定问句分支。

### M326-A：ReAct 增量动作与 workflow 策略解耦 — 进行中

- 目标：开放式 ReAct 的合法增量动作不被静态 workflow/template 蓝图过早阻断，同时保留
  ToolRegistry、Execution Policy、权限、审批、数据 readiness、依赖和预算门禁。
- 必要文件：`agent/react/loop.py`、`agent/runtime_core/react_runtime.py`、
  `agent/runtime_core/planning_surface.py`、`agent/runtime_core/execution_policy.py`、
  `domains/gis/domain.py`、`tests/test_m320_react_runtime.py`。
- 当前发现：真实 run 已完成真实 GIS 工具，但下一步增量计划校验命中 workflow/template 约束；
  当前仅允许非策略类校验失败做部分恢复，尚未区分“明确 workflow 蓝图”与“开放 ReAct”两种策略来源。
- 验证：先补最小红测试，再运行受影响 M320/M325 契约、compileall 和 architecture strict；不重复调用真实模型。
- 阻塞：无。不得通过放宽 Registry、权限、审批或数据门禁来绕过失败。
- 下一步：审计 `validate_plan_for_execution` 的调用来源，增加只对开放 ReAct 生效的策略投影，保持显式
  workflow 的蓝图校验不变。

### M326-A：ReAct 增量动作与 workflow 策略解耦 — 已完成

- 结果：开放 ReAct 的累计计划不再调用自动 Domain 模板的静态 `validate_plan` 蓝图约束；显式 workflow
  仍执行原有 `validate_workflow_plan`/`validate_plan`。Domain 可实现 `validate_open_react_plan` 提供
  开放模式额外安全校验。
- 修改：`agent/runtime_core/planning_surface.py`、`agent/runtime_core/execution_policy.py`、
  `agent/runtime_core/react_runtime.py`、`agent/runtime.py`、`agent/plan_policy.py`、
  `agent/domain_contract.py`、`tests/test_m320_react_runtime.py`。
- 验证：本地和 Docker `tests.test_m320_react_runtime` 均 **23/23**；覆盖多步开放动作、依赖、非法参数、
  SQLite evidence 恢复、开放模式 Domain 安全门禁和 policy evidence 来源。
- 安全边界：ToolRegistry、schema、权限、审批、数据 readiness、依赖和 Runtime 动作/轮次预算未放宽；
  未调用真实模型，未保存 Prompt、模型原文、密钥或私有数据。
- 下一步：M326-B 统一部分结果、停止原因、已完成动作数和可重试性的公共 Result/evidence 投影。

### M326-B：部分结果与停止原因 — 进行中

- 目标：让 ReAct 的 finished/partial/blocked/等待决策状态在 Result、evidence、artifact、轮询和 SSE
  中保持同一语义，答案生成不误报未完成步骤。
- 当前状态：尚未修改代码；下一步只建立最小红测试并读取 ReAct contracts、Result 投影和生命周期收束 seam。

### M326-B/C：结果完整性与答案语义 — 已完成

- 结果：新增 `spatial-agent.result-completeness.v1`，统一 `complete`、`partial`、`blocked`、`waiting_decision`、
  `pending`，并保留计划/尝试/完成/阻断动作数、停止原因、可重试性和不确定性；Composite 父结果会在子组件 section
  挂载后重算完整性，避免 `COMPLETED` 传输状态掩盖部分子结果。
- 修改范围：`agent/result_completeness.py`、`agent/evidence/projection.py`、`agent/nested_schema.py`、
  `agent/persistence/artifact_manifest.py`、`agent/persistence/artifact_viewer.py`、`agent/runtime_core/react_runtime.py`、
  `agent/runtime_core/projection.py`、`agent/application/composite_contract.py`、`agent/application/composite_view.py`、
  `agent/answer_generation.py` 及 `tests/test_m326_result_completeness.py`。
- 验证：本地 `M326 + M177 + M178 + M320` 定向回归 39/39；本地 M281 HTTP 用例因缺少 FastAPI 未完成，转 Docker
  复验；未调用真实模型，未保存 Prompt、模型原文、密钥或私有结果。
- 下一步：M326-D 使用 Docker 重建镜像，完成跨入口字段一致性与真实模型/GIS 显式验收。

### M326-D-artifact-atomic-publish — 进行中

- 目标：修复异步完成状态与 Artifact 文件可读取性之间的竞态，确保 HTTP、轮询、Artifact 和恢复不会看到半写入 JSON。
- 复现：Docker 重建后运行 `scripts/live_http_acceptance.py --planner rule --backend memory --domain gis --request '查询DEM栅格元数据'`，首次出现 `non-JSON response for GET /domains/gis/artifacts/runs/<id>.json`；同命令重试通过，确认是间歇性发布问题。
- 根因定位：`agent/persistence/artifact_store.py` 的 `ArtifactStore.write_run()` 直接对最终路径调用 `Path.write_text()`，多次更新 Artifact 时读者可能看到截断内容。
- 必要文件：`agent/persistence/artifact_store.py`、新增最小 Artifact 原子发布回归测试、M326-D 交接文档。
- 下一步：先用并发读写回归锁定“旧 Artifact 始终可解析”，再使用同目录临时文件和原子替换发布；Docker 只运行该回归及跨入口验收。
- 阻塞：无；不保存模型原文、Prompt、密钥或真实数据。

### M326-D-live-acceptance-guard — 进行中

- 目标：真实模型验收必须确认模型结构化响应成功，不能把 live provider 失败后的降级结果当成成功。
- 发现：真实 GIS 多步请求调用 `deepseek-v4-flash` 1 次、0 重试，`model_evidence.status=error`、`error_type=response_json_error`，结果为 `partial`；当前 `scripts/live_http_acceptance.py` 只检查最终状态 `COMPLETED`。
- 必要文件：`scripts/live_http_acceptance.py`、`tests/test_m326_artifact_atomicity.py`、M326-D 交接文档。
- 下一步：补 live evidence 判定和离线回归，再用一次简短真实 GIS 请求验证；不保存模型原文、Prompt、密钥或私有结果。

### M326-D-live-empty-response — 进行中

- 目标：将 provider 的空结构化 content 统一归类为 `planning/invalid_model_response`，保持失败可恢复语义。
- 发现：真实请求中模型证据为 `status=success`，但 content 为空；新解析器抛出 `ValueError("structured response is empty")`，未被 `complete_json()` 转换为 `PlanningError`。
- 必要文件：`agent/llm_planner.py`、`tests/test_m326_provider_json_compat.py`。
- 下一步：先补空 content 的 Planner 回归，再修复异常映射并在 Docker 中复跑；不重复调用 provider，除非代码修复后确需一次验收。

### M326-D-live-plan-budget — 进行中

- 目标：在不改变代码契约的前提下，用一次受控配置验证 Planner 空 content 是否由输出预算不足引起。
- 变量：临时 GIS 容器使用 `OPENAI_MAX_OUTPUT_TOKENS=8192`、`OPENAI_MAX_RETRIES=0`、`OPENAI_TIMEOUT_SECONDS=120`；默认服务配置不变。
- 约束：只执行一次真实多步请求；成功必须同时满足 live model evidence 成功、GIS 工具执行完成和 HTTP/Artifact/Evidence/SSE 对照。

### M326-D-live-result-shape — 进行中

- 目标：补充一种与多步栅格/通用结果不同的真实模型矢量结果形态。
- 已完成：真实模型多步请求 1 次调用、0 重试，计划 3 个动作、完成 2 个、1 个动作校验阻断；Result 明确为 `partial` 且可重试，HTTP/Artifact/Evidence/SSE 对照通过。
- 下一步：用同一临时 GIS 容器执行一次“洪山区行政区边界”短请求，记录安全结果类型/动作数量；随后不再重复 live。

### M326-D/E：跨入口验收与阶段收口 — 已完成

- 结果：完成 Artifact 同目录临时文件 + 原子替换发布；异步完成状态与 Artifact 可读取性不再暴露半写入 JSON。
- 结果：Provider 原始 JSON、完整 Markdown JSON fence、完整 `<think>` 包裹均受控解析；空 content/非法 JSON 统一归类为
  `planning/invalid_model_response`，不保存模型原文。
- 结果：live 验收脚本必须确认 `available=true`、`execution_mode=live_model` 和 `status=success`，不能把 fallback 当作真实模型成功。
- 验证：Docker 阶段紧凑回归 `49/49`；Artifact/Provider 定向回归、compileall、architecture strict、readiness `200`、
  sync/async/artifact/restart/evidence/view 对照和 SSE/Last-Event-ID 续传均通过。
- 真实验收：一次真实模型 + Docker/GIS 多步请求执行 2/3 动作后安全收束为可重试 `partial`；一次矢量结果形态请求完成安全验收。
  真实数据只读挂载且临时容器已清理，未保存密钥、Prompt、模型原文或完整私有结果。
- 交付：M326 交接、当前状态、问题日志和 document/code index 已收口；M327 全局重规划的 Capability Map、Spec、Plan 和 handoff 已建立。

### M327：开放请求能力发现与结果质量 — 规划完成

- 目标：从产品、Runtime、Domain、数据、模型、部署、体验和测试七个维度，补齐能力描述、选择解释和跨类型结果摘要，
  不为固定区域、问句或 GIS 页面增加专用分支。
- 入口：`docs/stages/M327/capability-map.md`、`spec.md`、`plan.md`、`handoff.md`。
- 当前任务：M327-B 能力选择与用户可见解释；只读取 Catalog、Result/Evidence 和当前紧凑回归相关文件。
- 边界：首版不引入 RAG、自动下载或模型生成工具自动上线；保持 Registry、权限、审批、网络白名单、数据 readiness 和结果校验。
- 阻塞：无。

### M327-A：能力描述契约 — 已完成

- 结果：新增 `agent/capability_descriptor.py`，提供版本化 `spatial-agent.capability-descriptor.v1` 投影，统一表达输入事实、
  数据前置条件、输出 Result 类型、证据要求、执行工具、成本提示和可用性。
- 接入：`capability_catalog()` 为所有 Domain Pack 暴露 `capability_descriptors` 和 descriptor schema/count；保留既有
  `capabilities` 字段，兼容旧调用方，不修改 Runtime 生命周期或执行门禁。
- 安全：descriptor 只保留有界公开元数据；缺失身份或未知 schema 的 descriptor 不进入 Planner 可用投影，未知扩展字段不被传播。
- 验证：Docker M327-A 与相邻 Catalog/requirements 回归 `28/28`，覆盖文本非 GIS Domain、GIS 兼容字段、未知版本和可变性隔离。
- 下一步：M327-B 将 descriptor 接入 Planner context，并生成脱敏的能力选择解释 evidence。

### M327-B：能力选择与用户可见解释 — 已完成

- 实现：Planner context 的 capability catalog 现在携带有界 descriptor 摘要，优先保留发现候选；LLM Planner
  将 descriptor 视为能力选择元数据，workflow template 仅作为兼容执行提示，不改变 Registry、权限、审批和 readiness 门禁。
- 实现：新增 `agent/capability_selection.py`，提供版本化 `spatial-agent.capability-selection.v1`，统一记录
  chosen/selected capability、candidate ids、缺失事实、选择原因、来源、匹配信号和安全候选摘要。
- 接入：成功计划、无计划失败、Result contract、evidence projection、evidence registry、异步/Artifact 公共投影均保留
  同一能力选择 identity；descriptor 和 receipt 不含 Prompt、模型原文或工具参数。
- 修改：`agent/capability_catalog.py`、`agent/planner_context.py`、`agent/llm_planner.py`、
  `agent/runtime_core/planning_surface.py`、`agent/runtime_core/plan_evidence.py`、`agent/runtime.py`、
  `agent/capability_selection.py`、`agent/evidence/projection.py`、`agent/evidence/registry.py`、
  `agent/application/service_async.py`、`result_contract.py`、`tests/test_m327_capability_selection.py`。
- 验证：Docker M327-B 专项 `8/8`；相邻能力/evidence/async/selection 回归 `21/21`；规则 Runtime 实际链路、compileall、
  architecture strict、code/document index 校验均通过。不调用真实模型，不保存敏感内容。
- 下一步：进入 M327-C，统一矢量、栅格、指标和文本结果的跨类型摘要输入与输出契约。

### M327-C：跨类型结果摘要 — 契约冻结

- 目标：让公共 Runtime 用同一个有界 projection 表达矢量、栅格、指标、时间序列、文本和文档证据结果，
  并让 Composite View 与答案生成共享该输入。
- 已完成：补充 M327-C Spec/Plan/handoff；冻结 `spatial-agent.result-summary.v1` 的输入、block、facts、限制和
  evidence 边界。摘要不传播 Prompt、模型原文、工具参数、路径、几何 features、密钥或任意内部引用。
- 必要文件：`agent/result_summary.py`、`agent/application/composite_view.py`、`agent/answer_generation.py`、
  `agent/contract_versions.py`、`tests/test_m327_result_summary.py`。
- 下一步：实现领域中立摘要 projection，接入 Composite View 与答案 context，再运行三类结果紧凑回归。
- 阻塞：无；不调用真实模型，不保存真实私有结果。

### M327-C：跨类型结果摘要 — 已完成

- 实现：新增 `agent/result_summary.py`，提供版本化 `spatial-agent.result-summary.v1`，统一输出 conclusion、key findings、
  limitations、evidence 和 typed blocks；支持 vector/raster/metrics/timeseries/text/document_evidence/composite。
- 接入：公共 `result_contract`、Composite Result/View 和答案生成 context 共用同一投影；技术 facts 有界保留，Prompt、模型原文、
  工具参数、路径、几何 features、内部引用和密钥均不传播；答案提示优先使用结论、关键发现、限制与证据来源。
- 兼容：答案上下文增加无 `to_dict()` 的轻量结果对象适配，保持旧流式测试及正式 `AgentRunResult` 路径一致。
- 修改：`agent/result_summary.py`、`agent/contract_versions.py`、`agent/nested_schema.py`、`result_contract.py`、
  `agent/application/composite_contract.py`、`agent/application/composite_view.py`、`agent/answer_generation.py`、
  `tests/test_m327_result_summary.py` 及 M327 文档。
- 验证：Docker M327-C 专项 `4/4`；受影响 Result/答案/Composite 回归 `26/26`；答案流相邻回归 `5/5`；compileall、
  architecture strict、代码索引（328 文件、语义覆盖 100%）和文档索引通过。
- 下一步：进入 M327-D，统一跨入口消费并接入 Console 的公共摘要；不在本阶段增加 GIS 页面专用分支。

### M327-D：跨入口与前端接入 — 已完成

- 实现：同步 `Result`、异步结果 evidence、Artifact 顶层、普通恢复证据和 Composite evidence 统一消费
  `spatial-agent.result-summary.v1`；同步/恢复响应提供同值顶层别名，嵌套 Result 仍是规范来源。
- 实现：Console Result Projection 优先读取统一摘要，动态展示结论、关键发现、结果明细、限制和证据来源；
  不依赖 GIS 页面分支，地图/图表仍由 Renderer Registry 作为可选 View。前端对有界对象值进行可读格式化，
  不再出现 `[object Object]`。
- 修改：`agent/application/service_async.py`、`agent/application/run.py`、`agent/application/service_format.py`、
  `agent/application/run_recovery.py`、`agent/application/composite_runs.py`、`agent/persistence/artifact_store.py`、
  `web/src/console_result_projection.js`、`web/src/styles.css`、`scripts/console_result_projection_smoke.js`、
  `tests/test_m327_cross_entry_projection.py` 及 M327 交接文档。
- 验证：Docker M327-C/D 与相邻紧凑回归 `16/16`，跨入口 Artifact/恢复/异步摘要一致性 `2/2`，前端结构化
  projection smoke、Node 语法、Docker compileall 和 architecture strict 通过；strict 仅保留既有 runtime/service
  God module 警告。
- 下一步：进入 M327-E，运行 Docker 阶段门禁与 readiness；环境可用时完成一次显式真实模型 + Docker/GIS 验收，
  再做七维度全局重规划并提交阶段版本。

### M327-E：Docker/live 验收与阶段收口 — 已完成

- 修复：`scripts/live_provider_probe.py` 的 live Composite 输出预算上限从 4096 提升为有界 12000，避免验收脚本
  把复杂计划截断误报为 JSON 错误；Composite Planner 明确只选择 `available=true` 且 `execution_ready=true` 的候选。
- 修复：ReAct proposal 提示明确 source 仅可出现在 `proposal.source`，并声明六个必需字段、有限 JSON Schema
  关键字和 sandbox 允许的纯函数语法；未放宽 Registry、AST、sandbox 或人工审批门禁。
- 验证：Docker 受影响紧凑回归 `66/66`；compileall、architecture strict、readiness `200`、Console projection smoke 通过。
- 真实 Composite：DeepSeek 一次结构化规划选出 GIS+经济两组件；异步执行两组件完成，结果含 composite/vector/metrics，
  Artifact 与 `spatial-agent.result-summary.v1` 可读。
- 真实 Web/数据：经济本地数据步骤完成，明确请求触发 `web_search`；实际返回 `search_network_error/unavailable`，
  本地数据继续处理且没有伪造网页来源；HTTP/Artifact/SSE/Last-Event-ID 对照通过。
- 真实工具提案：模型 proposal 经过有限 Schema、AST 和 Docker 无网络 sandbox 校验，运行进入 `WAITING_FOR_DECISION`；
  未执行、未发布，receipt 不含 source/example。
- 真实流式回答：两次真实经济运行分别产生 `512`、`331` 个 `answer_delta`，均回放到 terminal；未保存模型正文、Prompt、
  密钥、网页正文或完整私有结果。
- 下一阶段：已完成七维度全局规划，建立 `docs/stages/M328/{capability-map.md,spec.md,plan.md,handoff.md}`；
  M328-A 从审批后的运行恢复闭环开始。

### M328-A：审批后的运行恢复闭环 — 已完成

- 目标：让工具提案从 `WAITING_FOR_DECISION` 经审批后恢复原运行，审批前不执行，并用同一 run identity、proposal version 和 receipt fingerprint 保护 Registry binding。
- 已确认：`RuntimeReactExecution` 已保存 bounded proposal receipt，但没有把 approval record 关联到 run；`Service.resolve_tool_approval` 只发布/撤销工具，不继续等待中的 run。
- 实现：approval record/store 保存有界 `run_id`；ToolRegistry binding 和 execution-policy allowlist 支持动态审批工具；新增 `RuntimeToolApprovalResume`，批准后从安全 ReAct 历史继续原 run，拒绝/撤销/过期安全结束。
- 实现：Service approval 入口按同一 run identity 恢复并通过统一 RunApplication 投影结果；ReAct loop 支持续跑参数；旧 SQLite approval payload 兼容读取。
- 修改：`agent/tooling/approval.py`、`agent/tooling/rehydration.py`、`agent/tools.py`、`agent/react/loop.py`、`agent/runtime_core/react_runtime.py`、`agent/runtime_core/execution_policy.py`、`agent/runtime_core/tool_approval_resume.py`、`agent/runtime_core/run_lifecycle.py`、`agent/runtime.py`、`agent/application/run.py`、`agent/service.py`、`tests/test_m328_tool_approval_resume.py`。
- 验证：Docker M328-A 专项 `3/3`；M322/M323/M324 相邻回归 `26/26`；compileall 通过。
- 下一步：进入 M328-B Web evidence 可用性；阶段显式验收时再执行一次真实模型 proposal 审批闭环。

### M328-B：Web evidence 可用性 — 已完成

- 目标：让公开网页搜索的成功、无结果、部分结果和网络不可用在公共 Result Summary 中保持同一可验证契约，
  并由答案与前端显示来源状态和限制。
- 实现：`result_summary` 新增文档证据归一化，安全保留 bounded HTTPS source record（标题、链接、域名、摘要）、
  status、reason_code、query 和 allowlist；无结果、不可用与部分可用分别映射为 `no_results`、`unavailable`、
  `degraded`，不将网络失败伪装为来源成功。
- 实现：Console Result Projection 只消费结构化 `source_records`，安全校验链接并渲染来源列表；不再把来源对象
  转成 `[object Object]`，也不把技术失败信息当作网页正文展示。
- 修改：`agent/result_summary.py`、`web/src/console_result_projection.js`、`web/src/styles.css`、
  `tests/test_m328_web_evidence.py`、`scripts/console_result_projection_smoke.js`。
- 验证：Docker M321 Web、M328-B、M327 Result Summary、M328-A 回归 `17/17`；前端结果投影 smoke 通过；
  Docker 服务重建成功。
- 下一步：进入 M328-C，完成经济/指标/Web 的多步骤真实回答，并验收 proposal 审批后的同一运行恢复。

### M328-C/D/E：跨域开放行动、实时体验与阶段收口 — 已完成

- 实现：Composite/Domain ReAct 共享当前 Runtime Registry、Execution Policy 和 `result_summary`；未增加固定区域、
  固定问句或 GIS 专用 Runtime 分支。
- 修复：审批恢复补充有界 `tool_approval_accepted` history；ReAct 每轮读取动态 Registry 工具；基础 Provider 工具
  集合与动态审批工具解耦，避免 Runtime context fingerprint 漂移。
- 验收：真实经济多步本地数据 + `web_search` 共 4 个工具步骤；Web 安全返回
  `unavailable/search_network_error`，本地结果继续保留且未伪造来源。真实工具提案已完成 sandbox 校验、人工审批、
  同一 Run 恢复和动态工具实际执行。
- 最终回归：Docker 重建后 M322/M323/M324/M328 紧凑回归 `32/32`；离线 smoke、compileall、architecture strict、代码索引、
  文档索引、readiness `200` 和前端结果投影 smoke 全部通过。
- 真实复杂验收：经济本地数据 + `web_search` 完成 4 个工具步骤，`COMPLETED`，SSE 420 事件并成功 Last-Event-ID 续传；
  经济目录 + 区域指标目录由真实模型规划为 2 个组件并全部完成；真实工具提案经过 sandbox、人工审批、同一 Run 恢复后
  实际执行成功，审批前 0 步、审批后 1 步。
- 真实边界验收：过宽请求和缺少具体指标的请求返回结构化 `NEEDS_CLARIFICATION`；Provider 组件字段漂移返回
  `plan_component_field_invalid`，均未创建执行 Run。
- 安全边界：只记录脱敏状态、动作/事件计数、reason code、结果完整性、SSE 续传和答案流计数；不保存密钥、Prompt、
  模型原文、网页正文、工具 source 或私有路径。

### M329-0：阶段初始化与恢复入口收敛 — 已完成

- 目标：建立通用请求路由与跨域能力汇聚阶段的 capability map、Spec、Plan、handoff，并把热恢复入口切换到 M329。
- 实现：新增 `docs/stages/M329/{capability-map.md,spec.md,plan.md,handoff.md}`；精简并更新
  `docs/agent-work-state.md`、`tasks/current-state.md`、`tasks/plan.md` 和 `tasks/todo.md`。
- 约束：单 Agent、最大并发度 1；默认恢复只读热状态、当前阶段 handoff 和必要源码；不读取模型原文、Prompt、密钥或完整历史。
- 验证：`81e79ab` 基线干净；文档文件已创建，代码尚未修改，M329-A 进入执行队列。
- 下一步：实现 `spatial-agent.request-mode.v1`，接入 Result、SQLite/artifact、execution record 和终态事件。

### M329-A：Request Mode 契约 — 已完成

- 目标：用统一、领域中立的模式描述直接回答、工具执行、混合回答和澄清，避免新增模型分类调用。
- 实现：新增 `agent/request_mode.py`；`AgentRunResult`、SQLite 恢复、execution record 和终态 RunEvent 接入
  `spatial-agent.request-mode.v1`，仅公开模式、原因、工具计数和执行是否开始。
- 兼容：旧快照没有 `request_mode` 时仍可恢复；非法可选字段归一化为安全的 answer 投影。
- 验证：Docker `tests.test_m329_general_route` 共 `4/4` 通过。
- 下一步：M329-B 聚合已注册 Domain Pack 的 capability/provider，并实现 owner dispatch 和局部不可用降级。

### M329-B：通用 Capability Host — 已完成

- 目标：把已登记 Domain Pack 的 capability、provider、权限、健康状态和结果类型汇聚到一个领域中立 Host，
  为通用 Runtime 提供唯一 ToolProvider seam。
- 实现：新增 `agent/general_capability_host.py`；`GeneralCapabilityHost` 提供有界聚合 catalog、唯一 tool owner map、
  ToolRegistry-compatible `definitions/invoke`、Domain-owned `preflight_tool` 转发、结果导出 owner 记录和稳定 context fingerprint。
- 降级：provider 初始化或健康异常只标记对应 Domain 为 `degraded/unavailable`；不影响其他 provider 或无工具直接回答。
- 安全：能力 ID、工具名、实际结果类型重复跨 Domain 时 fail-closed；未被能力/工作流/工具输出引用的旧兼容结果条目不进入
  公共结果平面，避免遗留元数据制造假冲突；没有动态重命名、反射 dispatch 或敏感错误传播。
- 验证：Docker 重建后 `tests.test_m329_capability_host` 与 `tests.test_m329_general_route` 共 `8/8`；四个内置 Domain Pack
  聚合为 `22` 个工具、`32` 个能力、`31` 个实际结果类型并报告 `ready`；ToolRegistry 实际调用文本与经济 provider 成功。
- 下一步：M329-C 构建通用 Runtime Pack/Factory，接入默认 `/runs`、CLI 和前端，同时保留显式 Domain Runtime 隔离。

### M329-C-1：通用 Runtime Pack/Factory — 已完成

- 目标：把 `GeneralCapabilityHost` 接入现有 Runtime 生命周期，提供领域中立的请求事实合并、能力发现、结果注册和 fallback。
- 实现：新增 `agent/general_runtime.py` 的 `GeneralRuntimePack`、`GeneralResultRegistry`、`GeneralAnswerComposer` 和诚实的
  离线规则 Planner；新增 `build_general_runtime` 与提交时上下文快照 factory。
- 兼容：显式 `build_runtime(..., domain_id=...)` 不变；通用 Runtime 使用 `general` 身份和 Host provider，结果 View/来源仍按
  唯一结果 owner 转发；不在公共 Runtime 代码引入 GIS 专用策略。
- 验证：Docker 重建后 Host/Request Mode/General Runtime 紧凑回归 `9/9`；通用规则 Runtime 完成 direct-answer，聚合 Host
  使用 `23` 个工具并报告 `32` 个能力、`ready` 健康状态。
- 下一步：M329-C-2 验证通用 Runtime 的真实模型 full ReAct、Web 搜索、工具提案和领域中立降级。

### M329-C-2：真实模型与开放行动默认配置 — 已完成

- 实现：默认 Agent 设置保持 `full ReAct`、白名单 Web 搜索和工具提案开启；提案仍由 Docker sandbox 校验并等待人工审批，
  不自动注册或执行。修复 Host provider 不可用时 descriptor `availability` 的契约形状，并为 Host 增加公开 backend 属性。
- 真实验收：DeepSeek + Docker 普通通用问题 `COMPLETED`；跨域经济请求实际调用 `economic_list_indicators` 与
  `economic_indicator_query`；白名单 Web 请求实际调用 `web_search` 并在网络不可用时返回
  `document_evidence/unavailable/search_network_error`；新工具请求进入 `WAITING_FOR_DECISION`，审批状态为 pending。
- 验证：Docker 重建成功，M329 紧凑回归 `10/10`；未保存密钥、Prompt、模型原文、网页正文或工具 source。
- 下一步：M329-D 将产品 HTTP、CLI 和前端默认切换到 `general` Runtime，同时保留显式 Domain 入口。

### M329-D：通用 Runtime 产品入口 — 已完成

- 实现：`AgentService(general=True)` 使用通用 Runtime factory 和通用提交上下文；production FastAPI、stdlib `serve_api.py`
  默认服务改为 general，CLI `--domain` 默认加入并选择 general。显式 `/domains/{domain_id}` 和 `--domain gis/text/...`
  仍走原 Domain Runtime。
- 验证：Docker `/capabilities` 返回 `general` 与 32 个能力；`/runs`、`/runs/preview`、`/runs/async`、`/runs/{id}`、
  `/runs/{id}/events` 和 Artifact 均完成通用身份/契约验证；`/domains/text/runs` 仍返回 `text`。Docker 端 M329 回归 `10/10`。
- 下一步：进入 M329-E，验证 SQLite/Artifact 重启恢复、多轮会话、SSE/Last-Event-ID 和审批恢复，再进行阶段收口。

### M329-E/F：恢复验收与阶段交付 — 已完成

- 验收：临时 SQLite + Artifact 重启后同一 Run、`general` 身份、结果摘要和事件可恢复；重启后的同一会话可继续运行，
  会话 Run 数保持一致。HTTP SSE 使用 `Last-Event-ID=6` 时只回放 7–13 号事件并包含终态。
- 验收：真实 HTTP 通用 Runtime 提案先返回 `WAITING_FOR_DECISION`，审批后沿同一 `run_id` 恢复并 `COMPLETED`；没有自动发布，
  既有显式 Domain proposal resume 回归继续通过。
- 阶段门禁：Docker M329/M328 相关紧凑回归 `18/18`，答案生成定向回归 `15/15`；compileall、architecture strict、readiness
  `200`、code-index `333/333` 且语义覆盖 `100%`、document-index 和 Console projection smoke 均通过。
- 质量修复：答案生成上下文把内部 `EXECUTING` 明确投影为 `FINALIZING`，真实模型复验不再输出“仍处于执行中”。
- 交付：M329 全部任务完成，下一阶段从全局目标重新规划 M330；不默认读取 M327/M328 完整历史、模型原文、Prompt、密钥或
  全量测试。
### M330-A：通用直接回答场景矩阵 — 进行中

- 开始：已将热状态、当前阶段交接和必要源码入口切换到 M330-A；本子任务不增加固定问句路由。
- 当前动作：固定非 GIS/经济的概念解释、比较、总结、写作和简单计算场景，验证公共 `general` Runtime 的 direct-answer、
  `request_mode=answer`、无工具步骤和领域中立降级契约。
- 下一步：补充场景矩阵文档与紧凑契约测试；完成后再做一次显式真实模型验收。

### M330-A：通用直接回答场景矩阵 — 实现完成

- 实现：新增 `docs/stages/M330/direct-answer-scenarios.md`，固定概念解释、比较、总结、写作和简单计算五类无数据场景，
  统一断言 `request_mode=answer`、`direct_answer`、0 个工具步骤和领域中立 fallback。
- 修改：`agent/answer_generation.py` 允许不依赖外部数据的通用请求使用用户请求直接回答；实时、地域和专门外部事实仍要求证据。
  新增 `tests/test_m330_direct_answer.py`。
- 验证：Docker 重建后 M330-A 紧凑测试 `4/4` 通过；初次失败仅为测试夹具缺少 `metrics` 和误调用不存在的 runtime `close()`，已修复。
- 当前动作：运行答案生成/通用入口相邻回归，并执行一次显式真实模型通用直接回答验收；不保存模型原文、Prompt 或密钥。

### M330-B：开放请求与能力发现 — 实现完成

- 实现：`GeneralCapabilityHost` 从声明式 workflow blueprint 受控解析工具与操作对应的公共 Result 类型；`ToolRegistry` 和
  ReAct 执行 seam 支持传入已校验参数。General Runtime 使用已发布 Result Registry 的严格 allowlist，可信目录推导优先于
  模型标签，歧义/未知结果保持 fail-closed。
- 修改：`agent/general_capability_host.py`、`agent/tools.py`、`agent/runtime.py`、`agent/general_runtime.py`、
  `agent/runtime_core/react_runtime.py`、`tests/test_m330_open_capability.py`。
- 验证：Docker M330-B 合并回归 `23/23`；真实模型能力选择为 `COMPLETED`、`general`、`mixed`、1 个已完成工具步骤、
  `economic_catalog_result` 和 live-model answer evidence；不保存模型原文、Prompt 或密钥。
- 下一步：M330-C 执行 Web 成功/无结果/网络失败、工具提案审批恢复、局部 provider 降级和澄清/重试/取消边界。

### M330-C：开放行动与故障恢复 — 实现完成

- 验证：Docker 紧凑回归 `15/15` 通过，覆盖 Web evidence 状态、Provider 降级、ReAct 预算/澄清/参数校验和提案恢复。
- 显式真实验收：工具提案在审批前进入 `WAITING_FOR_DECISION` 且 0 步；批准后恢复同一 Run，`COMPLETED`、执行 1 步、
  答案流开启。30 秒首次 HTTP 超时，扩大到 60 秒有界时限后通过，归类为 provider 延迟。
- 安全边界：Web 网络不可达保持 `unavailable/search_network_error`；提案继续经过 sandbox 和人工审批，不自动上线。
- 下一步：M330-D 验证 RunEvent、SSE/Last-Event-ID、轮询、Artifact 和前端动态投影。

### M330-D：实时产品体验 — 实现完成

- 验证：Docker compileall、architecture strict、readiness/home `200`、结果投影 smoke 和 RunEvent smoke 全部通过；保留既有
  `runtime/service God module` warning，无 architecture error。
- 默认 HTTP `/runs` 真实模型直答返回 `general`、`COMPLETED`、`answer`、`direct_answer` 和 live-model answer evidence；
  默认异步 HTTP/SSE/Artifact 验收的轮询、artifact、证据端点和 Last-Event-ID 回放一致。
- 说明：`/runs/auto` 是自动 Domain 选择入口，选到 GIS 属于既有语义；产品默认 `/runs` 已明确使用 `general`。

### M330-E：阶段综合验收 — 实现完成

- Docker 合并紧凑回归 `31/31` 通过，覆盖 M330-A/B、M329 通用 Host/入口/答案和 M328 Web/提案恢复；smoke、compileall、
  architecture strict、代码索引、文档索引、readiness 和前端事件投影均通过。
- 真实模型验收覆盖非数据直答、能力目录选择、Web 不可用降级、sandbox+人工审批同一 Run 恢复和默认 HTTP 异步/SSE/Artifact；
  只保留脱敏状态、模式、动作计数、结果类型、evidence 和事件序列。
- 阻塞：无。前一轮 30 秒提案请求超时在 60 秒有界时限下通过，归类为 provider 延迟而非功能失败。

### M330-F：阶段交付与全局重规划 — 进行中

- 当前动作：更新热状态、交接、里程碑和索引，执行 diff 检查后提交并推送 M330 版本。
- 下一步：推送完成后，从产品、Runtime、Planner、Domain、数据、模型、部署、体验和测试全局规划下一阶段。

### M330-F：阶段交付与全局重规划 — 已完成

- 实现：更新 M330 Plan、handoff、热状态、任务计划、进度账本、里程碑、代码/文档索引，并建立 M331 capability map、Spec、
  Plan 和 handoff；恢复入口切换到 M331-0。
- 交付：M330 版本已提交并推送；未纳入私有配置、密钥、Prompt、模型原文、网页正文、工具源码或私有数据。
- 下一阶段：M331 聚焦真实模型开放任务可靠性、有限修复、通用组合、长任务上下文、恢复和答案体验，不引入 RAG 或无边界执行。

### M331-0：阶段初始化与全局规划 — 进行中

- 当前动作：只保留 M331 规划入口和最小热状态；下一步进入 M331-A，建立真实模型结构化输出 conformance 场景矩阵。

### M331-0：阶段初始化与全局规划 — 已完成

- 交付：M330 已提交并推送为 `0ce3ba4`；代码索引、模块索引和文档索引重新生成并通过校验。
- 规划：M331 已建立 capability map、Spec、Plan 和 handoff；当前按全局目标进入模型协议与有限修复，不新增固定问句或领域专用分支。
- 下一步：M331-A 建立脱敏 conformance 场景矩阵，并从现有 Planner/ReAct/Answer 解析入口抽取最小公共修复边界。

### M331-A：模型协议与有限修复 — 进行中

- 开始：已将热状态和交接入口切换到 M331-A；当前只读取模型结构化响应解析、Provider 错误分类和直接相关测试。
- 当前动作：梳理字段漂移、截断 JSON、错误结果类型、漏字段、额外字段和 timeout 的统一处理方式；不保存模型原文。
- 下一步：形成可脱敏的场景矩阵并补最小公共解析/修复 seam，再执行 Docker 定向验证。

### M331-A：模型协议与有限修复 — 已完成

- 实现：新增 `agent/integration/structured_response.py`，统一 Planner、ReAct、普通答案和 Composite 答案的一次 compact recovery、
  无歧义字段别名修复和稳定失败分类；ReAct 语义修复改为共享 compact 调用 seam，恢复响应不递归重试。
- 文档：新增 `docs/stages/M331/structured-output-conformance.md`，只记录脱敏场景、决策、reason code 和恢复边界。
- 兼容修复：ReAct 只向模型暴露当前可信 tool catalog 中存在契约的工具，保留动态审批工具的实时发现能力；避免未提供契约的注册名进入上下文。
- 验证：Docker 新增 M331-A 契约与 M320/答案/M330 相邻回归 `40/40` 通过；未保存模型原文、Prompt、密钥或网页正文。
- 下一步：M331-B 验证直接回答、单域、多域和混合任务的目录驱动组合及 Result/Evidence 闭合。

### M331-B：通用任务组合与结果闭合 — 进行中

- 开始：已切换热状态和阶段交接；必要文件限定为通用 Host/Runtime、ReAct 执行、ToolRegistry、Result Registry 及直接测试。
- 当前动作：检查能力选择、操作到结果类型推导、依赖/权限/预算/preflight、部分成功和多结果汇总是否共用公共 seam。
- 下一步：补充不依赖关键词的组合场景矩阵，先用 Docker 定向回归区分契约缺口和已有能力。

### M331-B：通用任务组合与结果闭合 — 已完成

- 文档/测试：新增 `docs/stages/M331/task-composition-matrix.md` 和 `tests/test_m331_task_composition.py`，覆盖目录 owner、操作结果类型、
  通用直接问题和部分成功。
- 修复：`GeneralAnswerComposer` 在有可用结果但存在失败步骤时明确报告“部分结果”和未完成项，不把请求说成全部完成。
- 验证：Docker M331-A/B 与 M320、答案、Host、通用入口回归 `50/50` 通过；未新增关键词路由或领域 Runtime 分支。
- 下一步：M331-C 检查多轮/长任务上下文裁剪、预算、取消、重试、澄清/审批续跑和 SQLite/Artifact/SSE 恢复。

### M331-C：上下文、长任务与恢复可用率 — 进行中

- 开始：已将热状态和阶段交接切换到 M331-C；只读取上下文工程、状态存储、Artifact、RunEvent、异步运行和直接测试。
- 当前动作：确认安全历史投影、上下文预算、事件分页/Last-Event-ID、重启接管和同一 Run/session identity 的现有行为。
- 下一步：补充最小恢复对照测试，只有发现可复现契约缺口时才修改公共恢复 seam。

### M331-C：上下文、长任务与恢复可用率 — 已完成

- 修复：上下文预算超限时先压缩版本化 workflow template 摘要，保留 schema、能力边界和步骤形状，再按预算继续裁剪；避免整段目录被替换为缺少版本字段的 `omitted` 对象。
- 验证：Docker 恢复紧凑回归 `24/24` 通过，覆盖上下文脱敏、SQLite/Artifact、RunEvent/SSE、工具审批恢复和同一 Run identity。

### M331-D：答案质量与实时体验 — 已完成

- 实现：新增领域无关 `agent/answer_quality.py`，对最终答案做空值、长度、内部标记、乱码和非终态状态披露检查；receipt 通过 `answer_generation` evidence 进入共享结果契约，Runtime fallback、普通答案和 Composite 答案均覆盖。
- 实现：补齐 Python/Console ReAct 事件契约可见性，修复答案流与 `answer_length` 的 1800 字符封顶，使前端逐字输出上限与答案契约统一为 6000 字符。
- 验证：Docker M331 结构化输出/任务组合/答案体验/上下文/答案流/事件/生成回归 `42/42`，Console answer/event/projection smoke、compileall、architecture strict、服务 smoke 全部通过。
- 真实模型：通用直答 `COMPLETED`、`live_model`、`streaming=True`、质量 `pass`；复杂 GIS 多步请求在临时 45 秒有界预算中未返回，记录为 provider 规划延迟，未保存模型原文。

### M331-E/F：阶段验收与交付 — 已完成并推送（`11d7492`）

- 完成：更新热状态、M331 Plan/handoff、任务账本、开发问题记录和代码/文档索引；全局重规划输入已写入 M331 Plan/handoff。
- 下一步：后续优先处理真实模型复杂规划的可控超时/增量反馈，并保持通用能力边界不退化。

### M332-0：阶段初始化与契约落地 — 进行中

- 开始：已将热状态、恢复入口和必要文件切换到 M332；本阶段按单 Agent、Docker 优先和最小充分验证执行。
- 文档：已建立 M332 capability map、Spec、Plan、handoff，明确 RunBudget、阶段心跳、Provider deadline、超时恢复、终态隔离和实时投影的依赖顺序。
- 当前动作：实现统一 `RunBudget` 与阶段进度协调器；不保存模型原文、Prompt、隐藏思维链或敏感配置。
- 下一步：完成 M332-0 文档索引更新后进入 M332-A。

### M332-0：阶段初始化与契约落地 — 已完成

- 交付：建立 M332 capability map、Spec、Plan、handoff，切换热状态和文档索引到 M332。
- 验证：`scripts/validate_document_index.ps1` 通过；未修改 Runtime、Provider 或前端代码。
- 下一步：M332-A 实现统一 RunBudget 深模块。

### M332-A：统一 RunBudget — 进行中

- 开始：已切换热状态到 M332-A；当前只读取 Runtime 控制、Provider deadline 和现有 timeout 配置相关接口。
- 当前动作：实现总预算、阶段预算、单次调用预算、剩余时间和脱敏 receipt；保持现有 `timeout_seconds` 兼容。
- 下一步：完成预算契约后运行单组紧凑契约测试，再接入阶段进度协调器。

### M332-A：统一 RunBudget — 已完成

- 实现：新增 `agent/runtime_core/run_budget.py` 和 `spatial-agent.run-budget.v1` 安全 receipt；支持总预算、阶段预算、provider 单次预算、尝试/重试和剩余时间。
- 集成：从 `agent/runtime_core/__init__.py` 导出公共 Runtime 深模块符号，未改变既有 Provider、ToolRegistry 或 Domain 行为。
- 验证：Docker `tests.test_m332_realtime_budget` 通过 `4/4`；首次因旧镜像缺少新测试文件，重建 `docker-compose.prod.yml` 服务后通过。
- 下一步：M332-B 实现阶段进度协调器和真实 heartbeat。

### M332-B：阶段进度协调器 — 进行中

- 开始：已切换热状态到 M332-B；当前只读取 `RunBudget` 和 RunEvent 安全字段相关接口。
- 当前动作：实现可注入 event sink 的阶段协调器，确保 heartbeat 在线程阻塞期间产生且关闭时不泄漏。
- 下一步：补充最小心跳/阶段顺序契约测试，再接入 Provider 和 Runtime。

### M332-B：阶段进度协调器 — 已完成

- 实现：新增 `agent/runtime_core/progress.py`，集中管理阶段开始、尝试、heartbeat、恢复和关闭；`run_events.py` 补齐超时/取消/重试/恢复事件及安全计时字段。
- 验证：Docker 预算与进度合并测试 `6/6` 通过；后台 heartbeat 可关闭且不继续写入事件。
- 下一步：M332-C 将阶段剩余时间传入 Provider、Planner、ReAct 和答案流。

### M332-C：Provider、Planner、ReAct 与答案流预算接入 — 进行中

- 开始：已切换热状态到 M332-C；当前只读取结构化调用、OpenAI-compatible client、Planner、ReAct 和答案生成接口。
- 当前动作：增加有界 timeout、剩余 deadline 和安全进度回调；结构化响应仍必须完整校验后才能进入 Runtime。
- 下一步：先完成 provider adapter 和 fake-client 紧凑测试，再接入 Runtime 生命周期。

### M332-C：Provider、Planner、ReAct 与答案流预算接入 — 已完成

- 实现：`structured_response` 支持调用级 `timeout_seconds`、单调 `deadline`、动态 `timeout_provider` 和脱敏 `on_progress`；结构化恢复沿用同一安全边界。
- 实现：`LLMPlanner` 的规划/ReAct/compact recovery、普通答案和 Composite 答案均可接收 `RunBudget` 与安全进度协调器；结构化结果继续在完整校验后才可进入 Runtime。
- 实现：`OpenAIPlannerClient` 的 Responses/Chat Completions 结构化请求与文本流均以调用级 deadline 限制 socket timeout、重试和退避；流式答案在增量边界检查阶段预算。
- 验证：M331 结构化响应 + M332 预算/进度/Provider 紧凑测试 `17/17` 通过；只使用 fake client，未保存模型原文、Prompt、密钥或网页正文。
- 下一步：M332-D 把 `RunBudget` 与 `ProgressCoordinator` 接入 `run_lifecycle.py`、`runtime.py`，统一超时和恢复终态。

### M332-D：Runtime 超时与恢复接入 — 已完成

- 实现：把规划、执行、答案和总 Run 的剩余预算接入统一生命周期；超时、失败、部分结果和恢复 lineage 均保留结构化证据。
- 修复：处理 M37 极短超时、M60 自定义 factory 的 `event_sink` 兼容和 M69 异步超时类型丢失。
- 验证：Runtime lifecycle、RunBudget、Progress、Provider、M37、M60、M69、M79 定向回归通过。

### M332-E：异步与持久化终态隔离 — 已完成

- 实现：reaper、SQLite、内存和 Artifact 共享终态 fence；迟到 worker 不能覆盖超时/取消/完成状态，事件序号竞争已修复。
- 验证：新增终态事件 fence 回归；M332-D/E 定向 Docker 回归 `30/30` 通过，未调用真实模型。

### M332-F：SSE/前端与阶段验收 — 已完成

- 实现：SSE、轮询和前端消费 heartbeat、预算、重试、恢复与超时字段；规划等待、答案流、事件和结果投影保持结构化展示。
- 修复：ReAct 后续 Planner 超时不再覆盖先前成功的 `planner_metrics`；新增紧凑回归，公开 `model_evidence` 仍能证明真实模型成功参与。
- 修复：规划等待 smoke 显式注入独立抽取函数所需的预算格式化依赖，避免测试夹具误报前端闭包缺失。
- 验证：Docker M332 定向回归 `15/15`、compileall、architecture strict、服务 smoke、readiness `200`、Console 规划等待/答案流/事件/结果投影 smoke 通过。
- 真实验收：使用生产 Compose `--env-file .env.production` 正确挂载 `D:/dataset/agent`，显式 GIS + 真实模型复杂请求 `COMPLETED`；异步、轮询、Artifact、SSE 断点续传和 evidence 对照通过。仅记录脱敏状态/计数。

### M332 阶段收口与全局重规划输入

- 交付：M332 的实时执行体验、预算、恢复、终态一致性和真实 GIS 链路已闭合；下一阶段从产品体验、Runtime、Planner、Domain/数据、部署和测试全局规划。
- 约束：默认测试继续离线、精简、按风险分层；真实模型/GIS 只作为显式验收；不保存模型原文、Prompt、网页正文、工具源码或密钥。
