from __future__ import annotations

import threading
import time

import redis

from app.config import get_settings


class LoginRateLimiter:
    """Istemci basina basarisiz giris denemelerini sayan hiz siniri.

    nonce_store ile ayni desen: Redis varsa onu kullanir, yoksa surec-ici bellege
    duser. Bellek modu tek surec icinde calisir; birden fazla worker calistirilirsa
    Redis onerilir. Anahtar istemci tanimlayicisidir (genelde IP adresi).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.max_attempts = settings.login_max_attempts
        self.window_seconds = settings.login_window_seconds
        self._lock = threading.Lock()
        self._memory: dict[str, list[float]] = {}
        self._redis: redis.Redis | None = None
        try:
            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._redis = client
        except redis.RedisError:
            self._redis = None

    @staticmethod
    def _key(identifier: str) -> str:
        return f"login_fail:{identifier}"

    def _memory_count(self, key: str, *, now: float) -> int:
        timestamps = [t for t in self._memory.get(key, []) if now - t < self.window_seconds]
        self._memory[key] = timestamps
        return len(timestamps)

    def is_blocked(self, identifier: str) -> bool:
        key = self._key(identifier)
        if self._redis:
            try:
                value = self._redis.get(key)
                return int(value) >= self.max_attempts if value else False
            except (redis.RedisError, ValueError):
                pass
        now = time.monotonic()
        with self._lock:
            return self._memory_count(key, now=now) >= self.max_attempts

    def register_failure(self, identifier: str) -> None:
        key = self._key(identifier)
        if self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, self.window_seconds)
                pipe.execute()
                return
            except redis.RedisError:
                pass
        now = time.monotonic()
        with self._lock:
            timestamps = [t for t in self._memory.get(key, []) if now - t < self.window_seconds]
            timestamps.append(now)
            self._memory[key] = timestamps

    def reset(self, identifier: str) -> None:
        key = self._key(identifier)
        if self._redis:
            try:
                self._redis.delete(key)
                return
            except redis.RedisError:
                pass
        with self._lock:
            self._memory.pop(key, None)


login_rate_limiter = LoginRateLimiter()


def client_identifier(request) -> str:
    """Ters proxy arkasinda gercek istemci IP'sini belirler.

    Uvicorn --proxy-headers ile request.client.host zaten iletilen IP'yi tasir;
    yine de X-Forwarded-For varsa ilk (orijinal istemci) degeri onceliklidir.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
