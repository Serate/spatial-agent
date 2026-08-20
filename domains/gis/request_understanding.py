"""GIS-owned request understanding and capability discovery guidance."""

GIS_REQUEST_UNDERSTANDING_GUIDANCE = {
    "domain_id": "gis",
    "fact_fields": [
        "admin_name",
        "tasks",
        "datasets",
        "constraints",
        "evidence",
    ],
    "task_hints": [
        {"id": "admin_boundary", "label": "行政区边界", "phrases": ["行政区", "边界", "区划"]},
        {"id": "elevation", "label": "高程", "phrases": ["DEM", "高程", "地形"]},
        {"id": "slope", "label": "坡度", "phrases": ["坡度"]},
        {"id": "land_use", "label": "土地利用", "phrases": ["土地利用", "地类"]},
        {"id": "roads", "label": "道路", "phrases": ["道路", "路网"]},
        {"id": "water", "label": "水体", "phrases": ["水体", "河流", "湖泊"]},
        {"id": "buildability", "label": "建设候选筛选", "phrases": ["建设适宜性", "建设候选"]},
    ],
    "constraint_hints": [
        {"id": "slope_max", "label": "最大坡度", "phrases": ["坡度不超过", "坡度小于"]},
        {"id": "road_distance_max", "label": "道路距离上限", "phrases": ["距离道路不超过", "道路附近"]},
        {"id": "exclude_water", "label": "排除水体", "phrases": ["排除水体", "避开水体"]},
    ],
    "evidence_hints": [
        {"id": "geometry", "label": "空间几何", "phrases": ["边界", "地图", "空间预览"]},
        {"id": "trace", "label": "执行轨迹", "phrases": ["步骤", "过程", "依据"]},
    ],
    "clarification_policy": [
        "空间请求缺少行政区、数据集或阈值时，先返回结构化澄清，不猜测参数。",
        "未注册的空间意图不能伪装为已支持的分析。",
    ],
    "discovery_policy": [
        "先根据 RequestFacts 选择候选能力，再交给 Planner 生成 TaskPlan。",
        "能力目录、工具 schema 和数据健康状态共同决定可执行性。",
    ],
}
