from app.db.models import FieldLayer
from app.domain.enums import FieldLayerType
from app.services.field_layer_effects import build_field_layer_effects, point_in_geojson_polygon


def _polygon() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [29.0, 41.0],
                [29.2, 41.0],
                [29.2, 41.2],
                [29.0, 41.2],
                [29.0, 41.0],
            ]
        ],
    }


def _layer(layer_id: str, layer_type: FieldLayerType, *, active: bool = True) -> FieldLayer:
    return FieldLayer(
        id=layer_id,
        name=f"Layer {layer_id}",
        layer_type=layer_type,
        geometry=_polygon(),
        style={},
        is_active=active,
    )


def test_point_in_geojson_polygon_counts_inside_and_boundary_only() -> None:
    geometry = _polygon()

    assert point_in_geojson_polygon(geometry, lat=41.1, lon=29.1) is True
    assert point_in_geojson_polygon(geometry, lat=41.0, lon=29.1) is True
    assert point_in_geojson_polygon(geometry, lat=41.3, lon=29.1) is False


def test_build_field_layer_effects_orders_multiple_active_layers_and_skips_inactive() -> None:
    effects = build_field_layer_effects(
        [
            _layer("patrol", FieldLayerType.patrol_area),
            _layer("restricted", FieldLayerType.restricted_area),
            _layer("inactive", FieldLayerType.base_perimeter, active=False),
        ],
        lat=41.1,
        lon=29.1,
    )

    assert [item.layer_type for item in effects] == [FieldLayerType.restricted_area, FieldLayerType.patrol_area]
    assert effects[0].severity == "critical"
    assert effects[0].label == "Kısıtlı bölge teması"
