from __future__ import annotations

import httpx

from bridge.schemas import ForwardResult


async def forward_to_api(
    *,
    client: httpx.AsyncClient,
    ingest_url: str,
    headers: dict[str, str],
    raw_body: bytes,
    timeout_seconds: float,
) -> ForwardResult:
    try:
        response = await client.post(
            ingest_url,
            headers=headers,
            content=raw_body,
            timeout=timeout_seconds,
        )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        return ForwardResult(
            retryable=True,
            error_reason=f"{exc.__class__.__name__}",
        )
    except httpx.HTTPError as exc:
        return ForwardResult(
            retryable=True,
            error_reason=f"{exc.__class__.__name__}",
        )

    json_body = None
    text_body = None
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        try:
            json_body = response.json()
        except ValueError:
            json_body = None
    else:
        text_body = response.text

    return ForwardResult(
        status_code=response.status_code,
        json_body=json_body,
        text_body=text_body,
        retryable=response.status_code >= 500,
        error_reason=f"upstream_{response.status_code}" if response.status_code >= 500 else None,
    )

