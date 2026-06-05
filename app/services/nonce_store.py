from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import redis

from app.config import get_settings


class NonceStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.ttl_seconds = settings.nonce_ttl_seconds
        self._memory: dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._redis: redis.Redis | None = None
        try:
            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._redis = client
        except redis.RedisError:
            self._redis = None

    def register_once(self, drone_uid: str, nonce: str) -> bool:
        key = f"nonce:{drone_uid}:{nonce}"
        if self._redis:
            try:
                result = self._redis.set(key, "1", nx=True, ex=self.ttl_seconds)
                return bool(result)
            except redis.RedisError:
                # Redis temporary outage: degrade to local memory.
                pass

        now = datetime.now(timezone.utc)
        expire_cutoff = now - timedelta(seconds=self.ttl_seconds)
        with self._lock:
            stale = [k for k, ts in self._memory.items() if ts < expire_cutoff]
            for item in stale:
                self._memory.pop(item, None)
            if key in self._memory:
                return False
            self._memory[key] = now
            return True

