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

## Future Real Data Backends

The next real backend should implement the SpatialBackend interface:

~~~text
get_dataset_schema(dataset)
range_query(dataset, conditions, limit, bbox=None)
spatial_join(left_dataset, right_dataset, relation, distance_m=None)
~~~

Candidate adapters:

- GeoJSONBackend: reads local GeoJSON files and performs small local queries.
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

All backend implementations must return result_ref rather than large raw geometry payloads. This keeps model context small and makes map rendering/export a separate tool.

## Why This Matters For Interviews

This shows the Agent is not a prompt-only demo. The model plans work, ToolRegistry validates calls, and SpatialBackend owns data execution. Replacing in-memory data with PostGIS or Spark is an adapter change, not an Agent rewrite.
