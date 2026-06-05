from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RetryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headers: dict[str, str]
    body_b64: str
    attempts: int = 0
    queued_at: datetime = Field(default_factory=utc_now)
    last_error: str | None = None

    @classmethod
    def from_payload(cls, *, headers: dict[str, str], body: bytes, attempts: int = 0, last_error: str | None = None) -> "RetryEnvelope":
        return cls(
            headers=headers,
            body_b64=base64.b64encode(body).decode("ascii"),
            attempts=attempts,
            last_error=last_error,
        )

    def body_bytes(self) -> bytes:
        return base64.b64decode(self.body_b64.encode("ascii"))


class ForwardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_code: int | None = None
    json_body: Any | None = None
    text_body: str | None = None
    retryable: bool = False
    error_reason: str | None = None


class BridgeHealthResponse(BaseModel):
    status: str
    queue_connected: bool
    worker_running: bool


class BridgeStatsResponse(BaseModel):
    queue_len: int
    dlq_len: int
    last_error_at: datetime | None
    last_error_reason: str | None
    worker_running: bool

