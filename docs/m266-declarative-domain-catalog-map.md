# M266 能力图

| 模块 | 职责 | 归属 |
|---|---|---|
| `DomainCatalogSpec` | 描述一个 Domain 的能力、数据集、工具、workflow 与结果类型 | Domain Pack 声明 |
| `validate_domain_catalog_spec` | 校验声明之间的公共引用边界 | Agent 公共契约 |
| `build_domain_catalog` | 通过既有 capability catalog 构建 Planner-facing catalog | Agent 公共工厂 |
| Indicators/Economic adapters | 提供各自数据、事实解析、工具和结果实现 | Domain Pack |
| Runtime/Planner/ToolRegistry | 继续负责生命周期、计划、dispatch 和执行门禁 | Agent Runtime |

依赖方向：

`Domain Pack declarations → DomainCatalogSpec → capability_catalog → Planner context → Runtime/ToolRegistry`
