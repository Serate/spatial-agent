# `agent/` 全量模块职责地图

> 本文件由 `scripts/build_agent_module_map.py` 根据 `docs/code-index.json` 生成。
> 它是当前职责盘点，不是物理迁移方案；下一阶段再根据整体依赖和 seam 评估目录调整。
> 文档不复制源码正文，只保留职责、语义层、稳定性、阶段和验证入口。

## 使用边界

- `职责` 是恢复上下文和代码导航的第一入口；`层` 是当前语义分类，不等于立即迁移目标。
- `来源` 为 `file-override` 时，职责由精确文件规则维护；为 `path-rule` 时，职责继承目录/文件族规则。
- `导出符号数` 和 `验证入口` 用于快速定位深模块接口与最小验证面，详细符号仍在 `docs/code-index.json`。
- 新增或重命名 `agent/` 源码后，必须重新生成本报告并通过索引校验。

## 总览

| 指标 | 数值 |
| --- | ---: |
| `agent/` 源码文件 | 211 |
| 全仓源码文件 | 343 |
| 职责覆盖 | 211/211 |
| 语义覆盖率 | 100.0% |

### 语义层分布

| 层 | 文件数 |
| --- | ---: |
| `adapter` | 3 |
| `analysis` | 5 |
| `application` | 36 |
| `data` | 2 |
| `domain` | 11 |
| `evidence` | 18 |
| `frontend` | 1 |
| `integration` | 14 |
| `observability` | 2 |
| `persistence` | 15 |
| `planner` | 31 |
| `result` | 8 |
| `runtime` | 53 |
| `tooling` | 9 |
| `verification` | 3 |

### 当前物理目录分布

| 当前目录 | 文件数 | 主要语义层 |
| --- | ---: | --- |
| `agent/（根目录公共入口与契约）` | 114 | adapter (3), application (11), data (2), domain (11), evidence (7), frontend (1), integration (4), observability (2), persistence (7), planner (28), result (8), runtime (25), tooling (2), verification (3) |
| `agent/analysis/` | 5 | analysis (5) |
| `agent/application/` | 25 | application (25) |
| `agent/evidence/` | 11 | evidence (11) |
| `agent/integration/` | 6 | integration (6) |
| `agent/network/` | 4 | integration (4) |
| `agent/persistence/` | 8 | persistence (8) |
| `agent/react/` | 3 | planner (3) |
| `agent/runtime_core/` | 28 | runtime (28) |
| `agent/tooling/` | 7 | tooling (7) |

## 文件职责清单

### `agent/（根目录公共入口与契约）`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/__init__.py` | `runtime` | Core modules for the spatial Agent Runtime. | `public-boundary` | `M1-M325` | `path-rule` | 0 | — |
| `agent/action_contract.py` | `runtime` | Bounded input validation for Domain-owned actions. | `public-boundary` | `M127-M325` | `path-rule` | 2 | — |
| `agent/action_effect.py` | `runtime` | Domain-neutral effect projection for one lifecycle action. | `public-boundary` | `M127-M325` | `path-rule` | 2 | — |
| `agent/action_identity.py` | `runtime` | Domain-neutral identity linkage for Action Receipt evidence. | `public-boundary` | `M127-M325` | `path-rule` | 5 | — |
| `agent/action_lifecycle.py` | `runtime` | Domain-neutral projection for the externally visible run lifecycle. | `public-boundary` | `M127-M325` | `path-rule` | 1 | — |
| `agent/action_lineage.py` | `runtime` | Bounded, domain-neutral lineage for consecutive lifecycle actions. | `public-boundary` | `M127-M325` | `path-rule` | 3 | — |
| `agent/action_precondition.py` | `runtime` | Domain-neutral, bounded preconditions for lifecycle actions. | `public-boundary` | `M127-M325` | `path-rule` | 3 | — |
| `agent/agent_settings.py` | `runtime` | Product-facing defaults for the open Agent execution modes. | `public-boundary` | `M1-M325` | `path-rule` | 1 | — |
| `agent/analysis_intent.py` | `planner` | Domain-neutral, bounded analysis intent contract. | `public-boundary` | `M311-M325` | `path-rule` | 2 | — |
| `agent/analysis_ready_binding.py` | `adapter` | Compatibility facade for the canonical GIS analysis-ready binding. | `public-boundary` | `M69-M325` | `file-override` | 0 | — |
| `agent/answer_composer.py` | `result` | Backward-compatible import for the GIS Domain Pack answer composer. | `public-boundary` | `M8-M325` | `path-rule` | 0 | — |
| `agent/answer_generation.py` | `result` | Controlled natural-language answer generation for completed runs. | `public-boundary` | `M8-M334` | `file-override` | 14 | `tests/test_answer_generation.py`<br>`tests/test_m334_evidence_quality.py` |
| `agent/answer_quality.py` | `result` | Small, domain-neutral checks for user-visible answer quality. | `public-boundary` | `M8-M325` | `path-rule` | 2 | — |
| `agent/api_contract.py` | `application` | Shared HTTP request/response contract for the dev (stdlib) and production (FastAPI) entry points. | `public-boundary` | `M10-M325` | `path-rule` | 16 | — |
| `agent/artifact_access.py` | `persistence` | Compatibility facade for canonical persistence artifact access. | `public-boundary` | `M14-M325` | `path-rule` | 0 | — |
| `agent/artifact_manifest.py` | `persistence` | Compatibility facade for canonical persistence artifact manifests. | `public-boundary` | `M14-M325` | `path-rule` | 0 | — |
| `agent/artifact_reference.py` | `persistence` | Compatibility facade for canonical persistence artifact references. | `public-boundary` | `M14-M325` | `path-rule` | 0 | — |
| `agent/artifact_store.py` | `persistence` | Compatibility facade for canonical persistence artifact storage. | `public-boundary` | `M14-M325` | `path-rule` | 0 | — |
| `agent/artifact_viewer.py` | `persistence` | Compatibility facade for canonical persistence artifact viewing. | `public-boundary` | `M14-M325` | `path-rule` | 0 | — |
| `agent/capability_catalog.py` | `planner` | The shared, safe capability contract for planners, APIs, and the Console. | `public-boundary` | `M59-M325` | `path-rule` | 5 | — |
| `agent/capability_descriptor.py` | `planner` | Bounded, domain-neutral descriptors for capability discovery. | `public-boundary` | `M59-M325` | `path-rule` | 3 | — |
| `agent/capability_discovery.py` | `planner` | Domain-neutral capability discovery value objects. | `public-boundary` | `M59-M325` | `path-rule` | 9 | — |
| `agent/capability_routing.py` | `planner` | Compatibility facade for the former GIS capability router. | `public-boundary` | `M59-M325` | `path-rule` | 7 | — |
| `agent/capability_selection.py` | `planner` | Bounded capability-selection evidence for Planner and public results. | `public-boundary` | `M59-M325` | `path-rule` | 2 | — |
| `agent/component_evidence.py` | `evidence` | Compatibility facade for canonical component evidence. | `public-boundary` | `M293-M325` | `path-rule` | 0 | — |
| `agent/context_engineering.py` | `planner` | Bounded, auditable context construction for planner calls. | `public-boundary` | `M77-M325` | `path-rule` | 3 | — |
| `agent/contract_versions.py` | `runtime` | Version identifiers for the domain-neutral planning/result contracts. | `public-boundary` | `M1-M325` | `path-rule` | 0 | — |
| `agent/conversation_turn.py` | `application` | Domain-neutral conversation turn identity and continuation policy. | `public-boundary` | `M217-M325` | `path-rule` | 3 | — |
| `agent/cost_governance.py` | `runtime` | Cost governance and concurrency quota (M81.1). | `public-boundary` | `M81-M325` | `path-rule` | 18 | — |
| `agent/data_kinds.py` | `data` | Domain-neutral result data-shape profiles. | `public-boundary` | `M51-M325` | `path-rule` | 4 | — |
| `agent/data_readiness.py` | `data` | Bounded, domain-neutral data readiness projections. | `public-boundary` | `M51-M325` | `path-rule` | 1 | — |
| `agent/decision_lifecycle.py` | `application` | Domain-neutral decision lifecycle contract for controlled Agent runs. | `public-boundary` | `M151-M325` | `path-rule` | 27 | — |
| `agent/deployment_evidence.py` | `verification` | Domain-neutral deployment evidence projection. | `public-boundary` | `M136-M325` | `path-rule` | 1 | — |
| `agent/domain_catalog.py` | `domain` | Domain-neutral validation and construction for declarative Domain catalogs. | `public-boundary` | `M112-M325` | `path-rule` | 4 | — |
| `agent/domain_contract.py` | `domain` | Contracts for domain packs consumed by the generic Agent Runtime. | `public-boundary` | `M112-M325` | `path-rule` | 57 | — |
| `agent/domain_http.py` | `domain` | Shared HTTP adapter helpers for explicit Domain-prefixed routes. | `public-boundary` | `M112-M325` | `path-rule` | 3 | — |
| `agent/domain_registry.py` | `domain` | Controlled Domain Pack registry for deployment and entry-point selection. | `public-boundary` | `M112-M325` | `path-rule` | 10 | — |
| `agent/domain_routing_entry.py` | `domain` | Shared application seam for automatic Domain routing entry points. | `public-boundary` | `M112-M325` | `path-rule` | 23 | — |
| `agent/domain_routing_evidence.py` | `domain` | Bounded execution evidence derived from Domain routing decisions. | `public-boundary` | `M112-M325` | `path-rule` | 6 | — |
| `agent/domain_runtime_host.py` | `domain` | Multi-Domain application host for isolated :class:`AgentService` instances. | `public-boundary` | `M112-M325` | `path-rule` | 7 | — |
| `agent/domain_selection.py` | `domain` | Versioned, transport-neutral selection of one registered Domain Pack. | `public-boundary` | `M112-M325` | `path-rule` | 3 | — |
| `agent/domain_selector.py` | `domain` | Versioned, bounded selection of a Domain before planning begins. | `public-boundary` | `M112-M325` | `path-rule` | 24 | — |
| `agent/domain_selector_provider.py` | `domain` | Controlled provider selection for automatic Domain routing. | `public-boundary` | `M112-M325` | `path-rule` | 14 | — |
| `agent/environment_status.py` | `verification` | 运行环境与依赖状态探测 | `public-boundary` | `M22-M325` | `path-rule` | 1 | — |
| `agent/errors.py` | `runtime` | Runtime 稳定错误类型与错误码 | `public-boundary` | `M1-M325` | `path-rule` | 7 | — |
| `agent/evidence_contract.py` | `evidence` | Compatibility facade for the canonical evidence contract. | `public-boundary` | `M71-M325` | `path-rule` | 0 | — |
| `agent/evidence_projection.py` | `evidence` | Compatibility facade for the canonical evidence projection. | `public-boundary` | `M71-M325` | `path-rule` | 0 | — |
| `agent/evidence_recovery.py` | `evidence` | Compatibility facade for the canonical evidence recovery seam. | `public-boundary` | `M71-M325` | `path-rule` | 0 | — |
| `agent/evidence_registry.py` | `evidence` | Compatibility facade for the canonical evidence registry. | `public-boundary` | `M71-M325` | `path-rule` | 0 | — |
| `agent/evidence_revalidation.py` | `evidence` | Compatibility facade for canonical evidence revalidation. | `public-boundary` | `M71-M325` | `path-rule` | 0 | — |
| `agent/execution_contract.py` | `runtime` | Domain-neutral execution identity and observability projection. | `public-boundary` | `M128-M325` | `path-rule` | 2 | — |
| `agent/execution_timeline.py` | `runtime` | Domain-neutral, bounded execution timeline evidence. | `public-boundary` | `M128-M325` | `path-rule` | 3 | — |
| `agent/failure_contract.py` | `runtime` | Stable, credential-free run-level failure evidence. | `public-boundary` | `M33-M325` | `path-rule` | 2 | — |
| `agent/general_capability_host.py` | `runtime` | Domain-neutral capability and provider aggregation. | `internal` | `M1-M325` | `path-rule` | 19 | — |
| `agent/general_runtime.py` | `runtime` | Domain-neutral Runtime adapter backed by :mod:`general_capability_host`. | `internal` | `M1-M325` | `path-rule` | 38 | — |
| `agent/geojson_exporter.py` | `result` | 空间结果 GeoJSON 有界导出 | `public-boundary` | `M18-M325` | `path-rule` | 2 | — |
| `agent/interaction_contract.py` | `application` | Versioned, domain-neutral contract for all user/runtime interactions. | `public-boundary` | `M164-M325` | `path-rule` | 11 | — |
| `agent/interaction_host.py` | `application` | Stateful host for authoritative interaction inspection and invocation. | `public-boundary` | `M164-M325` | `path-rule` | 3 | — |
| `agent/llm_planner.py` | `planner` | 真实模型结构化规划与 ReAct 决策适配 | `public-boundary` | `M286-M325` | `file-override` | 13 | `tests/test_m320_react_runtime.py` |
| `agent/memory.py` | `persistence` | Compatibility facade for canonical persistence fact memory. | `public-boundary` | `M80-M325` | `path-rule` | 0 | — |
| `agent/model_evidence.py` | `integration` | Compatibility facade for the canonical model evidence projector. | `public-boundary` | `M61-M325` | `path-rule` | 0 | — |
| `agent/models.py` | `runtime` | 运行请求、计划、步骤和结果数据模型 | `public-boundary` | `M1-M325` | `path-rule` | 6 | — |
| `agent/nested_schema.py` | `result` | One migration and validation seam for nested result contracts. | `public-boundary` | `M149-M325` | `path-rule` | 9 | — |
| `agent/observability.py` | `observability` | Structured observability with OpenTelemetry-style span tracing (M80.3). | `public-boundary` | `M80-M325` | `path-rule` | 9 | — |
| `agent/openai_config.py` | `integration` | Compatibility facade for the canonical provider integration config. | `public-boundary` | `M16-M325` | `path-rule` | 0 | — |
| `agent/operation_binding.py` | `planner` | Domain-neutral binding between analysis operations and result profiles. | `public-boundary` | `M247-M325` | `path-rule` | 1 | — |
| `agent/plan_identity.py` | `planner` | Stable identity for comparing a planned TaskPlan with a later execution. | `public-boundary` | `M141-M325` | `path-rule` | 2 | — |
| `agent/plan_policy.py` | `planner` | Versioned evidence for the policy that accepted or rejected a TaskPlan. | `public-boundary` | `M141-M325` | `path-rule` | 3 | — |
| `agent/plan_quality.py` | `planner` | Bounded workflow-aware TaskPlan quality diagnostics. | `public-boundary` | `M141-M325` | `path-rule` | 3 | — |
| `agent/plan_repair.py` | `planner` | Capability-guided planning repair behind one small Runtime seam. | `public-boundary` | `M141-M325` | `path-rule` | 7 | — |
| `agent/plan_schema.py` | `planner` | 计划 schema、质量、策略、身份与修复 | `public-boundary` | `M141-M325` | `path-rule` | 2 | — |
| `agent/planner.py` | `planner` | Planner protocol and bounded compatibility facade. | `public-boundary` | `M2-M325` | `path-rule` | 5 | — |
| `agent/planner_context.py` | `planner` | Planner-only projections of the richer runtime context contracts. | `public-boundary` | `M129-M325` | `path-rule` | 1 | — |
| `agent/planner_guidance.py` | `planner` | Shared contract and rendering helpers for Domain-owned planner policy. | `public-boundary` | `M129-M325` | `path-rule` | 3 | — |
| `agent/planner_repair.py` | `planner` | Bounded, provider-neutral Planner repair contracts. | `public-boundary` | `M129-M325` | `path-rule` | 5 | — |
| `agent/planner_selection.py` | `planner` | Domain-neutral evidence for Planner capability alignment. | `public-boundary` | `M129-M325` | `path-rule` | 2 | — |
| `agent/provenance.py` | `evidence` | 结果来源与数据血缘构建 | `public-boundary` | `M35-M325` | `path-rule` | 1 | — |
| `agent/provider_runtime.py` | `integration` | Compatibility facade for the canonical provider runtime evidence seam. | `public-boundary` | `M93-M325` | `path-rule` | 0 | — |
| `agent/provider_structured_output.py` | `integration` | Compatibility facade for the canonical structured-output provider seam. | `public-boundary` | `M93-M325` | `path-rule` | 0 | — |
| `agent/recovery_action.py` | `runtime` | Domain-neutral action and receipt projection seam. | `public-boundary` | `M181-M325` | `path-rule` | 7 | — |
| `agent/release_evidence.py` | `adapter` | Compatibility facade for the canonical GIS release evidence adapter. | `public-boundary` | `M76-M325` | `file-override` | 0 | — |
| `agent/replanning.py` | `planner` | Adaptive replanning during execution. | `public-boundary` | `M80-M325` | `path-rule` | 10 | — |
| `agent/request_identity.py` | `planner` | Build a stable, transport-neutral identity for a user request. | `public-boundary` | `M77-M325` | `path-rule` | 2 | — |
| `agent/request_mode.py` | `planner` | Versioned, domain-neutral classification of one completed request. | `public-boundary` | `M77-M325` | `path-rule` | 2 | — |
| `agent/request_model.py` | `planner` | Domain-neutral RequestFacts value object and legacy GIS parser facade. | `public-boundary` | `M77-M325` | `path-rule` | 5 | — |
| `agent/request_requirements.py` | `planner` | Domain-neutral request-fact requirements and satisfaction semantics. | `public-boundary` | `M77-M325` | `path-rule` | 6 | — |
| `agent/request_understanding.py` | `planner` | Generic, bounded guidance for domain-owned request understanding. | `public-boundary` | `M77-M325` | `path-rule` | 2 | — |
| `agent/result_completeness.py` | `result` | Domain-neutral completion projection for run results. | `public-boundary` | `M46-M325` | `path-rule` | 2 | — |
| `agent/result_registry.py` | `result` | Domain-neutral result type metadata registry. | `public-boundary` | `M46-M325` | `path-rule` | 16 | — |
| `agent/result_summary.py` | `result` | Domain-neutral, bounded summary projection for typed results. | `public-boundary` | `M46-M334` | `file-override` | 3 | `tests/test_m334_evidence_quality.py` |
| `agent/rule_planning.py` | `planner` | Compatibility facade for the former GIS plan composer. | `internal` | `M7-M325` | `path-rule` | 3 | — |
| `agent/run_events.py` | `runtime` | Versioned, bounded lifecycle events for realtime Agent consumers. | `public-boundary` | `M13-M325` | `path-rule` | 6 | — |
| `agent/runtime.py` | `runtime` | AgentRuntime 门面与生命周期入口 | `public-boundary` | `M318-M325` | `file-override` | 25 | `tests/test_m320_react_runtime.py` |
| `agent/runtime_capabilities.py` | `adapter` | Compatibility facade for the canonical GIS runtime capability adapter. | `public-boundary` | `M59-M325` | `file-override` | 0 | — |
| `agent/runtime_context.py` | `runtime` | Versioned, bounded configuration evidence for one Agent Runtime run. | `public-boundary` | `M1-M325` | `path-rule` | 5 | — |
| `agent/runtime_defaults.py` | `runtime` | Product-facing defaults for the Agent Runtime. | `public-boundary` | `M1-M325` | `path-rule` | 3 | — |
| `agent/runtime_factory.py` | `runtime` | Runtime factory shared by the CLI, HTTP services, evaluation, and tests. | `public-boundary` | `M1-M325` | `path-rule` | 4 | — |
| `agent/runtime_state.py` | `runtime` | In-memory runtime state adapters. | `public-boundary` | `M1-M325` | `path-rule` | 17 | — |
| `agent/scenario.py` | `verification` | Validated, transport-friendly spatial comparison scenarios. | `internal` | `M57-M325` | `path-rule` | 7 | — |
| `agent/selection_interaction.py` | `application` | Domain-neutral interaction projection for workflow selection. | `public-boundary` | `M164-M325` | `path-rule` | 2 | — |
| `agent/service.py` | `application` | AgentService 兼容门面与资源生命周期 | `public-boundary` | `M78-M325` | `path-rule` | 47 | — |
| `agent/service_async.py` | `application` | Compatibility facade for the canonical Application async helpers. | `public-boundary` | `M68-M325` | `file-override` | 0 | — |
| `agent/service_format.py` | `application` | Compatibility facade for the canonical Application formatting helpers. | `public-boundary` | `M68-M325` | `file-override` | 0 | — |
| `agent/service_sessions.py` | `application` | Compatibility facade for the canonical Application session helpers. | `public-boundary` | `M68-M325` | `file-override` | 0 | — |
| `agent/service_state.py` | `application` | Compatibility facade for the canonical Application service state. | `public-boundary` | `M78-M325` | `file-override` | 0 | — |
| `agent/spatial_intent.py` | `domain` | Legacy compatibility facade for the GIS intent policy. | `internal` | `M3-M325` | `path-rule` | 3 | — |
| `agent/sqlite_store.py` | `persistence` | Compatibility facade for canonical persistence SQLite stores. | `public-boundary` | `M313-M325` | `file-override` | 0 | `tests/test_m42_sqlite_store.py`<br>`tests/test_m320_react_runtime.py` |
| `agent/tool_provider.py` | `tooling` | Pluggable sources of tool definitions and implementations. | `public-boundary` | `M92-M325` | `path-rule` | 22 | — |
| `agent/tools.py` | `tooling` | ToolRegistry schema 校验与 dispatch | `public-boundary` | `M81-M325` | `file-override` | 24 | `tests/test_m320_react_runtime.py`<br>`tests/test_m322_tool_proposal.py` |
| `agent/trace_formatter.py` | `observability` | 执行轨迹格式化与可读投影 | `public-boundary` | `M13-M325` | `path-rule` | 1 | — |
| `agent/transition_evidence.py` | `runtime` | Bounded data-evidence transition projection for recovery actions. | `public-boundary` | `M182-M325` | `path-rule` | 3 | — |
| `agent/web_assets.py` | `frontend` | Canonical static asset seam for the Console HTTP adapters. | `public-boundary` | `M258-M325` | `path-rule` | 3 | — |
| `agent/workflow_selection.py` | `planner` | Domain-neutral evidence for capability-to-workflow selection. | `public-boundary` | `M44-M325` | `path-rule` | 3 | — |
| `agent/workflow_templates.py` | `planner` | Controlled, JSON-safe workflow template contracts. | `public-boundary` | `M44-M325` | `path-rule` | 16 | — |

### `agent/analysis/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/analysis/__init__.py` | `analysis` | Domain-neutral analytical engines used by Domain Pack adapters. | `public-boundary` | `M243-M325` | `path-rule` | 0 | — |
| `agent/analysis/indicator_core.py` | `analysis` | Reusable analysis engine for normalized numeric observations. | `public-boundary` | `M243-M325` | `path-rule` | 5 | — |
| `agent/analysis/record_analysis.py` | `analysis` | Deep, domain-neutral analysis of bounded mapping records. | `public-boundary` | `M243-M325` | `path-rule` | 2 | — |
| `agent/analysis/record_contract.py` | `analysis` | Domain-neutral contract helpers for bounded record analysis. | `public-boundary` | `M243-M325` | `path-rule` | 2 | — |
| `agent/analysis/record_views.py` | `analysis` | Domain-neutral views for bounded record-analysis results. | `public-boundary` | `M243-M325` | `path-rule` | 1 | — |

### `agent/application/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/application/__init__.py` | `application` | Canonical application use-case seams. | `public-boundary` | `M254-M325` | `path-rule` | 0 | — |
| `agent/application/actions.py` | `application` | Canonical Domain action application use case. | `public-boundary` | `M254-M325` | `path-rule` | 7 | — |
| `agent/application/async_runs.py` | `application` | Canonical asynchronous run application use case. | `public-boundary` | `M254-M325` | `path-rule` | 10 | — |
| `agent/application/catalog.py` | `application` | Canonical runtime and Domain capability catalog application. | `public-boundary` | `M254-M325` | `path-rule` | 17 | — |
| `agent/application/comparisons.py` | `application` | Compatibility application for bounded comparison scenarios. | `public-boundary` | `M254-M325` | `path-rule` | 4 | — |
| `agent/application/composite.py` | `application` | Transport-neutral execution coordinator for bounded Composite requests. | `public-boundary` | `M254-M325` | `path-rule` | 3 | — |
| `agent/application/composite_contract.py` | `application` | Domain-neutral request/result/evidence seam for cross-Domain composition. | `public-boundary` | `M254-M334` | `file-override` | 5 | `tests/test_m334_evidence_quality.py` |
| `agent/application/composite_planner.py` | `application` | Domain-neutral Rule/LLM planner contract for Composite requests. | `public-boundary` | `M254-M325` | `path-rule` | 11 | — |
| `agent/application/composite_planning.py` | `application` | Bounded Planner-facing projection for cross-Domain Composite requests. | `public-boundary` | `M254-M325` | `path-rule` | 5 | — |
| `agent/application/composite_request_context.py` | `application` | Bounded, domain-neutral context for open Composite requests. | `public-boundary` | `M254-M325` | `path-rule` | 3 | — |
| `agent/application/composite_runs.py` | `application` | Durable Composite run application built on the shared async lifecycle. | `public-boundary` | `M254-M325` | `path-rule` | 11 | — |
| `agent/application/composite_view.py` | `application` | Domain-neutral user projection for a canonical Composite Result. | `public-boundary` | `M254-M334` | `file-override` | 2 | `tests/test_m334_evidence_quality.py` |
| `agent/application/decisions.py` | `application` | Canonical decision application use case. | `public-boundary` | `M254-M325` | `path-rule` | 3 | — |
| `agent/application/http.py` | `application` | Domain-neutral HTTP application dispatcher. | `public-boundary` | `M307-M325` | `file-override` | 3 | `tests/test_m313_realtime_events.py` |
| `agent/application/http_transport.py` | `application` | Framework-neutral HTTP transport helpers. | `public-boundary` | `M254-M325` | `path-rule` | 8 | — |
| `agent/application/inspection.py` | `application` | Canonical bounded service inspection application. | `public-boundary` | `M254-M325` | `path-rule` | 3 | — |
| `agent/application/interactions.py` | `application` | Canonical run interaction application use case. | `public-boundary` | `M254-M325` | `path-rule` | 3 | — |
| `agent/application/run.py` | `application` | Canonical synchronous run application use case. | `public-boundary` | `M254-M325` | `path-rule` | 2 | — |
| `agent/application/run_recovery.py` | `application` | Canonical run query and recovery application. | `public-boundary` | `M254-M325` | `path-rule` | 8 | — |
| `agent/application/service_async.py` | `application` | Async job lifecycle helpers shared by the service facade and entry points. | `public-boundary` | `M68-M325` | `file-override` | 18 | `tests/test_m146_async_view_evidence.py`<br>`tests/test_m78_service_split.py` |
| `agent/application/service_format.py` | `application` | Result formatting, geometry evidence, and request normalization helpers. | `public-boundary` | `M68-M325` | `file-override` | 11 | `tests/test_m78_service_split.py`<br>`tests/test_m128_execution_contract.py` |
| `agent/application/service_sessions.py` | `application` | Session identity helpers shared by the service facade. | `public-boundary` | `M68-M325` | `file-override` | 6 | `tests/test_m78_service_split.py`<br>`tests/test_m79_reaper.py` |
| `agent/application/service_state.py` | `application` | Converged mutable state for AgentService. | `public-boundary` | `M78-M325` | `file-override` | 47 | `tests/test_m79_reaper.py` |
| `agent/application/sessions.py` | `application` | Session catalog and lifecycle application use case. | `public-boundary` | `M254-M325` | `path-rule` | 6 | — |
| `agent/application/submission.py` | `application` | Canonical run and preview submission application. | `public-boundary` | `M254-M325` | `path-rule` | 3 | — |

### `agent/evidence/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/evidence/__init__.py` | `evidence` | Canonical, domain-neutral evidence contracts and projections. | `public-boundary` | `M71-M325` | `path-rule` | 0 | — |
| `agent/evidence/bundle.py` | `evidence` | Bounded aggregation of heterogeneous evidence source records. | `public-boundary` | `M334` | `file-override` | 3 | `tests/test_m334_evidence_quality.py` |
| `agent/evidence/component.py` | `evidence` | Domain-neutral evidence projection for composed workflow components. | `public-boundary` | `M71-M325` | `path-rule` | 3 | — |
| `agent/evidence/composite.py` | `evidence` | Domain-neutral fact receipts and alignment metadata for Composite results. | `public-boundary` | `M334` | `file-override` | 4 | `tests/test_m334_evidence_quality.py` |
| `agent/evidence/contract.py` | `evidence` | Versioned, domain-neutral metadata for evidence projections. | `public-boundary` | `M71-M325` | `path-rule` | 6 | — |
| `agent/evidence/identity.py` | `evidence` | Stable, domain-neutral identity for bounded evidence sources. | `public-boundary` | `M334` | `file-override` | 9 | `tests/test_m334_evidence_quality.py` |
| `agent/evidence/projection.py` | `evidence` | Shared, bounded projection for result evidence and compatibility status. | `public-boundary` | `M71-M334` | `file-override` | 2 | `tests/test_m177_evidence_projection.py`<br>`tests/test_m334_evidence_quality.py` |
| `agent/evidence/quality.py` | `evidence` | Auditable freshness and completeness quality for evidence sources. | `public-boundary` | `M334` | `file-override` | 3 | `tests/test_m334_evidence_quality.py` |
| `agent/evidence/recovery.py` | `evidence` | Compatibility facade for the canonical evidence projection seam. | `public-boundary` | `M71-M325` | `path-rule` | 0 | — |
| `agent/evidence/registry.py` | `evidence` | Domain-neutral registry for public evidence projections. | `public-boundary` | `M71-M325` | `path-rule` | 3 | — |
| `agent/evidence/revalidation.py` | `evidence` | Bounded revalidation status derived from a transition evidence projection. | `public-boundary` | `M71-M325` | `path-rule` | 6 | — |

### `agent/integration/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/integration/__init__.py` | `integration` | Provider integration seams for configuration, model calls and safe evidence. | `public-boundary` | `M16-M325` | `path-rule` | 0 | — |
| `agent/integration/model_evidence.py` | `integration` | Bounded, transport-neutral evidence for replaceable planner models. | `public-boundary` | `M16-M325` | `path-rule` | 1 | — |
| `agent/integration/openai_config.py` | `integration` | Provider 配置、结构化输出与脱敏运行证据 canonical 实现 | `public-boundary` | `M16-M325` | `path-rule` | 2 | — |
| `agent/integration/provider_runtime.py` | `integration` | Bounded, provider-neutral health and deadline evidence. | `public-boundary` | `M16-M325` | `path-rule` | 6 | — |
| `agent/integration/provider_structured_output.py` | `integration` | Provider-neutral structured-output capability profile. | `public-boundary` | `M16-M325` | `path-rule` | 4 | — |
| `agent/integration/structured_response.py` | `integration` | Shared, bounded handling for provider structured responses. | `public-boundary` | `M16-M325` | `path-rule` | 5 | — |

### `agent/network/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/network/__init__.py` | `integration` | Network capabilities kept behind explicit, server-owned policy seams. | `public-boundary` | `M321-M334` | `path-rule` | 0 | — |
| `agent/network/web_fetch.py` | `integration` | Bounded HTML fetching behind the shared public-web policy. | `public-boundary` | `M321-M334` | `path-rule` | 7 | — |
| `agent/network/web_policy.py` | `integration` | Server-owned policy for bounded public web access. | `public-boundary` | `M321-M334` | `path-rule` | 10 | — |
| `agent/network/web_search.py` | `integration` | Bounded public-web search adapter. | `public-boundary` | `M321-M334` | `path-rule` | 8 | — |

### `agent/persistence/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/persistence/__init__.py` | `persistence` | Canonical persistence implementations for artifacts, SQLite and memory. | `public-boundary` | `M14-M325` | `path-rule` | 0 | — |
| `agent/persistence/artifact_access.py` | `persistence` | Bounded, domain-aware artifact file access for HTTP entry points. | `public-boundary` | `M14-M325` | `path-rule` | 1 | — |
| `agent/persistence/artifact_manifest.py` | `persistence` | Bounded, portable discovery metadata for persisted run artifacts. | `public-boundary` | `M14-M325` | `path-rule` | 3 | — |
| `agent/persistence/artifact_reference.py` | `persistence` | Portable, bounded references for persisted run and geometry artifacts. | `public-boundary` | `M14-M325` | `path-rule` | 2 | — |
| `agent/persistence/artifact_store.py` | `persistence` | Artifact、SQLite 与 Memory canonical 持久化实现 | `public-boundary` | `M14-M325` | `path-rule` | 14 | — |
| `agent/persistence/artifact_viewer.py` | `persistence` | Artifact、SQLite 与 Memory canonical 持久化实现 | `public-boundary` | `M14-M325` | `path-rule` | 1 | — |
| `agent/persistence/memory.py` | `persistence` | Cross-session fact memory (M80.2). | `public-boundary` | `M14-M325` | `path-rule` | 9 | — |
| `agent/persistence/sqlite_store.py` | `persistence` | SQLite-backed state and conversation stores for the production demo. | `public-boundary` | `M14-M325` | `path-rule` | 43 | — |

### `agent/react/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/react/__init__.py` | `planner` | Bounded, domain-neutral ReAct contracts and execution helpers. | `public-boundary` | `M320-M325` | `path-rule` | 0 | — |
| `agent/react/contracts.py` | `planner` | Versioned ReAct decision and evidence contracts. | `public-boundary` | `M320-M325` | `path-rule` | 8 | — |
| `agent/react/loop.py` | `planner` | Controlled, domain-neutral ReAct loop. | `public-boundary` | `M320` | `file-override` | 6 | `tests/test_m320_react_runtime.py`<br>`tests/test_m322_tool_proposal.py` |

### `agent/runtime_core/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/runtime_core/__init__.py` | `runtime` | Canonical, domain-neutral Runtime implementation seams. | `public-boundary` | `M253-M325` | `path-rule` | 0 | — |
| `agent/runtime_core/analysis_discovery.py` | `runtime` | Bounded discovery receipt for open, cross-domain analysis requests. | `public-boundary` | `M253-M325` | `path-rule` | 4 | — |
| `agent/runtime_core/capabilities.py` | `runtime` | Domain-neutral Runtime capability and deployment evidence surface. | `public-boundary` | `M253-M325` | `path-rule` | 10 | — |
| `agent/runtime_core/clarification_continuation.py` | `runtime` | Opaque, bounded continuation for component fact clarification. | `public-boundary` | `M253-M325` | `path-rule` | 6 | — |
| `agent/runtime_core/component_fact_handoff.py` | `runtime` | Bounded fact handoff between Composite Planner components and Domains. | `public-boundary` | `M253-M325` | `path-rule` | 7 | — |
| `agent/runtime_core/composite_taskplan.py` | `runtime` | Domain-neutral bridge from Composite candidates to canonical TaskPlans. | `public-boundary` | `M253-M325` | `path-rule` | 4 | — |
| `agent/runtime_core/composition.py` | `runtime` | Domain-neutral validation for bounded Composite input references. | `public-boundary` | `M253-M325` | `path-rule` | 5 | — |
| `agent/runtime_core/control.py` | `runtime` | Cooperative run cancellation and deadline control seam. | `public-boundary` | `M253-M325` | `path-rule` | 5 | — |
| `agent/runtime_core/decision_resume.py` | `runtime` | Decision-approved Runtime resume lifecycle. | `public-boundary` | `M253-M325` | `path-rule` | 2 | — |
| `agent/runtime_core/execution.py` | `runtime` | Tool execution seam for the domain-neutral Runtime. | `public-boundary` | `M253-M325` | `path-rule` | 3 | — |
| `agent/runtime_core/execution_binding.py` | `runtime` | Validated execution input for composed Domain runs. | `public-boundary` | `M253-M325` | `path-rule` | 7 | — |
| `agent/runtime_core/execution_policy.py` | `runtime` | Domain-neutral execution-policy contract. | `public-boundary` | `M253-M325` | `path-rule` | 11 | — |
| `agent/runtime_core/plan_completeness.py` | `runtime` | Domain-neutral completeness checks for Composite planning. | `public-boundary` | `M253-M325` | `path-rule` | 4 | — |
| `agent/runtime_core/plan_evidence.py` | `runtime` | Canonical plan evidence projection. | `public-boundary` | `M253-M325` | `path-rule` | 6 | — |
| `agent/runtime_core/plan_receipt.py` | `runtime` | Safe receipts for plans that have crossed the execution gate. | `public-boundary` | `M253-M325` | `path-rule` | 2 | — |
| `agent/runtime_core/planner_envelope.py` | `runtime` | Small, versioned context envelope sent to a Planner provider. | `public-boundary` | `M253-M325` | `path-rule` | 6 | — |
| `agent/runtime_core/planning.py` | `runtime` | Domain-neutral planning helpers behind the Runtime planning seam. | `public-boundary` | `M253-M325` | `path-rule` | 3 | — |
| `agent/runtime_core/planning_surface.py` | `runtime` | Runtime planning and replanning surface. | `public-boundary` | `M253-M325` | `path-rule` | 11 | — |
| `agent/runtime_core/preview.py` | `runtime` | Planning-only Runtime preview seam. | `public-boundary` | `M253-M325` | `path-rule` | 2 | — |
| `agent/runtime_core/progress.py` | `runtime` | Real-time progress coordination for one Runtime Run. | `public-boundary` | `M253-M325` | `path-rule` | 11 | — |
| `agent/runtime_core/projection.py` | `runtime` | Pure Runtime projections used by planning and lifecycle orchestration. | `public-boundary` | `M253-M334` | `file-override` | 16 | `tests/test_m326_result_completeness.py`<br>`tests/test_m334_evidence_quality.py` |
| `agent/runtime_core/react_runtime.py` | `runtime` | Runtime bridge for bounded, one-action-at-a-time ReAct execution. | `public-boundary` | `M320` | `file-override` | 2 | `tests/test_m320_react_runtime.py`<br>`tests/test_m322_tool_proposal.py` |
| `agent/runtime_core/recovery.py` | `runtime` | Runtime cancel and retry recovery seam. | `public-boundary` | `M253-M325` | `path-rule` | 3 | — |
| `agent/runtime_core/request_fact_readiness.py` | `runtime` | Bounded, domain-neutral readiness for Planner-facing request facts. | `public-boundary` | `M253-M325` | `path-rule` | 2 | — |
| `agent/runtime_core/run_budget.py` | `runtime` | Domain-neutral wall-clock budgets for one Agent Run. | `public-boundary` | `M253-M325` | `path-rule` | 20 | — |
| `agent/runtime_core/run_lifecycle.py` | `runtime` | Synchronous Runtime run lifecycle behind a small compatibility seam. | `public-boundary` | `M307` | `file-override` | 3 | `tests/test_m320_react_runtime.py` |
| `agent/runtime_core/selection_evidence.py` | `runtime` | Bounded evidence for capability selection and clarification outcomes. | `public-boundary` | `M253-M325` | `path-rule` | 2 | — |
| `agent/runtime_core/tool_approval_resume.py` | `runtime` | Approval-bound continuation for ReAct tool proposals. | `public-boundary` | `M253-M325` | `path-rule` | 2 | — |

### `agent/tooling/`

| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `agent/tooling/__init__.py` | `tooling` | Controlled Python tool proposal validation seams. | `public-boundary` | `M322-M325` | `path-rule` | 0 | — |
| `agent/tooling/approval.py` | `tooling` | Human approval contract for validated tool proposals. | `public-boundary` | `M322-M325` | `path-rule` | 24 | — |
| `agent/tooling/proposal.py` | `tooling` | Bounded contracts and local validation for generated Python tools. | `public-boundary` | `M322` | `file-override` | 8 | `tests/test_m322_tool_proposal.py` |
| `agent/tooling/rehydration.py` | `tooling` | Safe restart rehydration for approved dynamic tools. | `public-boundary` | `M322-M325` | `path-rule` | 1 | — |
| `agent/tooling/sandbox.py` | `tooling` | Bounded Unix-socket transport for the Python proposal sandbox. | `public-boundary` | `M322` | `file-override` | 4 | `tests/test_m322_tool_proposal.py` |
| `agent/tooling/sandbox_runner.py` | `tooling` | One-shot child process used inside the proposal sandbox sidecar. | `public-boundary` | `M322-M325` | `path-rule` | 1 | — |
| `agent/tooling/sandbox_worker.py` | `tooling` | Long-lived Unix socket worker for isolated Python tool proposal checks. | `internal` | `M322` | `file-override` | 2 | `tests/test_m322_tool_proposal.py` |

## 盘点结论

- 当前 `agent/` 已形成 Runtime、Application、Planner、Tooling、Domain、Persistence、Evidence、Result、Verification 和 Frontend 等职责簇。
- `agent/` 根目录仍同时承载公共契约、兼容 facade 和稳定入口；这不是单凭文件名就能安全迁移的同质目录。
- 下一阶段应结合导入图、公共稳定性、测试入口和实际 seam 决定是否迁移；仅有一个实现且调用方广泛的模块优先保持深模块与稳定入口。
- 本清单完成的是“文件职责可见化”，不宣称已经完成逐行架构审计或物理目录重构。
