# M267 能力图

| 层 | 事实 | 责任 |
|---|---|---|
| 物理数据声明 | 有独立 Provider/health/discovery 映射 | Domain Catalog / DatasetCatalog |
| 派生数据声明 | 由前序数据或工具产生，无独立 Provider | Domain Catalog，仅作依赖事实 |
| Planner | 看到 bounded capability/workflow 声明 | 选择已注册能力 |
| Runtime/ToolRegistry | 校验前序结果、参数、权限和实际执行 | 最终执行门禁 |

依赖方向：

`physical/derived declaration → catalog validation → Planner context → Runtime preflight → ToolRegistry`
