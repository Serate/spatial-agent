# 本地数据整理清单

更新时间：2026-08-25

本清单对应宿主机目录 `D:\dataset\agent`。原始数据不进入仓库；仓库只保存数据目录模板、来源说明和可复现的状态约定。运行时配置模板为 [`config/datasets.wuhan.local.example.json`](../config/datasets.wuhan.local.example.json)。

## 整理原则

数据按“能否直接被 Agent 选择”分为三类：

| 状态 | 含义 | Planner 是否可直接选择 |
|---|---|---|
| `ready` | 文件可读取，且基本格式/关键元数据已核验 | 可以，但仍需检查 AOI、时间和 CRS 是否满足请求 |
| `partial` | 文件可读取，但覆盖范围或时间范围不完整 | 默认不选择；需要补充数据或用户确认 |
| `pending` | 已下载或压缩包可读取，但尚未解压、裁剪、字段核验或许可核验 | 不可以，仅作为可用数据线索 |

物理目录当前已经形成较清晰的分层：

```text
D:\dataset\agent\
├─ 原始压缩包与单文件下载       raw source candidates
├─ downloads\wuhan-gis\         已下载的外部开放数据与下载说明
├─ staged\                     已解压但仍需核验/裁剪的数据
│  ├─ dem-aster\               ASTER DEM 解压瓦片
│  ├─ land-use-2025\           2025 土地利用解压瓦片
│  ├─ hubei-vector\            湖北道路/水域/水系/铁路 GeoJSON
│  ├─ wuhan-vector\            武汉建筑/土地使用 GeoJSON
│  └─ hydrology\               HydroRIVERS/HydroBASINS 解压数据
├─ analysis-ready\              对齐到统一目标网格的可分析派生层
└─ partial\                     断点续传分片与错误日志（当前位于 downloads\wuhan-gis\partial）
```

原始文件已移动到 `raw/archives`，没有删除；`analysis-ready`、`downloads/wuhan-gis` 和 `wuhan-osm.gpkg` 保持原位置，Docker 只读挂载仍然有效。目录中的“整理”同时通过物理分层、配置状态和证据完成。

## 已核验、可直接作为输入的数据

| 数据集 | 类型 | 当前状态 | 覆盖/时间 | 关键元数据 | 适合能力 |
|---|---|---|---|---|---|
| `dem` | 栅格 | `ready` | 武汉目标范围 | EPSG:32649，30 m，4562×5277，Float32，NoData=-9999 | 高程、坡度、栅格筛选 |
| `land_use` | 栅格 | `ready` | 武汉目标范围 | EPSG:32649，30 m，4562×5277，UInt16，NoData=0 | 土地利用统计、像元组合 |
| `dem_tiles` | 栅格 | `ready` | 湖北及周边 9 个 ASTER 瓦片 | ASTER GDEM v3，约 30 m；同时存在 EPSG:32649/32650，需逐文件读取 | 原始高程补充、重建分析就绪层 |
| `land_use_tiles` | 栅格 | `ready` | 湖北及周边 4 个 2025 瓦片 | UTM 投影、约 30 m；不同瓦片范围需逐文件读取 | 土地利用补充、重建分析就绪层 |
| `roads` | 矢量 | `ready` | 武汉市 | OSM GeoPackage，EPSG:4326，68,903 条道路要素 | 道路汇总、距离/缓冲/可达性 |
| `water` | 矢量 | `ready` | 武汉市 | OSM GeoPackage，EPSG:4326，20,923 条水体/水系要素 | 水体汇总、距离/排除区 |
| `admin_areas` | 矢量 | `ready` | 湖北省 | GeoJSON，EPSG:4490，103 个县级要素 | 行政区识别与裁剪 |
| `admin_areas_geoboundaries` | 矢量 | `ready` | 中国，2017 | GeoJSON，EPSG:4326，2391 个县级要素，PDDL 1.0 | 全国/跨区域行政区发现 |
| `worldcover_2020` | 栅格 | `ready` | N30E111 + N30E114，2020 | EPSG:4326，约 10 m，ESA WorldCover v100 | 土地覆盖、建成区/水体分类、变化基线 |
| `earthquakes_wuhan` | 矢量 | `ready` | 武汉周边矩形，2000—2026 | GeoJSON，EPSG:4979，10 个目录要素 | 灾害事件与时间查询 |

注意：`ready` 只表示文件本身和登记元数据可用，不表示它自动满足任意行政区、时间范围或精度要求。Planner 仍需把覆盖范围、CRS、分辨率和时间范围纳入计划证据。

## 已下载但暂不进入默认分析路径的数据

以下数据已经登记为 `pending`，不会被 `DatasetCatalog.discover()` 的默认 `status="ready"` 查询返回。它们已完成解压，但仍需字段、范围、几何和许可核验：

- `raw/archives/hubei-wuhan-vector` 中的湖北省道路路网、水系水路、水域、铁路轨道以及武汉建筑轮廓/土地使用 GeoJSON 原始压缩包；对应解压文件位于 `staged/hubei-vector` 和 `staged/wuhan-vector`；
- `downloads/wuhan-gis` 中的 HydroRIVERS/HydroBASINS 原始压缩包（解压副本位于 `staged/hydrology`，分别约 142.9 万条河流和 16.1 万个流域面）；
- `raw/archives/land-use-2025` 中的 4 个 2025 土地利用 RAR 原始压缩包；
- `raw/archives/dem-aster` 中的 9 个 ASTER GDEM 原始 ZIP（解压瓦片位于 `staged/dem-aster`）。

它们下一步需要经过：文件格式/字段检查 → CRS 与范围检查 → 按 AOI 裁剪或拼接 → provenance/许可登记 → manifest → 才能提升为 `ready` 或 `partial`。解压动作已经完成，但不等于数据已经通过分析可用性检查。

`worldcover_2021_partial` 当前是可读取的单个 N30E114 瓦片，但缺少西侧瓦片，因此只作为时间比较候选，不代表完整武汉市 2021 土地覆盖。

## Docker 核验摘要

生产容器通过只读卷 `/data` 访问该目录。2026-08-25 在 GIS Docker 环境完成以下轻量核验：

- `rasterio` 成功读取分析就绪 DEM、土地利用、WorldCover 2020/2021 和 ASTER IMG；
- `fiona` 成功读取湖北县界、geoBoundaries、地震 GeoJSON；
- `wuhan-osm.gpkg` 的 `roads` 与 `water` 图层均可读取；
- ZIP 压缩包目录可读取；断点分片不作为数据集输入；
- 未对原始栅格做全量像元扫描，也未把压缩包自动解压到生产目录。

生产配置仍使用 [`config/datasets.container.example.json`](../config/datasets.container.example.json) 的 analysis-ready + OSM 最小闭环。扩展目录是本地数据发现和后续验收入口，不会在默认 CI 中绑定真实私有数据。

## 后续处理顺序

1. 先将武汉建筑、土地使用、湖北道路/水域压缩包解压为临时工作区，读取字段、几何类型、要素数、CRS 与范围；
2. 选择建筑密度、土地使用、道路/水系多尺度分析中真正需要的图层，避免把所有下载内容都注册成工具；
3. 对 HydroRIVERS/HydroBASINS 做武汉—长江流域裁剪，保留源版本和许可证据；
4. 补齐 WorldCover 2021 缺失瓦片后，生成按年份的 analysis-ready 派生层；
5. 将“数据发现 → 覆盖/时间/CRS 检查 → 计划澄清或选择 → 结果证据”接入通用 Planner/Runtime，而不是新增固定数据集分支。
