# M267 派生数据集声明与 GIS Catalog 迁移 Spec

状态：已完成

## 背景

M266 的 `DomainCatalogSpec` 已统一 Indicators/Economic 的声明校验。对 GIS 做只读试迁移时发现，兼容能力 `legacy_road_slope` 声明了 `slope`，但它不是独立的物理 dataset/tool provider，而是由 DEM/空间处理得到的派生或虚拟数据集。把所有 capability dataset 强制要求出现在物理 dataset-tool 映射中，会错误阻止合法的复杂 Domain 声明。

## 目标

让声明模型明确区分：

- `dataset_tool_capabilities`：可由数据 Provider 直接发现/读取的物理数据集；
- `derived_datasets`：由已有数据或前序工具步骤产生、没有独立 Provider 映射的派生数据集。

在不修改 Runtime、Planner、ToolRegistry、GIS 算法和执行 gate 的前提下，把 GIS capability/workflow catalog 接入 M266 公共工厂。

## 约束

1. `derived_datasets` 只能放宽 catalog 声明交叉引用，不能把派生数据标记为 ready，也不能绕过运行时数据/前置结果校验。
2. 派生数据必须仍出现在 capability 的声明中，便于 Planner 理解依赖；它不自动进入 dataset health 或 data evidence。
3. 公共模块不能出现 `slope`、GIS 工具名或领域策略分支。
4. GIS 的 legacy workflow、capability IDs、结果类型和 ToolRegistry 清单保持不变。

## 验收标准

- GIS `DomainCatalogSpec` 通过公共校验，且只新增 `derived_datasets=("slope",)` 声明。
- GIS capability catalog 的能力数量、数据集、工具、结果类型和 workflow IDs 与迁移前一致。
- `legacy_road_slope` 仍不会因 builder 而获得虚假的数据就绪状态。
- Docker GIS/M266/M265/Indicators/Economic 回归、quick/stage、compileall、architecture strict 通过。

## Completion evidence

- Docker M267/M266/M249/M265/M251/M263 定向回归 **22/22** 通过。
- `slope` 仅出现在 capability 的 `derived_datasets` 依赖中，不进入物理 dataset groups 或 dataset evidence；Planner 可以看到依赖，执行 gate 仍由 Runtime/ToolRegistry/Domain preflight 负责。
- GIS 的 capability/workflow 声明通过同一 `DomainCatalogSpec` builder；容器重建后 quick/stage、compileall 和 architecture strict 通过。
