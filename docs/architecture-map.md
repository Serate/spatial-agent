# Spatial Agent 架构地图

本文档描述当前活动路径、目标边界和重构期间必须保持的公共接口。它是代码结构重构的导航文档，不记录每个里程碑的历史细节。

## 当前活动路径

```text
CLI / serve_api.py / production_api.py / Console
                         │
                         ▼
                 HTTPApplication
                         │
                         ▼
                    AgentService
                         │
                         ▼
          Run / Session / Action / Decision / Interaction / Async
                    Applications
                         │
                         ▼
                    AgentRuntime
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   Runtime state   Runtime capability  Planner/Execution
      adapters          surface       ToolRegistry/Evidence
          │              │              │
          └──────────── DomainPack ─────┘
                         │
             GIS / Text / Indicators
```

当前实现已经通过 Domain Pack、ToolRegistry 和 Result Registry 形成逻辑分层，但以下物理边界仍待收敛：

- `agent/service.py` 仍包含目录、取消/重试和少量跨用例入口，并保留两个 Domain capability/facts 适配端口；Run、Session、Action、Decision、Interaction、Async 的主要应用用例已进入 `agent/application/`，Service 只保留兼容入口、线程池/资源生命周期和适配端口。
- Application Service 的异步、格式化、会话和状态实现已位于 `agent/application/service_*.py`；根目录同名文件只作兼容 facade，Application 包采用惰性导出避免低层模块触发用例循环导入。
- `agent/runtime.py` 的内存状态和能力目录职责已迁入 `agent/runtime_state.py` 与 `agent/runtime_core/capabilities.py`；计划构建/修复/执行重规划已迁入 `agent/runtime_core/planning_surface.py`，同步 run lifecycle 已迁入 `agent/runtime_core/run_lifecycle.py`，decision resume 已迁入 `agent/runtime_core/decision_resume.py`，cancel/retry recovery 已迁入 `agent/runtime_core/recovery.py`，preview 已迁入 `agent/runtime_core/preview.py`，plan evidence 已迁入 `agent/runtime_core/plan_evidence.py`，Runtime 只剩小型兼容 facade 和生命周期组合。
- FastAPI 与标准库 HTTP 入口已经通过 `agent/application/http.py` 共享读写语义，并通过 `agent/application/http_transport.py` 共享 request target/query、JSON 编解码、错误投影和 artifact 安全访问；两个入口只保留框架适配。
- `agent/` 保留公共契约、稳定入口和必要兼容回退；GIS 数据、栅格、矢量和几何实现统一位于
  `domains/gis/adapters/`，不再保留 `agent/` 根目录的重复 GIS 转发模块。Evidence 契约、注册、
  投影、恢复、重验证和组件证据已统一位于 `agent/evidence/`；根目录六个旧入口只做单向兼容导出。
- GIS 的 analysis-ready binding、release evidence、runtime capability snapshot 和 demo Tool Adapter
  也已统一位于 `domains/gis/adapters/`；`agent/` 根目录只保留历史导入 facade，ToolRegistry 本身不再顶层依赖 GIS。
- Console 源码位于 `web/src`，由 `scripts/build_console.py` 生成 `web/dist`；`web/index.html` 和根目录 `console_*.js` 只保留兼容 facade，HTTP 资源通过 `agent/web_assets.py` 选择 dist/source。

## 物理目录与语义索引

源码导航由 [`docs/code-index.json`](code-index.json) 提供，维护入口是
[`docs/code-index-overrides.json`](code-index-overrides.json)。索引通过目录规则覆盖完整职责簇，
再用文件级 override 校准公共 seam；当前生成结果要求所有已发现源码都有非默认语义分类。
详细规则见 [`docs/code-index-guide.md`](code-index-guide.md)；`agent/` 全量文件职责见
[`docs/agent-module-responsibilities.md`](agent-module-responsibilities.md)。

当前目录优化采取“职责簇优先、稳定导入兼容”的原则：`application`、`persistence`、`integration`、
`evidence`、`runtime_core`、`tooling`、`react`、`network`、`analysis` 和各 `domains/*` 是 canonical 深模块；`agent/` 根目录保留公共
契约/稳定入口，`web/` 根目录保留兼容 facade，`scripts/` 保持命令路径稳定。没有明确迁移收益
时不对根目录模块或脚本做机械移动，避免制造重复实现和浅层转发。

当前阶段先完成 `agent/` 的全量职责盘点：报告逐文件列出当前物理位置、职责、语义层、稳定性、阶段、导出数量和验证入口。
盘点报告不是迁移清单；后续分类必须以报告、项目内导入图和公共 seam 的组合证据为依据。

## 目标边界

```text
Transport adapters
  production_api.py / serve_api.py
             │
             ▼
      agent/application/http.py
             │
             ▼
   agent/application/http_transport.py
             │
             ▼
      agent/application/AgentService
             │
      ┌──────┴──────────────┐
      ▼             ▼
 Run / Session / Action / Decision / Interaction / Async  Catalog
      │
      ▼
 agent/runtime_core/
  resolve → clarify → plan → validate/repair
             → execute → answer → evidence/finalize
      │
      ▼
  DomainPack / ToolRegistry / ResultRegistry
      │
      ├── domains/gis/adapters
      ├── domains/text
      └── domains/indicators
```

## 不变量

1. `agent.runtime.AgentRuntime`、`agent.service.AgentService` 和 `run_demo.build_runtime` 保持可导入。
2. 兼容 facade 只能单向委托 canonical 实现，不能重新参与领域策略、授权或状态机。
3. 通用 Runtime 不读取 GIS 数据集名称、行政区名称或 GIS 专属阈值。
4. 工具执行只能经过 ToolRegistry；领域实现不能从 HTTP 入口直接调用。
5. Result、Evidence、Artifact、Async 和 SQLite/restart 使用同一核心契约。
6. 前端只消费 workspace、view、evidence 和 action contract，不按领域写结果分支。

## 重构顺序

1. 架构地图、兼容矩阵和静态守卫。
2. Domain Pack 与 GIS 适配器物理下沉。
3. Runtime 规划/执行/生命周期/投影拆分；projection、planning、execution、control、state、capability、planning-surface、run-lifecycle、decision-resume、recovery、preview、plan-evidence seams 已建立，Runtime 主模块已降为兼容 facade 与生命周期组合。
4. Application Service、持久化和 HTTP Application 收敛；Run、Session、Action、Decision、Interaction、Async 与 HTTP read/write 已建立 canonical seam。
5. Contract/Evidence 基础 helper 收敛；Evidence 的 contract、registry、projection、recovery、
   revalidation 和 component 已进入 `agent/evidence/`，版本常量只在 canonical 实现声明。
6. Console 源码与 `web/dist` 构建产物分离，HTTP 静态资源共享 `agent/web_assets.py` seam；后续继续按职责簇拆分 `console_app.js`。
7. Runtime 生命周期已阶段化，HTTP transport 已共享，架构守卫已区分 shim/facade/真实公共模块；
   Result Registry、Planning 和 Answer Generation 因公共/反向依赖暂留原 seam。后续全局规划只处理
   有明确替换收益的职责簇，并在稳定后再删除已确认无引用的兼容入口和临时文件。
