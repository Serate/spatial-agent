# M266 声明式 Domain Catalog 接入 Spec

状态：已完成

## 背景

Indicators 与 Economic 已经复用了 Runtime、Planner、ToolRegistry 和指标分析核心，但两个 Domain Pack 仍分别重复组合 capability、dataset/tool 映射、workflow、允许工具和结果类型。新增专题如果继续复制这些组合逻辑，接入成本会随领域数量线性上升。

## 目标

增加领域中立的 `DomainCatalogSpec` 与 `build_domain_catalog()`，统一校验并构建 Domain-owned 的 capability catalog；不改变 Runtime 生命周期、Planner 选择、ToolRegistry dispatch、Result/Artifact/Evidence 契约。

## 公共契约

声明至少包含：

- `domain_id`
- capability declarations
- dataset → tool 映射与 dataset groups
- workflow templates
- known tool names
- known result types
- 可选 `analysis_ready_capability_ids`

构建前必须校验：ID 唯一、数据集引用、工具引用、结果类型引用、workflow `allowed_tools`、step blueprint 工具边界和分析就绪能力引用。校验失败应明确拒绝，不生成部分 catalog。

## 边界

- Domain Pack 仍拥有数据读取、RequestFacts、领域 Planner、工具实现、结果视图和来源证据。
- 公共工厂只处理声明的结构校验、深拷贝和现有 `capability_catalog` 组装。
- 不把 GIS、经济、指标名称写进公共模块。
- 不动态导入任意 Python 路径，不替代 ToolRegistry schema 校验，不把 catalog 当执行授权。
- GIS 当前复杂 catalog 不强行迁移；先用 Indicators 与 Economic 验证接入 seam。

## 验收标准

1. Indicators 与 Economic 使用同一 `DomainCatalogSpec`/builder。
2. 错误的工具、结果类型、数据集或 workflow 引用在进入 Planner 前被拒绝。
3. Builder 返回独立 JSON-safe catalog，不允许调用方修改 Domain 原声明。
4. Runtime、Planner、ToolRegistry、HTTP、Result、Artifact 和前端主流程无改动。
5. Docker 定向 contract、Indicators/Economic 回归、quick/stage、compileall 和 architecture strict 通过。
