from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import ValidationError

from app.schemas.models import TelemetryPayload
from bridge.config import BridgeSettings, get_bridge_settings
from bridge.forwarder import forward_to_api
from bridge.queue import BridgeQueue
from bridge.schemas import BridgeHealthResponse, BridgeStatsResponse, RetryEnvelope
from bridge.security import BRIDGE_TOKEN_HEADER, extract_forward_headers, token_valid
from bridge.worker import RetryWorker


class BridgeRuntime:
    def __init__(self, settings: BridgeSettings) -> None:
        self.settings = settings
        self.queue = BridgeQueue(settings)
        self.client = httpx.AsyncClient()
        self.worker: RetryWorker | None = None

    async def start(self) -> None:
        if self.queue.connected:
            self.worker = RetryWorker(
                settings=self.settings,
                queue=self.queue,
                client=self.client,
            )
            self.worker.start()

    async def stop(self) -> None:
        if self.worker:
            await self.worker.stop()
        await self.client.aclose()


settings = get_bridge_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = BridgeRuntime(settings)
    app.state.runtime = runtime
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.post("/bridge/v1/telemetry/ingest")
async def bridge_ingest(request: Request):
    runtime: BridgeRuntime = request.app.state.runtime
    headers = {key.lower(): value for key, value in request.headers.items()}

    if not token_valid(headers.get(BRIDGE_TOKEN_HEADER), runtime.settings.bridge_source_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bridge token")

    forward_headers, missing_headers = extract_forward_headers(headers)
    if missing_headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Missing required telemetry headers", "missing_headers": missing_headers},
        )

    raw_body = await request.body()
    try:
        TelemetryPayload.model_validate_json(raw_body)
    except ValidationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid telemetry payload")

    result = await forward_to_api(
        client=runtime.client,
        ingest_url=runtime.settings.bridge_api_ingest_url,
        headers=forward_headers,
        raw_body=raw_body,
        timeout_seconds=runtime.settings.bridge_forward_timeout_seconds,
    )

    if result.retryable:
        envelope = RetryEnvelope.from_payload(
            headers=forward_headers,
            body=raw_body,
            attempts=0,
            last_error=result.error_reason,
        )
        enqueued = await asyncio.to_thread(runtime.queue.enqueue, envelope)
        if enqueued:
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={"queued": True, "detail": "upstream_unavailable"},
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upstream unavailable and queue is full or unreachable",
        )

    status_code = result.status_code or status.HTTP_502_BAD_GATEWAY
    if result.json_body is not None:
        return JSONResponse(status_code=status_code, content=result.json_body)
    if result.text_body is not None:
        return PlainTextResponse(status_code=status_code, content=result.text_body)
    return JSONResponse(status_code=status_code, content={})


@app.get("/bridge/v1/health", response_model=BridgeHealthResponse)
async def bridge_health(request: Request) -> BridgeHealthResponse:
    runtime: BridgeRuntime = request.app.state.runtime
    return BridgeHealthResponse(
        status="ok",
        queue_connected=runtime.queue.connected,
        worker_running=bool(runtime.worker and runtime.worker.running),
    )


@app.get("/bridge/v1/stats", response_model=BridgeStatsResponse)
async def bridge_stats(request: Request) -> BridgeStatsResponse:
    runtime: BridgeRuntime = request.app.state.runtime
    snapshot = await asyncio.to_thread(runtime.queue.snapshot)
    return BridgeStatsResponse(
        queue_len=snapshot.queue_len,
        dlq_len=snapshot.dlq_len,
        last_error_at=runtime.worker.last_error_at if runtime.worker else None,
        last_error_reason=runtime.worker.last_error_reason if runtime.worker else None,
        worker_running=bool(runtime.worker and runtime.worker.running),
    )

