from types import SimpleNamespace

import httpx
import pytest

from app.services.opensky import (
    OpenSkyConfigError,
    clear_opensky_caches,
    fetch_opensky_aircraft,
    parse_bbox,
)


def _settings(**overrides):
    values = {
        "opensky_bbox": "34.0,18.0,45.5,45.5",
        "opensky_base_url": "https://opensky-network.org/api",
        "opensky_cache_ttl_seconds": 30,
        "opensky_timeout_seconds": 6.0,
        "opensky_client_id": "",
        "opensky_client_secret": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_opensky_normalizes_state_vectors_and_filters_missing_position() -> None:
    clear_opensky_caches()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states/all"
        assert request.url.params["lamin"] == "34.0"
        assert request.url.params["lomin"] == "18.0"
        assert request.url.params["lamax"] == "45.5"
        assert request.url.params["lomax"] == "45.5"
        assert request.url.params["extended"] == "1"
        return httpx.Response(
            200,
            json={
                "time": 1710000000,
                "states": [
                    [
                        "4baa01",
                        "THY123  ",
                        "Turkey",
                        1710000001,
                        1710000002,
                        29.302,
                        40.883,
                        3400.5,
                        False,
                        215.3,
                        92.0,
                        -1.2,
                        None,
                        3450.0,
                        "7000",
                        False,
                        0,
                        3,
                    ],
                    ["missing-position", None, "Turkey", None, None, None, None],
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        aircraft = fetch_opensky_aircraft(_settings(), client=client)

    assert len(aircraft) == 1
    assert aircraft[0].icao24 == "4baa01"
    assert aircraft[0].callsign == "THY123"
    assert aircraft[0].origin_country == "Turkey"
    assert aircraft[0].lat == 40.883
    assert aircraft[0].lon == 29.302
    assert aircraft[0].baro_altitude_m == 3400.5
    assert aircraft[0].geo_altitude_m == 3450.0
    assert aircraft[0].velocity_mps == 215.3
    assert aircraft[0].true_track_deg == 92.0
    assert aircraft[0].vertical_rate_mps == -1.2
    assert aircraft[0].on_ground is False
    assert aircraft[0].category == 3


def test_opensky_cache_prevents_repeated_external_calls_before_ttl() -> None:
    clear_opensky_caches()
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"states": [["4baa02", "PGT45", "Turkey", None, 1710000002, 29.1, 40.9]]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = fetch_opensky_aircraft(_settings(opensky_cache_ttl_seconds=60), client=client)
        second = fetch_opensky_aircraft(_settings(opensky_cache_ttl_seconds=60), client=client)

    assert call_count == 1
    assert first[0].icao24 == second[0].icao24 == "4baa02"


def test_parse_bbox_rejects_invalid_values() -> None:
    with pytest.raises(OpenSkyConfigError):
        parse_bbox("40.45,28.35,41.35")
    with pytest.raises(OpenSkyConfigError):
        parse_bbox("41.35,28.35,40.45,30.35")
