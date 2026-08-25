# M266 声明式 Domain Catalog 接入 Plan

状态：已完成

## 任务

### 1. 建立公共声明校验器

- [x] 新增 `agent/domain_catalog.py`。
- [x] 定义 `DomainCatalogSpec`、`build_domain_catalog()` 和 workflow copy seam。
- [x] 校验 capability/dataset/tool/result/workflow 的跨引用和边界。

### 2. 迁移两个 Domain Pack

- [x] Indicators 使用 `INDICATOR_CATALOG_SPEC`。
- [x] Economic 使用 `ECONOMIC_CATALOG_SPEC`。
- [x] 保持 GIS 现有复杂路径，待跨 Domain 验收后再评估是否迁移。

### 3. 契约与回归

- [x] 新增 M266 精简 contract：合法构建、非法引用拒绝、深拷贝隔离、双 Domain catalog。
- [x] Docker 运行 M266/Indicators/Economic 定向回归。
- [x] Docker 运行 quick、stage、compileall、architecture strict。

### 4. 收口

- [x] 更新恢复卡、milestones 和中文问题日志。
- [x] 提交并推送阶段版本。
- [x] 从全局七维度重规划下一阶段，并决定是否用第三个指标类专题做真实接入验收。

## Completion evidence

- Docker M266/Indicators/Economic 定向回归 **15/15** 通过。
- Docker `quick + stage`、`compileall`、`architecture_check.py --strict` 和 `git diff --check` 通过。
- 生产容器重建后保持 `healthy`；Runtime、HTTP、ToolRegistry、Result、Artifact 和前端主流程未修改。
- 迁移范围限定为 Indicators/Economic；GIS 复杂 catalog 保持原实现，待后续全局验收后再决定是否迁移。

## 风险控制

- 不迁移 GIS 复杂声明，避免一次性改变成熟空间能力。
- 不修改公共 Runtime 和 transport；所有变化限定在声明构建 seam 与 Domain Pack 适配端。
- 默认测试保持精简，真实数据/模型/Docker 作为显式验收路径。
