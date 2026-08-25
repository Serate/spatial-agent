# M267 派生数据集声明与 GIS Catalog 迁移 Plan

状态：已完成

## 任务

### 1. 声明模型

- [x] 在 `DomainCatalogSpec` 增加 bounded `derived_datasets`。
- [x] 校验 capability 可引用物理或派生数据集；dataset groups 仍只能引用可发现物理数据集。
- [x] 保持 builder 输出版本化、深拷贝和 ToolRegistry 独立。

### 2. GIS 迁移

- [x] 新增 `GIS_CATALOG_SPEC`，通过同一 builder 构建 GIS capability/workflow catalog。
- [x] 只登记 `slope` 为派生数据集，不移动 GIS 算法或请求解析。
- [x] 保持旧 `capability_catalog` 的兼容输出和 workflow copy 语义。

### 3. 验收与收口

- [x] 新增 M267 精简 contract，比较迁移前/后的声明 ID 和边界。
- [x] Docker 运行定向回归及分层 profile。
- [x] 更新中文恢复卡、里程碑、问题日志，提交并推送。

## Completion evidence

- 定向 22/22；quick/stage、compileall、architecture strict 通过。
- GIS 迁移只改变声明构建入口和派生数据标记，未改算法、ToolRegistry schema 或 Runtime 生命周期。
