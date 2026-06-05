from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from bridge.config import BridgeSettings
from bridge.forwarder import forward_to_api
from bridge.queue import BridgeQueue
from bridge.schemas import RetryEnvelope


class RetryWorker:
    def __init__(
        self,
        *,
        settings: BridgeSettings,
        queue: BridgeQueue,
        client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._client = client
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.last_error_at: datetime | None = None
        self.last_error_reason: str | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            envelope = await asyncio.to_thread(self._queue.dequeue, 1)
            if not envelope:
                continue
            await self._process_one(envelope)

    async def _process_one(self, envelope: RetryEnvelope) -> None:
        result = await forward_to_api(
            client=self._client,
            ingest_url=self._settings.bridge_api_ingest_url,
            headers=envelope.headers,
            raw_body=envelope.body_bytes(),
            timeout_seconds=self._settings.bridge_forward_timeout_seconds,
        )
        if not result.retryable:
            return

        envelope.attempts += 1
        envelope.last_error = result.error_reason
        self.last_error_at = datetime.now(timezone.utc)
        self.last_error_reason = result.error_reason

        if envelope.attempts >= self._settings.bridge_retry_max_attempts:
            await asyncio.to_thread(self._queue.push_dlq, envelope)
            return

        await asyncio.sleep(self._settings.bridge_retry_backoff_seconds)
        await asyncio.to_thread(self._queue.enqueue, envelope)

