from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    retryable: bool
    status_code: int | None
    error_reason: str
    response_json: dict[str, Any] | None


class TelemetrySender:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        tls_ca_file: str | None = None,
        tls_client_cert_file: str | None = None,
        tls_client_key_file: str | None = None,
        tls_insecure_skip_verify: bool = False,
    ) -> None:
        verify: bool | str = False if tls_insecure_skip_verify else (tls_ca_file or True)
        cert: tuple[str, str] | None = None
        if tls_client_cert_file and tls_client_key_file:
            cert = (tls_client_cert_file, tls_client_key_file)
        self._client = httpx.Client(timeout=timeout_seconds, verify=verify, cert=cert)

    def close(self) -> None:
        self._client.close()

    def send(self, *, ingest_url: str, headers: dict[str, str], raw_body: bytes) -> DeliveryResult:
        try:
            response = self._client.post(ingest_url, headers=headers, content=raw_body)
        except httpx.HTTPError as exc:
            return DeliveryResult(
                delivered=False,
                retryable=True,
                status_code=None,
                error_reason=f"{exc.__class__.__name__}",
                response_json=None,
            )

        content_type = response.headers.get("content-type", "").lower()
        payload: dict[str, Any] | None = None
        if "application/json" in content_type:
            try:
                data = response.json()
                if isinstance(data, dict):
                    payload = data
            except ValueError:
                payload = None

        if 200 <= response.status_code < 300:
            return DeliveryResult(
                delivered=True,
                retryable=False,
                status_code=response.status_code,
                error_reason="ok",
                response_json=payload,
            )

        if response.status_code >= 500:
            return DeliveryResult(
                delivered=False,
                retryable=True,
                status_code=response.status_code,
                error_reason=f"http_{response.status_code}",
                response_json=payload,
            )

        detail = "-"
        if payload:
            detail = str(payload.get("detail") or payload.get("reason") or "-")

        return DeliveryResult(
            delivered=False,
            retryable=False,
            status_code=response.status_code,
            error_reason=f"http_{response.status_code}:{detail}",
            response_json=payload,
        )

