from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.alerts import raise_link_lost_alerts
from app.services.retention import purge_old_telemetry

settings = get_settings()


async def _safe_call(sync_fn) -> None:
    try:
        await asyncio.to_thread(sync_fn)
    except Exception:
        # Background maintenance must never crash API process.
        return


def _link_lost_tick() -> None:
    with SessionLocal() as db:
        raise_link_lost_alerts(db, settings.link_lost_seconds)
        db.commit()


def _retention_tick() -> None:
    with SessionLocal() as db:
        purge_old_telemetry(db, settings.retention_days)
        db.commit()


async def background_maintenance(stop_event: asyncio.Event) -> None:
    retention_every_seconds = 3600
    link_lost_every_seconds = 5
    next_retention = datetime.now(timezone.utc).timestamp() + retention_every_seconds

    while not stop_event.is_set():
        await _safe_call(_link_lost_tick)

        now_ts = datetime.now(timezone.utc).timestamp()
        if now_ts >= next_retention:
            await _safe_call(_retention_tick)
            next_retention = now_ts + retention_every_seconds

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=link_lost_every_seconds)
        except asyncio.TimeoutError:
            continue

