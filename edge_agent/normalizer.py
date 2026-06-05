from __future__ import annotations

from typing import Any, Mapping


def _pick(raw: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return default


def normalize_payload(raw: Mapping[str, Any], *, seq_fallback: int, default_source: str) -> dict[str, Any]:
    lat = _pick(raw, "lat")
    lon = _pick(raw, "lon")
    if lat is None or lon is None:
        raise ValueError("payload must contain lat/lon")

    return {
        "lat": float(lat),
        "lon": float(lon),
        "alt_m": float(_pick(raw, "alt_m", "alt", default=0.0)),
        "speed_mps": float(_pick(raw, "speed_mps", "speed", default=0.0)),
        "heading_deg": float(_pick(raw, "heading_deg", "heading", default=0.0)),
        "seq": int(_pick(raw, "seq", default=seq_fallback)),
        "source": str(_pick(raw, "source", default=default_source)),
    }

