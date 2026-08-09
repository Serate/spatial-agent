"""Validated, transport-friendly spatial comparison scenarios."""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple


@dataclass(frozen=True)
class BuildabilityComparisonScenario:
    """One normalized scenario shared by threshold and region comparisons."""

    admin_names: Tuple[str, ...]
    thresholds: Tuple[float, ...]
    operation: str = "buildability_comparison"

    @classmethod
    def for_thresholds(cls, admin_name: str, thresholds: Iterable[Any]):
        name = _clean_name(admin_name)
        values = _clean_thresholds(thresholds)
        return cls((name,), values)

    @classmethod
    def for_regions(cls, admin_names: Iterable[Any], threshold: Any):
        names = []
        for value in admin_names if isinstance(admin_names, (list, tuple)) else ():
            name = _clean_name(value)
            if name not in names:
                names.append(name)
        if not 2 <= len(names) <= 6:
            raise ValueError("admin_names must contain 2 to 6 values")
        values = _clean_thresholds([threshold])
        return cls(tuple(names), values)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "admin_names": list(self.admin_names),
            "thresholds": list(self.thresholds),
        }


def _clean_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("admin_name must be a non-empty string")
    return value.strip()[:80]


def _clean_thresholds(values: Iterable[Any]) -> Tuple[float, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("thresholds must contain 1 to 6 values")
    if not 1 <= len(values) <= 6:
        raise ValueError("thresholds must contain 1 to 6 values")
    normalized = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("slope thresholds must be numbers") from exc
        if not 1 <= number <= 45:
            raise ValueError("slope thresholds must be between 1 and 45 degrees")
        if number not in normalized:
            normalized.append(number)
    return tuple(normalized)
