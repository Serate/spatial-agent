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
- `agent/runtime.py` 的内存状态和能力目录职责已迁入 `agent/runtime_state.py` 与 `agent/runtime_core/capabilities.py`；计划构建/修复/执行重规划已迁入 `agent/runtime_core/planning_surface.py`，同步 run lifecycle 已迁入 `agent/runtime_core/run_lifecycle.py`，decision resume、retry/cancel/recovery 和 evidence helper 仍待继续物理拆分。
- FastAPI 与标准库 HTTP 入口已经通过 `agent/application/http.py` 共享读写语义；transport 只负责 URL/JSON、HTTP 状态码和 artifact 路径安全。
- `agent/` 保留历史 GIS facade、legacy 字段和兼容回退；evidence recovery 已并入 `agent/evidence_projection.py`，旧模块只做单向兼容导出。
- Console 源码位于 `web/src`，由 `scripts/build_console.py` 生成 `web/dist`；`web/index.html` 和根目录 `console_*.js` 只保留兼容 facade，HTTP 资源通过 `agent/web_assets.py` 选择 dist/source。

## 目标边界

```text
Transport adapters
  production_api.py / serve_api.py
             │
             ▼
      agent/application/http.py
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
  planning → execution → lifecycle → projection
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
3. Runtime 规划/执行/生命周期/投影拆分；projection、planning、execution、control、state、capability、planning-surface、run-lifecycle seams 已建立，decision/retry/recovery 与 evidence helper 仍待收敛。
4. Application Service、持久化和 HTTP Application 收敛；Run、Session、Action、Decision、Interaction、Async 与 HTTP read/write 已建立 canonical seam。
5. Contract/Evidence 基础 helper 收敛；evidence projection/recovery 已共享一个 canonical seam，版本常量避免重复声明。
6. Console 源码与 `web/dist` 构建产物分离，HTTP 静态资源共享 `agent/web_assets.py` seam；后续继续按职责簇拆分 `console_app.js`。
7. Runtime/Service 剩余职责与前端主应用职责完成物理收敛，删除已确认无引用的兼容入口和临时文件，完成全局验收。
