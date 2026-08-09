# Data Adapter Plan

M3 does not require a production dataset to be present. The goal is to make data access replaceable so the Agent Runtime can run today with an in-memory backend and later switch to a real spatial backend without changing Planner, Runtime, or Tool Registry code.

## Current Adapter

The current runtime uses:

~~~text
ToolRegistry
  -> SpatialToolAdapter
  -> InMemorySpatialBackend
~~~

InMemorySpatialBackend is a deterministic placeholder backend. It returns stable schemas, counts, result references, and metrics. It is useful for tests, demos, and interview explanations before real data is available.

## Current Wuhan GIS Adapter

The local GIS path now also supports a clipped OSM GeoPackage:

| Dataset | Layer | Source | CRS | Current role |
|---|---|---|---|---|
| roads | `roads` | OpenStreetMap ways with `highway` | EPSG:4326 | road inventory and bounded attribute query |
| water | `water` | OpenStreetMap ways with `natural=water` or `waterway` | EPSG:4326 | water inventory and bounded attribute query |

The source is downloaded as tiled Overpass JSON, globally deduplicated by OSM `type:id`, clipped to the union of Wuhan's 13 district geometries, and written to GeoPackage. `GeoPackageBackend` keeps the raw source outside the repository, returns bounded `result_ref` values, and exports only a limited GeoJSON summary for the Console map. OSM attribution and ODbL restrictions remain part of the result provenance.

The Agent also supports `get_zonal_vector_summary` for a named administrative area and a real `near` spatial join between the `roads` and `water` layers. These operations return aggregate counts plus bounded geometry references; they do not expose the full 100+ MB source to the model or browser.

This is an OSM demonstration layer, not a legal road, water, ecological-redline, or planning-permission layer. Exact boundary clipping and geometry checks are recorded in the generated quality report.

## Future Real Data Backends

The next real backend should implement the SpatialBackend interface:

~~~text
get_dataset_schema(dataset)
range_query(dataset, conditions, limit, bbox=None)
spatial_join(left_dataset, right_dataset, relation, distance_m=None)
get_dataset_health_report(dataset="all", max_files=10)
~~~

Candidate adapters:

- GeoJSONBackend: reads local GeoJSON files and performs small local queries.
- RasterMetadataBackend: reads raster file metadata without loading raster arrays.
- PostGISBackend: translates structured conditions into parameterized SQL.
- SparkSedonaBackend: submits distributed spatial jobs and returns result references.
- HBaseSpatialBackend: uses spatial row keys and secondary indexes for lookup.

The rest of the Agent system should not know which backend is active.

## Minimum Data Contract

When real data is available, provide these logical layers first:

| Dataset | Geometry | Required fields |
|---|---|---|
| roads | LineString | id, road_level, geometry |
| slope | Polygon | id, slope_degree, geometry |
| admin_areas | Polygon | id, name, geometry |

Raster datasets are exposed through metadata tools first:

| Dataset | Format | Metadata returned |
|---|---|---|
| dem | IMG | file count, sample files, width, height, band count, dtype, CRS, bounds, pixel size |
| land_use | TIF | file count, sample files, width, height, band count, dtype, CRS, bounds, pixel size |

All backend implementations must return result_ref rather than large raw geometry payloads. This keeps model context small and makes map rendering/export a separate tool.
Raster metadata tools must not read full pixel arrays, clip rasters, or resample data.

数据健康检查只进行有界的文件读取、CRS/范围汇总和基础几何有效性检查；它用于在 Agent 执行分析前解释数据是否可用，不替代数据来源审查、精度评定、法定测绘成果或规划审批依据。

## Why This Matters For Interviews

This shows the Agent is not a prompt-only demo. The model plans work, ToolRegistry validates calls, and SpatialBackend owns data execution. Replacing in-memory data with PostGIS or Spark is an adapter change, not an Agent rewrite.
