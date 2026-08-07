# 核心流程整体验收

本文档定义 Spatial Agent 当前 Demo 的产品级验收基线。底层模块测试仍然保留，但后续功能修改至少不能破坏这里的核心流程。

## 三条核心流程

| 流程 | 示例问题 | 必须验证 |
| --- | --- | --- |
| 栅格概况 | 查询 DEM 栅格元数据 | 选择正确工具，返回元数据摘要 |
| 区域分析 | 分析洪山区 DEM 高程概况 | 使用行政区范围，返回有效像元和统计指标 |
| 建设筛选 | 分析洪山区建设适宜性，坡度不超过 20 度 | 同时完成高程、坡度、土地利用和候选筛选，并明确是演示筛选 |

## 共同验收要求

- 通用问题不调用空间工具。
- 不支持的空间领域进入澄清，不编造分析结果。
- 缺少行政区名称时先澄清，补充名称后使用同一 `session_id` 完成任务。
- 空间计划必须经过 TaskPlan 校验和 ToolRegistry 执行。
- 真实 GIS 结果必须包含可解释的统计指标或结果引用。
- GeoJSON、地图预览和答案必须使用同一结果来源，不能混用不同 CRS 的原始坐标。
- 内存后端只能用于结构和流程演示，不能被描述为真实栅格分析。

## 自动化入口

```powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m unittest tests.test_m44_core_workflows
```

真实 GIS 入口仍使用 `tests.test_m15_raster_metadata` 和 `docs/demo-checklist.md` 中的命令；真实模型入口必须显式设置 `SPATIAL_AGENT_LIVE_OPENAI=1`，不纳入默认 CI。
