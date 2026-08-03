# M0 场景与验收范围

## 1. 第一版场景

第一版只实现“自然语言驱动的空间条件查询”。

示例任务：

> 查询距离主干道 500 米以内、坡度超过 25 度的区域，并按行政区统计面积。

这个场景包含多个可验证步骤，但不需要先实现复杂的三维场景或无人机规划，适合验证 Agent 的核心能力：

- 从自然语言提取数据集和空间条件。
- 将一个请求拆成多个有依赖关系的步骤。
- 从工具注册表中选择工具。
- 在工具失败时报告错误或重试。
- 根据确定性工具结果生成摘要。

## 2. 数据契约

第一阶段使用三个逻辑图层。实现时可以先用 GeoJSON 或内存数据，后续再替换为 PostGIS、Spark/Sedona 或 HBase Adapter。

| 图层 | 几何类型 | 最小字段 |
|---|---|---|
| roads | LineString | id, road_level, geometry |
| slope | Polygon | id, slope_degree, geometry |
| admin_areas | Polygon | id, name, geometry |

空间参考统一为 EPSG:4326。距离计算工具内部可以转换到适合距离计算的投影坐标系，但转换细节对 Agent 隐藏。

## 3. 第一阶段工具

只开放三个核心工具：

1. get_dataset_schema
2. range_query
3. spatial_join

工具都为只读操作，不需要人工确认。后续的 render_map 和 export_result 不属于 M0。

## 4. 预期计划

对于示例任务，Agent 应生成近似以下的结构化计划：

~~~text
1. 获取 roads、slope、admin_areas 的 Schema。
2. 过滤 slope.slope_degree > 25。
3. 使用 spatial_join 的 near 关系查询道路 500 米范围内的坡度区域。
4. 将结果与 admin_areas 执行空间连接。
5. 按行政区统计面积并返回摘要。
~~~

M0 不要求真正执行上面全部步骤，但要求 Planner 能生成可校验的计划，且计划中的工具名称和参数必须符合工具 Schema。

## 5. M0 验收标准

- 三个工具都有明确的输入和输出 Schema。
- 五条评测用例可以被加载为结构化数据。
- 每条评测用例都有期望工具、关键约束和最大步骤数。
- 至少一条用例包含缺失信息。
- 至少一条用例包含越权或不安全请求。
- 计划中不允许出现未注册工具。
- 不允许直接执行任意 SQL、Shell 或模型生成代码。

## 6. 暂不解决的问题

- 真实大规模数据性能。
- 分布式任务调度。
- 三维点云和 Mesh。
- 长期记忆。
- 多 Agent 协作。
- 自动修改数据。
