import asyncio

import httpx
import pytest

from bridge.config import BridgeSettings
from bridge.schemas import ForwardResult, RetryEnvelope
from bridge.worker import RetryWorker
import bridge.worker as worker_module


class _FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[RetryEnvelope] = []
        self.dlq: list[RetryEnvelope] = []

    def enqueue(self, envelope: RetryEnvelope) -> bool:
        self.enqueued.append(envelope)
        return True

    def push_dlq(self, envelope: RetryEnvelope) -> bool:
        self.dlq.append(envelope)
        return True


def _settings(max_attempts: int) -> BridgeSettings:
    return BridgeSettings(
        _env_file=None,
        ENVIRONMENT="dev",
        BRIDGE_SOURCE_TOKEN="bridge-token-abcdefghijklmnopqrstuvwxyz",
        BRIDGE_API_INGEST_URL="http://api/v1/telemetry/ingest",
        BRIDGE_RETRY_MAX_ATTEMPTS=max_attempts,
        BRIDGE_RETRY_BACKOFF_SECONDS=0,
    )


def test_retry_worker_requeues_on_retryable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_forward(**_kwargs):
        return ForwardResult(retryable=True, error_reason="upstream_503")

    async def fake_sleep(_seconds: float):
        return None

    monkeypatch.setattr(worker_module, "forward_to_api", fake_forward)
    monkeypatch.setattr(worker_module.asyncio, "sleep", fake_sleep)

    async def run_case():
        queue = _FakeQueue()
        async with httpx.AsyncClient() as client:
            worker = RetryWorker(settings=_settings(max_attempts=3), queue=queue, client=client)
            envelope = RetryEnvelope.from_payload(headers={"X-Drone-Uid": "DRN-001"}, body=b"{}")
            await worker._process_one(envelope)

        assert len(queue.enqueued) == 1
        assert len(queue.dlq) == 0
        assert queue.enqueued[0].attempts == 1
        assert queue.enqueued[0].last_error == "upstream_503"

    asyncio.run(run_case())


def test_retry_worker_moves_to_dlq_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_forward(**_kwargs):
        return ForwardResult(retryable=True, error_reason="upstream_503")

    monkeypatch.setattr(worker_module, "forward_to_api", fake_forward)

    async def run_case():
        queue = _FakeQueue()
        async with httpx.AsyncClient() as client:
            worker = RetryWorker(settings=_settings(max_attempts=1), queue=queue, client=client)
            envelope = RetryEnvelope.from_payload(headers={"X-Drone-Uid": "DRN-001"}, body=b"{}")
            await worker._process_one(envelope)

        assert len(queue.enqueued) == 0
        assert len(queue.dlq) == 1
        assert queue.dlq[0].attempts == 1

    asyncio.run(run_case())


def test_retry_worker_ignores_non_retryable_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_forward(**_kwargs):
        return ForwardResult(status_code=400, json_body={"detail": "bad request"}, retryable=False)

    monkeypatch.setattr(worker_module, "forward_to_api", fake_forward)

    async def run_case():
        queue = _FakeQueue()
        async with httpx.AsyncClient() as client:
            worker = RetryWorker(settings=_settings(max_attempts=2), queue=queue, client=client)
            envelope = RetryEnvelope.from_payload(headers={"X-Drone-Uid": "DRN-001"}, body=b"{}")
            await worker._process_one(envelope)

        assert len(queue.enqueued) == 0
        assert len(queue.dlq) == 0

    asyncio.run(run_case())
