# M268 通用矢量查询与真实专题扩展 Plan

状态：已完成

## 1. 接口与数据审计

- [x] 确认 `range_query` 已支持 bbox、条件和 limit。
- [x] 确认 `GeoPackageBackend` 当前只注册 roads/water 并固定使用 layer。
- [x] 确认 `earthquakes_wuhan` 已在武汉本地数据配置中登记，原始文件不进入 Git。

## 2. 文档与架构映射

- [x] 写 M268 Spec、Plan 和能力映射文档。
- [x] 明确文件后端兼容类名、DatasetCatalog 发现边界和 ToolRegistry 最终校验边界。

## 3. 文件型矢量适配器

- [x] 保留 `GeoPackageBackend` 类名作为兼容 seam，但从 Catalog 收集所有 ready vector 条目。
- [x] GeoPackage 按 dataset layer 读取；GeoJSON/Shapefile 等文件按路径读取；不可读格式返回结构化错误。
- [x] 保留 roads/water 的分类摘要、空间连接和候选筛选逻辑；通用查询不依赖业务字段。
- [x] 对非 roads/water 的通用查询只依赖 geometry、字段和条件，不增加 dataset 名称分支。

## 4. Tool schema 与 GIS Catalog

- [x] 将 `get_dataset_schema`、`range_query` 的静态 dataset enum 改为受限字符串。
- [x] 由实际 Catalog、Provider 和 Domain capability 继续校验数据集存在性和可用性。
- [x] 新增 `earthquake_event_query` capability，复用通用工具和 `vector_result`/通用 vector profile。
- [x] 新增最小声明式 workflow；Planner 可复用已有工具，不新增 Runtime 分支。
- [x] 将 `earthquakes_wuhan` 纳入 GIS dataset groups 和可发现数据映射，但不伪造默认生产环境的数据就绪状态。

## 5. Contract 与显式真实验收

- [x] 增加精简 M268 contract：Catalog 发现、GeoJSON schema、震级条件查询、旧 roads/water 回归。
- [x] 增加不影响默认生产配置的 `datasets.container.earthquakes.example.json`。
- [x] 使用 Docker 显式注入配置和数据根执行真实 GIS 验收；不把原始文件复制进仓库。

## 6. 收口

- [x] Docker compileall、M268 定向回归、architecture strict、quick/stage。
- [x] 更新 `docs/agent-context-resume.md`、中文进度文档和 `docs/agent-development-issues.md`。
- [ ] commit/push 后基于全局目标重规划下一阶段。

## 设计门禁

如果实现过程中需要在 Runtime、Planner 主循环、ToolRegistry dispatch 或前端主流程中增加 `earthquake` 判断，则暂停并重新找 seam；本阶段的正确扩展点是 DatasetCatalog、文件 Adapter、GIS Catalog 和已有 Result/Artifact 契约。
