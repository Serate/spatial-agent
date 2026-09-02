# 公共接口与兼容矩阵

重构默认采用渐进兼容。旧入口只有在 canonical 活动路径稳定、历史读取完成迁移、最小回归通过后才允许删除。

| 接口 | 当前实现 | 重构后 canonical 实现 | 处理方式 |
|---|---|---|---|
| `agent.runtime.AgentRuntime` | `agent/runtime.py` | `agent/runtime_core/` | 保留同名薄 facade，继续导出 Runtime 和状态类型 |
| `agent.service.AgentService` | `agent/service.py` | `agent/application/` | 保留同名应用 facade，公共方法委托到 Application 模块 |
| `run_demo.build_runtime` | `agent/runtime_factory.py` | Runtime Factory | 保留 CLI 兼容导出，不增加第二套工厂 |
| `production_api.py` | FastAPI 路由与生命周期 | `agent/application/http.py` + `agent/application/http_transport.py` + FastAPI adapter | 保留 endpoint 和响应 envelope |
| `serve_api.py` | 标准库 HTTP handler | `agent/application/http.py` + `agent/application/http_transport.py` + stdlib adapter | 保留本地 GIS 启动方式，仅保留框架适配 |
| `RuntimeRunLifecycle.run` | 单一大编排方法 | `agent/runtime_core/run_lifecycle.py` 的 resolve/clarify/plan/validate-repair/execute/answer/evidence stages | 保持 `AgentRuntime.run()` 签名和 Result 生命周期 |
| 旧 Artifact | `artifact_store`/`sqlite_store` legacy fields | `agent/persistence` | 继续读取，新增结果只写 canonical schema |
| `agent/workflow_templates` | 通用校验 + GIS lazy fallback | workflow compiler | 保留兼容导出，活动路径显式传入 Domain catalog |
| `agent/request_model` | Domain parser facade | Domain-owned request facts | 保留旧导入，禁止公共 Runtime 直接调用 GIS parser |
| `agent/answer_composer` | GIS composer re-export | Domain-owned composer + Answer Generation | 只保留兼容导出 |
| `agent/service_async` / `service_format` / `service_sessions` / `service_state` | Application Service 支撑实现 | `agent/application/service_*.py` | canonical 实现已迁移，旧路径保留单向兼容 facade |
| `agent/analysis_ready_binding` | GIS analysis-ready source binding | `domains/gis/adapters/analysis_ready_binding.py` | canonical 实现已下沉，旧路径保留单向兼容 facade |
| `agent/release_evidence` | GIS release evidence | `domains/gis/adapters/release_evidence.py` | canonical 实现已下沉，旧路径保留单向兼容 facade |
| `agent/runtime_capabilities` | GIS runtime capability snapshot | `domains/gis/adapters/runtime_capabilities.py` | canonical 实现已下沉，旧路径保留单向兼容 facade |
| `agent.tools.DemoSpatialAdapter` | GIS deterministic demo Adapter | `domains/gis/adapters/demo_tool.py` | `agent.tools` 惰性兼容导出，ToolRegistry 保持领域中立 |
| `agent/evidence_contract.py`、`evidence_projection.py`、`evidence_recovery.py`、`evidence_registry.py`、`evidence_revalidation.py`、`component_evidence.py` | Evidence 契约、投影、恢复、注册、重验证和组件证据 | `agent/evidence/` | canonical 实现已下沉；旧路径只做单向兼容 facade，schema 与恢复语义不变 |
| `web/index.html` | 内联 CSS/JS + 静态入口 | `frontend/src` + `web/dist` | 迁移后不再作为源码维护 |

## 架构守卫清单

- `COMPAT_SHIMS`：只包含简单历史转发入口。
- `COMPAT_FACADES`：包含有限兼容适配的旧入口。
- `PUBLIC_MODULES`：`domain_contract`、`domain_registry`、`request_model`、`result_registry`、`workflow_templates` 等真实公共契约/引擎，不得进入兼容豁免集合。

`scripts/architecture_check.py --strict` 输出三类清单、分类 schema 版本和逐模块分类，并检查它们不重叠。对 `COMPAT_SHIMS` 还会用 AST 确认模块只包含文档、导入、未来导入和字符串 `__all__`，超过 80 行或包含实现节点则失败；`COMPAT_FACADES` 不套用 shim 形状规则。当前检查范围是顶层 Domain import；递归 lazy import 检查保留为独立后续任务。

## 删除条件

- `rg` 和架构检查确认没有活动生产引用。
- 至少一个兼容 import smoke 仍可证明替代入口存在。
- 历史 Artifact、SQLite/restart 和 HTTP contract 已通过。
- 旧入口已记录迁移状态和删除版本。
