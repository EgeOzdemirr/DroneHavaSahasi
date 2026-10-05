from __future__ import annotations

import time

# Son gercek HTTP isteginin zamani (monotonic). Uyanik tutma ping'leri (/healthz)
# burayi guncellemez; boylece kimse kullanmazken arka plan bakim dongusu
# veritabanini sorgulamayi birakir ve sunucusuz Postgres (Neon) uyuyabilir.
_last_activity: float = time.monotonic()


def mark_activity() -> None:
    global _last_activity
    _last_activity = time.monotonic()


def seconds_since_activity() -> float:
    return time.monotonic() - _last_activity


def is_idle(idle_after_seconds: int) -> bool:
    """0 veya negatif esik bosta kalmayi kapatir (saha varsayilani)."""
    if idle_after_seconds <= 0:
        return False
    return seconds_since_activity() >= idle_after_seconds
