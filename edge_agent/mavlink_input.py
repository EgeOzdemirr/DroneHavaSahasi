from __future__ import annotations

import math
from collections.abc import Generator
from typing import Any


def map_global_position_int(msg: Any, last_heading_deg: float) -> tuple[dict[str, float], float]:
    hdg_raw = getattr(msg, "hdg", 65535)
    if hdg_raw in (None, 65535):
        heading_deg = float(last_heading_deg)
    else:
        heading_deg = float(hdg_raw) / 100.0
        if heading_deg >= 360.0:
            heading_deg = heading_deg % 360.0

    relative_alt_mm = getattr(msg, "relative_alt", None)
    if relative_alt_mm is None:
        relative_alt_mm = getattr(msg, "alt", 0)

    vx = float(getattr(msg, "vx", 0.0))
    vy = float(getattr(msg, "vy", 0.0))
    speed_mps = math.sqrt((vx * vx) + (vy * vy)) / 100.0

    payload = {
        "lat": float(getattr(msg, "lat")) / 1e7,
        "lon": float(getattr(msg, "lon")) / 1e7,
        "alt_m": float(relative_alt_mm) / 1000.0,
        "speed_mps": speed_mps,
        "heading_deg": heading_deg,
    }
    return payload, heading_deg


def telemetry_stream_mavlink(device: str, baud: int) -> Generator[dict[str, float], None, None]:
    try:
        from pymavlink import mavutil  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency presence tested in runtime
        raise RuntimeError("pymavlink not installed. Install requirements including pymavlink.") from exc

    conn = mavutil.mavlink_connection(device, baud=baud, autoreconnect=True)
    last_heading_deg = 0.0
    print(f"[INFO] MAVLink listener active on {device} @ {baud}", flush=True)
    try:
        while True:
            msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
            if msg is None:
                continue
            payload, last_heading_deg = map_global_position_int(msg, last_heading_deg)
            yield payload
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
