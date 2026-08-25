# M268 通用矢量查询能力映射

## 目标路径

```text
DatasetCatalog
  └─ ready vector entries
      └─ GeoPackageBackend（兼容类名，文件型矢量 Adapter）
          ├─ GeoPackage layer reader
          ├─ GeoJSON reader
          ├─ Shapefile reader
          └─ generic schema/range_query
                ↓
        HybridSpatialBackend
                ↓
        SpatialToolAdapter / ToolRegistry
                ↓
      GIS Catalog capability discovery
                ↓
        Planner → TaskPlan → Runtime
                ↓
      vector Result / Artifact / Evidence / View
```

## 责任边界

| 模块 | 负责 | 不负责 |
|---|---|---|
| DatasetCatalog | 数据集名称、格式、文件、状态、来源和发现事实 | 选择业务步骤、执行工具授权 |
| GeoPackageBackend | 按 DatasetEntry 读取文件、schema、条件过滤和 bbox | 解析自然语言、编排 Runtime |
| ToolRegistry | 工具注册、schema、参数、权限和 dispatch | 猜测数据集是否存在 |
| GIS Catalog | 声明数据与能力的关系、workflow 和结果类型 | 读取文件、绕过 ToolRegistry |
| Planner | 根据请求事实和能力目录组合已注册工具 | 发明工具、发明数据集 |
| Runtime | 生命周期、重试、恢复、证据和结果一致性 | GIS/地震业务专用策略 |

## 兼容策略

- `GeoPackageBackend` 名称暂时保留，以减少旧调用方迁移成本；其实现语义扩展为“文件型矢量后端”。
- roads/water 的历史返回字段与空间分析路径保持稳定。
- 新数据集默认只获得通用 schema/query 能力，不自动获得道路、水体分类或区域摘要等业务语义。
- 真实配置与默认容器配置分离；只有显式验收配置才暴露 `earthquakes_wuhan`。
