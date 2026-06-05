from __future__ import annotations

import json
from dataclasses import dataclass

import redis

from bridge.config import BridgeSettings
from bridge.schemas import RetryEnvelope


@dataclass(slots=True)
class QueueSnapshot:
    queue_len: int
    dlq_len: int


class BridgeQueue:
    def __init__(self, settings: BridgeSettings) -> None:
        self._settings = settings
        self._client: redis.Redis | None = None
        try:
            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._client = client
        except redis.RedisError:
            self._client = None

    @property
    def connected(self) -> bool:
        return self._client is not None

    def enqueue(self, envelope: RetryEnvelope) -> bool:
        if not self._client:
            return False
        try:
            current_len = int(self._client.llen(self._settings.bridge_queue_key))
            if current_len >= self._settings.bridge_queue_max:
                return False
            self._client.rpush(self._settings.bridge_queue_key, envelope.model_dump_json())
            return True
        except redis.RedisError:
            return False

    def dequeue(self, timeout_seconds: int = 1) -> RetryEnvelope | None:
        if not self._client:
            return None
        try:
            item = self._client.blpop(self._settings.bridge_queue_key, timeout=timeout_seconds)
            if not item:
                return None
            _, payload = item
            return RetryEnvelope.model_validate_json(payload)
        except (redis.RedisError, json.JSONDecodeError, ValueError):
            return None

    def push_dlq(self, envelope: RetryEnvelope) -> bool:
        if not self._client:
            return False
        try:
            self._client.rpush(self._settings.bridge_dlq_key, envelope.model_dump_json())
            return True
        except redis.RedisError:
            return False

    def snapshot(self) -> QueueSnapshot:
        if not self._client:
            return QueueSnapshot(queue_len=0, dlq_len=0)
        try:
            return QueueSnapshot(
                queue_len=int(self._client.llen(self._settings.bridge_queue_key)),
                dlq_len=int(self._client.llen(self._settings.bridge_dlq_key)),
            )
        except redis.RedisError:
            return QueueSnapshot(queue_len=0, dlq_len=0)

