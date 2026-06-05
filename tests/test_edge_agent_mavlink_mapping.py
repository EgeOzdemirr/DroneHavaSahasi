from types import SimpleNamespace

from edge_agent.mavlink_input import map_global_position_int


def test_map_global_position_int_uses_relative_alt_and_speed():
    msg = SimpleNamespace(
        lat=410123456,
        lon=290654321,
        relative_alt=123450,
        alt=200000,
        vx=300,
        vy=400,
        hdg=9000,
    )
    payload, heading = map_global_position_int(msg, 0.0)
    assert round(payload["lat"], 7) == 41.0123456
    assert round(payload["lon"], 7) == 29.0654321
    assert payload["alt_m"] == 123.45
    assert payload["speed_mps"] == 5.0
    assert payload["heading_deg"] == 90.0
    assert heading == 90.0


def test_map_global_position_int_heading_fallback_when_unknown():
    msg = SimpleNamespace(
        lat=410000000,
        lon=290000000,
        relative_alt=100000,
        vx=0,
        vy=0,
        hdg=65535,
    )
    payload, heading = map_global_position_int(msg, 123.4)
    assert payload["heading_deg"] == 123.4
    assert heading == 123.4


def test_map_global_position_int_wraps_360_to_0():
    msg = SimpleNamespace(
        lat=410000000,
        lon=290000000,
        relative_alt=100000,
        vx=0,
        vy=0,
        hdg=36000,
    )
    payload, heading = map_global_position_int(msg, 10.0)
    assert payload["heading_deg"] == 0.0
    assert heading == 0.0
