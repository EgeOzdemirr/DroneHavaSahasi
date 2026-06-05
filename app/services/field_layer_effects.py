from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FieldLayer
from app.domain.enums import FieldLayerType
from app.schemas.models import FieldLayerEffectResponse


FIELD_LAYER_EFFECTS: dict[FieldLayerType, tuple[str, str]] = {
    FieldLayerType.restricted_area: ("critical", "Kısıtlı bölge teması"),
    FieldLayerType.base_perimeter: ("high", "Üs çevresi ihlali"),
    FieldLayerType.patrol_area: ("medium", "Devriye bölgesi teması"),
    FieldLayerType.safe_corridor: ("info", "Güvenli koridor teması"),
    FieldLayerType.custom: ("info", "Özel saha katmanı teması"),
}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "info": 1}
_EPSILON = 1e-9


def list_active_field_layers(db: Session) -> list[FieldLayer]:
    return list(
        db.execute(
            select(FieldLayer)
            .where(FieldLayer.is_active.is_(True))
            .order_by(FieldLayer.created_at.desc(), FieldLayer.name.asc())
        )
        .scalars()
        .all()
    )


def build_field_layer_effects(
    field_layers: Iterable[FieldLayer],
    *,
    lat: float,
    lon: float,
) -> list[FieldLayerEffectResponse]:
    if not math.isfinite(lat) or not math.isfinite(lon):
        return []

    effects: list[FieldLayerEffectResponse] = []
    for layer in field_layers:
        if not layer.is_active or not point_in_geojson_polygon(layer.geometry, lat=lat, lon=lon):
            continue
        severity, label = FIELD_LAYER_EFFECTS.get(layer.layer_type, FIELD_LAYER_EFFECTS[FieldLayerType.custom])
        effects.append(
            FieldLayerEffectResponse(
                layer_id=layer.id,
                layer_name=layer.name,
                layer_type=layer.layer_type,
                severity=severity,
                label=label,
            )
        )

    return sorted(
        effects,
        key=lambda item: (-SEVERITY_RANK.get(item.severity, 0), item.layer_name.lower(), item.layer_id),
    )


def point_in_geojson_polygon(geometry: dict[str, Any], *, lat: float, lon: float) -> bool:
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        return False
    rings = geometry.get("coordinates")
    if not isinstance(rings, list) or not rings:
        return False

    exterior_relation = _ring_relation(rings[0], lat=lat, lon=lon)
    if exterior_relation == "boundary":
        return True
    if exterior_relation != "inside":
        return False

    for hole in rings[1:]:
        hole_relation = _ring_relation(hole, lat=lat, lon=lon)
        if hole_relation == "boundary":
            return True
        if hole_relation == "inside":
            return False
    return True


def _ring_relation(ring: Sequence[Any], *, lat: float, lon: float) -> str:
    points = [_coordinate_pair(point) for point in ring]
    points = [point for point in points if point is not None]
    if len(points) < 4:
        return "outside"

    inside = False
    previous_lon, previous_lat = points[-1]
    for current_lon, current_lat in points:
        if _point_on_segment(
            lon,
            lat,
            previous_lon,
            previous_lat,
            current_lon,
            current_lat,
        ):
            return "boundary"
        crosses_ray = (previous_lat > lat) != (current_lat > lat)
        if crosses_ray:
            intersect_lon = (current_lon - previous_lon) * (lat - previous_lat) / (current_lat - previous_lat) + previous_lon
            if lon < intersect_lon:
                inside = not inside
        previous_lon, previous_lat = current_lon, current_lat

    return "inside" if inside else "outside"


def _coordinate_pair(point: Any) -> tuple[float, float] | None:
    if not isinstance(point, list | tuple) or len(point) < 2:
        return None
    try:
        lon = float(point[0])
        lat = float(point[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    return lon, lat


def _point_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> bool:
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > _EPSILON:
        return False

    min_x, max_x = sorted((ax, bx))
    min_y, max_y = sorted((ay, by))
    return (min_x - _EPSILON <= px <= max_x + _EPSILON) and (min_y - _EPSILON <= py <= max_y + _EPSILON)
