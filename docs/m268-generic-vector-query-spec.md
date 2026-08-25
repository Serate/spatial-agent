# M268 通用矢量查询与真实专题扩展 Spec

状态：已完成

## 背景

当前 `range_query` 已支持 bbox、结构化属性条件和结果数量上限，但真实文件后端只注册 `roads`、`water`，并且固定按 GeoPackage layer 读取。这样新增一个同类型的真实矢量数据集时，必须修改后端分支，无法验证“数据目录 + 通用工具 + Domain 能力声明”即可扩展专题。

本阶段使用已登记的 `earthquakes_wuhan` GeoJSON 作为真实验收数据。地震只是验证样本，不为地震请求增加专用 Runtime、专用执行循环或专用工具。

## 目标

1. 让文件型矢量后端从 `DatasetCatalog` 发现所有状态可用的 vector 数据集。
2. 同一个 `range_query` 支持 GeoPackage、GeoJSON 和 Shapefile 等已支持的文件格式；保留 roads/water 的历史结果契约。
3. 让 `get_dataset_schema` 和 `range_query` 的数据集参数由 ToolRegistry 做字符串/schema 校验、由 DatasetCatalog 和 Domain preflight 做实际合法性校验，而不是由静态 enum 锁死。
4. 在 GIS Domain Catalog 中声明一个通用地震事件查询能力，复用既有 `get_dataset_schema` 与 `range_query`。
5. 通过真实地震数据验证字段 schema、bbox、`mag >= 2.5` 条件和来源证据可以贯穿 Planner → ToolRegistry → Adapter → Result。

## 非目标

- 不新增地震专用工具、地震专用 Runtime 分支或地震专用回答模板。
- 不把原始数据提交到 Git，不把宿主机绝对路径写入容器配置。
- 不放宽 ToolRegistry 的注册、参数、权限和 dispatch 校验。
- 不把 GeoJSON 全量几何塞进 Planner context；查询仍遵守结果数量和 artifact 预算。
- 不在默认 CI 中依赖真实数据、真实模型或宿主机路径。

## 契约

### 数据发现

`DatasetCatalog` 是物理数据集的唯一发现来源。只有 `kind=vector` 且文件存在、状态为 ready（或历史配置未声明 status）的条目可进入文件后端；`pending/partial` 条目不能被执行工具选中。

### schema

`get_dataset_schema(dataset)` 返回既有字段：`dataset`、`geometry_type`、`crs`、`fields`，并可附加 bounded `metrics` 和 `source`。GeoJSON 的 `EPSG:4979` 等 CRS 必须保留，不强行改写为二维 CRS。

### range query

输入：

- `dataset`：字符串，由 ToolRegistry 做类型/长度校验，由实际 Catalog 做存在性校验；
- `conditions`：`eq/neq/gt/gte/lt/lte/in` 条件数组；
- `bbox`：可选 `[minx, miny, maxx, maxy]`，按数据 CRS 转换到 WGS84 后筛选；
- `limit`：1–10000。

输出保持 `result_ref`、`count`、`crs`，并包含 bounded metrics；真实矢量结果继续通过 result/artifact 导出能力获取几何。

### 失败与恢复

- 未登记、非 vector、文件不存在或格式不可读取：返回既有结构化 ToolError/不可用状态；
- 字段不存在：返回字段错误，不猜测字段名；
- 条件值类型不兼容：返回可读校验错误；
- 数据状态 pending/partial：返回可恢复的数据未就绪说明；
- 不因为空结果伪造“没有事件”之外的结论。

## Completion evidence

1. Docker M268 contract **3/3**；M267/M266/M265 定向回归 **14/14**。
2. 显式真实 Docker GIS 验收读取真实 `earthquakes_wuhan` GeoJSON：schema 包含 `mag/place/time`，保留 `EPSG:4979`；`mag >= 2.5` + 武汉 bbox 返回 1 条记录，健康检查报告 10 个要素且为 ready。
3. 旧 GIS/回答契约回归 **47/47**（7 个真实旧数据用例按环境跳过），历史脆弱自然语言断言已改为结构化事实断言。
4. GIS catalog 能发现 `earthquake_event_query`，其工具仅为 `get_dataset_schema`、`range_query`，数据 readiness 来自 DatasetCatalog；Rule Planner 通过声明式 workflow fallback 复用同一工具链。
5. Planner context 与 ToolRegistry 未增加地震专用 Runtime 分支；文件后端根据 DatasetCatalog 的 vector 条目和格式选择读取器。
6. Docker `compileall`、architecture strict、quick、stage 通过；默认生产配置未挂载真实地震数据，真实数据只通过显式验收配置和一次性挂载使用。
