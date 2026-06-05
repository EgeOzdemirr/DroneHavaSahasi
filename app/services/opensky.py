from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

import httpx

from app.config import get_settings
from app.schemas.models import OpenSkyAircraftResponse

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
TOKEN_REFRESH_MARGIN_SECONDS = 30


class OpenSkyConfigError(ValueError):
    """Raised when local OpenSky settings cannot be used safely."""


class OpenSkyUnavailableError(RuntimeError):
    """Raised when OpenSky cannot be reached or returns an unusable response."""


@dataclass
class _AircraftCache:
    key: tuple[str, tuple[float, float, float, float]]
    expires_at: float
    aircraft: list[OpenSkyAircraftResponse]


@dataclass
class _TokenCache:
    access_token: str
    expires_at: float


_aircraft_cache: _AircraftCache | None = None
_token_cache: _TokenCache | None = None


def clear_opensky_caches() -> None:
    global _aircraft_cache, _token_cache
    _aircraft_cache = None
    _token_cache = None


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in str(value or "").split(",")]
    if len(parts) != 4:
        raise OpenSkyConfigError("OPENSKY_BBOX must contain lamin,lomin,lamax,lomax.")

    try:
        lamin, lomin, lamax, lomax = (float(part) for part in parts)
    except ValueError as exc:
        raise OpenSkyConfigError("OPENSKY_BBOX values must be numeric.") from exc

    if not (-90 <= lamin <= 90 and -90 <= lamax <= 90):
        raise OpenSkyConfigError("OPENSKY_BBOX latitude values must be between -90 and 90.")
    if not (-180 <= lomin <= 180 and -180 <= lomax <= 180):
        raise OpenSkyConfigError("OPENSKY_BBOX longitude values must be between -180 and 180.")
    if lamin >= lamax or lomin >= lomax:
        raise OpenSkyConfigError("OPENSKY_BBOX lower bounds must be smaller than upper bounds.")
    return lamin, lomin, lamax, lomax


def normalize_state_vector(row: Any) -> OpenSkyAircraftResponse | None:
    if not isinstance(row, (list, tuple)):
        return None

    lon = _as_float(_row_value(row, 5))
    lat = _as_float(_row_value(row, 6))
    if lat is None or lon is None:
        return None

    icao24 = str(_row_value(row, 0) or "").strip().lower()
    if not icao24:
        return None

    callsign = _clean_text(_row_value(row, 1))
    origin_country = _clean_text(_row_value(row, 2))
    return OpenSkyAircraftResponse(
        icao24=icao24,
        callsign=callsign,
        origin_country=origin_country,
        lat=lat,
        lon=lon,
        baro_altitude_m=_as_float(_row_value(row, 7)),
        geo_altitude_m=_as_float(_row_value(row, 13)),
        velocity_mps=_as_float(_row_value(row, 9)),
        true_track_deg=_as_float(_row_value(row, 10)),
        vertical_rate_mps=_as_float(_row_value(row, 11)),
        on_ground=_as_bool(_row_value(row, 8)),
        last_contact=_unix_to_datetime(_as_int(_row_value(row, 4))),
        category=_as_int(_row_value(row, 17)),
    )


def fetch_opensky_aircraft(settings: object | None = None, client: httpx.Client | None = None) -> list[OpenSkyAircraftResponse]:
    settings = settings or get_settings()
    bbox = parse_bbox(str(getattr(settings, "opensky_bbox", "")))
    base_url = str(getattr(settings, "opensky_base_url", "")).rstrip("/")
    if not base_url:
        raise OpenSkyConfigError("OPENSKY_BASE_URL is required.")

    cache_key = (base_url, bbox)
    cached = _get_cached_aircraft(cache_key)
    if cached is not None:
        return cached

    owns_client = client is None
    http_client = client or httpx.Client(timeout=float(getattr(settings, "opensky_timeout_seconds", 6.0)))
    try:
        aircraft = _fetch_uncached(settings, http_client, base_url, bbox)
    finally:
        if owns_client:
            http_client.close()

    _set_cached_aircraft(settings, cache_key, aircraft)
    return aircraft


def _fetch_uncached(
    settings: object,
    client: httpx.Client,
    base_url: str,
    bbox: tuple[float, float, float, float],
) -> list[OpenSkyAircraftResponse]:
    headers = _auth_headers(settings, client)
    response = _request_states(client, base_url, bbox, headers)
    if response.status_code == 401 and headers:
        _clear_token_cache()
        response = _request_states(client, base_url, bbox, _auth_headers(settings, client))

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise OpenSkyUnavailableError(f"OpenSky returned {exc.response.status_code}.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenSkyUnavailableError("OpenSky returned invalid JSON.") from exc

    states = payload.get("states") if isinstance(payload, dict) else None
    if not states:
        return []
    aircraft: list[OpenSkyAircraftResponse] = []
    for row in states:
        normalized = normalize_state_vector(row)
        if normalized is not None:
            aircraft.append(normalized)
    return aircraft


def _request_states(
    client: httpx.Client,
    base_url: str,
    bbox: tuple[float, float, float, float],
    headers: dict[str, str],
) -> httpx.Response:
    lamin, lomin, lamax, lomax = bbox
    try:
        return client.get(
            f"{base_url}/states/all",
            params={
                "lamin": lamin,
                "lomin": lomin,
                "lamax": lamax,
                "lomax": lomax,
                "extended": 1,
            },
            headers=headers,
        )
    except httpx.HTTPError as exc:
        raise OpenSkyUnavailableError("OpenSky request failed.") from exc


def _auth_headers(settings: object, client: httpx.Client) -> dict[str, str]:
    client_id = str(getattr(settings, "opensky_client_id", "") or "").strip()
    client_secret = str(getattr(settings, "opensky_client_secret", "") or "").strip()
    if not client_id and not client_secret:
        return {}
    if not client_id or not client_secret:
        raise OpenSkyConfigError("OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET must be set together.")
    return {"Authorization": f"Bearer {_get_access_token(client, client_id, client_secret)}"}


def _get_access_token(client: httpx.Client, client_id: str, client_secret: str) -> str:
    if _token_cache is not None and _token_cache.expires_at > time.monotonic():
        return _token_cache.access_token

    try:
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OpenSkyUnavailableError("OpenSky authentication failed.") from exc

    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise OpenSkyUnavailableError("OpenSky authentication did not return a token.")

    expires_in = _as_int(payload.get("expires_in")) or 1800
    expires_at = time.monotonic() + max(1, expires_in - TOKEN_REFRESH_MARGIN_SECONDS)
    _set_token_cache(access_token, expires_at)
    return access_token


def _get_cached_aircraft(
    cache_key: tuple[str, tuple[float, float, float, float]],
) -> list[OpenSkyAircraftResponse] | None:
    if _aircraft_cache is None:
        return None
    if _aircraft_cache.key != cache_key or _aircraft_cache.expires_at <= time.monotonic():
        return None
    return list(_aircraft_cache.aircraft)


def _set_cached_aircraft(
    settings: object,
    cache_key: tuple[str, tuple[float, float, float, float]],
    aircraft: list[OpenSkyAircraftResponse],
) -> None:
    global _aircraft_cache
    ttl_seconds = int(getattr(settings, "opensky_cache_ttl_seconds", 30))
    if ttl_seconds <= 0:
        _aircraft_cache = None
        return
    _aircraft_cache = _AircraftCache(
        key=cache_key,
        expires_at=time.monotonic() + ttl_seconds,
        aircraft=list(aircraft),
    )


def _set_token_cache(access_token: str, expires_at: float) -> None:
    global _token_cache
    _token_cache = _TokenCache(access_token=access_token, expires_at=expires_at)


def _clear_token_cache() -> None:
    global _token_cache
    _token_cache = None


def _row_value(row: list[Any] | tuple[Any, ...], index: int) -> Any:
    return row[index] if len(row) > index else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _unix_to_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)
