"""Bounded intermediate representation for open-ended spatial requests.

This module only interprets request text. It does not select tools or execute
GIS work, so planners can evolve independently from entity extraction.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, Optional, Tuple


_ADMIN_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,12}(?:自治县|林区|市|县|区))(?!域)")
_ADMIN_PREFIXES = (
    "查询", "查找", "查看", "获取", "统计", "分析", "帮我", "请", "找出",
    "请对", "针对", "关于", "面向", "在", "对", "为",
    "筛选", "过滤", "挑选", "筛出", "选出",
)
_ADMIN_SUFFIXES = ("行政区", "县域", "边界", "区域", "地区", "片区", "范围")
_ADMIN_NAME_SUFFIXES = ("市", "县", "区", "自治县", "林区")
_INVALID_ADMIN_NAME_TERMS = (
    "道路", "路网", "坡度", "高程", "土地", "水体", "河流", "湖泊", "附近",
    "距离", "超过", "以内", "不超过", "的", "和", "与", "及", "或",
)
_SLOPE_PATTERN = re.compile(
    r"坡度(?:不超过|不大于|小于|低于|超过|大于|阈值为)\s*(\d+(?:\.\d+)?)\s*度"
)
_DISTANCE_PATTERN = re.compile(
    r"(?:距离)?道路(?:不超过|不大于|小于|低于|以内|附近)?\s*(\d+(?:\.\d+)?)\s*米"
)


REQUEST_FACTS_SCHEMA_VERSION = "spatial-agent.request-facts.v1"


@dataclass(frozen=True)
class RequestFacts:
    """Planner-neutral request facts extracted from natural language."""

    text: str
    admin_name: Optional[str]
    tasks: Tuple[str, ...]
    datasets: Tuple[str, ...]
    constraints: Dict[str, Any]
    evidence: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": REQUEST_FACTS_SCHEMA_VERSION,
            "text": self.text,
            "admin_name": self.admin_name,
            "tasks": list(self.tasks),
            "datasets": list(self.datasets),
            "constraints": dict(self.constraints),
            "evidence": list(self.evidence),
        }

    def as_context_dict(self) -> Dict[str, Any]:
        """Return the bounded, non-verbatim facts safe for planner context."""
        return {
            "schema_version": REQUEST_FACTS_SCHEMA_VERSION,
            "admin_name": self.admin_name,
            "tasks": list(self.tasks),
            "datasets": list(self.datasets),
            "constraints": dict(self.constraints),
            "evidence": list(self.evidence),
        }


def _clean_admin_name(value: str) -> str:
    name = value.strip()
    changed = True
    while changed:
        changed = False
        for prefix in _ADMIN_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix):]
                changed = True
                break
    changed = True
    while changed:
        changed = False
        for suffix in _ADMIN_SUFFIXES:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                changed = True
                break
    return name.strip()


def _extract_admin_name(text: str) -> Optional[str]:
    for match in _ADMIN_PATTERN.finditer(text):
        name = _clean_admin_name(match.group(1))
        if (
            name
            and name not in {"行政区", "县域"}
            and name.endswith(_ADMIN_NAME_SUFFIXES)
            and not any(term in name for term in _INVALID_ADMIN_NAME_TERMS)
        ):
            return name
    return None


def parse_spatial_request(request: str) -> RequestFacts:
    """Extract reusable facts without making a planning or execution claim."""

    text = str(request or "").strip()
    tasks = []
    datasets = []

    def add(task: str, dataset: Optional[str] = None) -> None:
        if task not in tasks:
            tasks.append(task)
        if dataset and dataset not in datasets:
            datasets.append(dataset)

    if any(term in text for term in ("行政区", "边界", "区划")):
        add("admin_boundary", "admin_areas")
    if any(term in text for term in ("DEM", "dem", "高程", "地形")):
        add("elevation", "dem")
    if "坡度" in text:
        add("slope", "slope")
    if any(term in text for term in ("土地利用", "土地覆盖", "地类", "land use", "land_use")):
        add("land_use", "land_use")
    if any(term in text for term in ("道路", "路网", "主干道", "高速", "公路")):
        add("roads", "roads")
    if any(term in text for term in ("水体", "河流", "湖泊", "水系")):
        add("water", "water")
    if any(term in text for term in ("建设适宜性", "适宜建设", "适合建设", "可建设", "适合开发", "建设潜力", "建设候选", "建设用地", "建设筛选")):
        add("buildability")

    constraints: Dict[str, Any] = {}
    slope_match = _SLOPE_PATTERN.search(text)
    if slope_match:
        value = float(slope_match.group(1))
        if any(term in text[slope_match.start():slope_match.end()] for term in ("不超过", "不大于", "小于", "低于", "阈值为")):
            constraints["slope_max"] = value
        else:
            constraints["slope_value"] = value
    distance_match = _DISTANCE_PATTERN.search(text)
    if distance_match:
        constraints["road_distance_max"] = float(distance_match.group(1))
    if any(term in text for term in ("排除水体", "避开水体", "排除水域", "不含水体")):
        constraints["exclude_water"] = True

    evidence = []
    if any(term in text for term in ("边界", "地图", "空间预览", "几何", "区域")):
        evidence.append("geometry")
    if any(term in text for term in ("轨迹", "过程", "步骤", "依据", "证据")):
        evidence.append("trace")
    return RequestFacts(
        text=text,
        admin_name=_extract_admin_name(text),
        tasks=tuple(tasks),
        datasets=tuple(datasets),
        constraints=constraints,
        evidence=tuple(evidence),
    )


# Compatibility name retained for existing planner and capability adapters.
SpatialRequest = RequestFacts
