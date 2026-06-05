import asyncio

import httpx

from bridge.forwarder import forward_to_api


def test_forward_success_json_passthrough() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Drone-Uid"] == "DRN-001"
        assert request.headers["X-Device-Id"] == "JETSON-001"
        return httpx.Response(status_code=202, json={"drone_uid": "DRN-001", "platform_role": "recon", "reason": "ok"})

    transport = httpx.MockTransport(handler)

    async def run_case():
        async with httpx.AsyncClient(transport=transport) as client:
            result = await forward_to_api(
                client=client,
                ingest_url="http://api/v1/telemetry/ingest",
                headers={"X-Drone-Uid": "DRN-001", "X-Device-Id": "JETSON-001"},
                raw_body=b'{"lat":1}',
                timeout_seconds=2.0,
            )
            assert result.status_code == 202
            assert result.json_body == {"drone_uid": "DRN-001", "platform_role": "recon", "reason": "ok"}
            assert not result.retryable

    asyncio.run(run_case())


def test_forward_4xx_not_retryable() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=400, json={"detail": "bad request"})

    transport = httpx.MockTransport(handler)

    async def run_case():
        async with httpx.AsyncClient(transport=transport) as client:
            result = await forward_to_api(
                client=client,
                ingest_url="http://api/v1/telemetry/ingest",
                headers={},
                raw_body=b"{}",
                timeout_seconds=2.0,
            )
            assert result.status_code == 400
            assert result.json_body == {"detail": "bad request"}
            assert not result.retryable

    asyncio.run(run_case())


def test_forward_5xx_retryable() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": "unavailable"})

    transport = httpx.MockTransport(handler)

    async def run_case():
        async with httpx.AsyncClient(transport=transport) as client:
            result = await forward_to_api(
                client=client,
                ingest_url="http://api/v1/telemetry/ingest",
                headers={},
                raw_body=b"{}",
                timeout_seconds=2.0,
            )
            assert result.status_code == 503
            assert result.retryable
            assert result.error_reason == "upstream_503"

    asyncio.run(run_case())


def test_forward_network_error_retryable() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect failed")

    transport = httpx.MockTransport(handler)

    async def run_case():
        async with httpx.AsyncClient(transport=transport) as client:
            result = await forward_to_api(
                client=client,
                ingest_url="http://api/v1/telemetry/ingest",
                headers={},
                raw_body=b"{}",
                timeout_seconds=2.0,
            )
            assert result.retryable
            assert result.error_reason == "ConnectError"
            assert result.status_code is None

    asyncio.run(run_case())
