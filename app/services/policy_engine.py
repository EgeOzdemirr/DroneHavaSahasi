from __future__ import annotations

import json
from typing import Any


def _to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise ValueError("value is not numeric")


def _check_altitude(policy: dict[str, Any], alt_m: float) -> bool:
    min_alt = policy.get("min_alt_m")
    max_alt = policy.get("max_alt_m")
    if min_alt is not None and alt_m < _to_float(min_alt):
        return False
    if max_alt is not None and alt_m > _to_float(max_alt):
        return False
    return True


def _point_in_polygon(lat: float, lon: float, polygon: list[list[float]]) -> bool:
    inside = False
    n = len(polygon)
    if n < 3:
        return False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]  # lon, lat
        xj, yj = polygon[j][0], polygon[j][1]  # lon, lat
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def evaluate_policy_area(area_geom: str | None, *, lat: float, lon: float, alt_m: float) -> bool:
    if not area_geom:
        return True

    try:
        policy = json.loads(area_geom)
        if not isinstance(policy, dict):
            return False
    except json.JSONDecodeError:
        return False

    policy_type = str(policy.get("type", "")).lower()
    if policy_type == "bbox":
        try:
            min_lat = _to_float(policy["min_lat"])
            max_lat = _to_float(policy["max_lat"])
            min_lon = _to_float(policy["min_lon"])
            max_lon = _to_float(policy["max_lon"])
        except (KeyError, ValueError):
            return False
        in_zone = min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
        if not in_zone:
            return False
        try:
            return _check_altitude(policy, alt_m)
        except ValueError:
            return False

    if policy_type == "polygon":
        raw_coordinates = policy.get("coordinates")
        if not isinstance(raw_coordinates, list):
            return False
        polygon: list[list[float]] = []
        try:
            for point in raw_coordinates:
                if not isinstance(point, list) or len(point) < 2:
                    return False
                polygon.append([_to_float(point[0]), _to_float(point[1])])
        except ValueError:
            return False
        if not _point_in_polygon(lat, lon, polygon):
            return False
        try:
            return _check_altitude(policy, alt_m)
        except ValueError:
            return False

    return False

