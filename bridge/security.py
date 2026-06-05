from __future__ import annotations

import hmac
from collections.abc import Mapping

BRIDGE_TOKEN_HEADER = "x-bridge-token"

REQUIRED_TELEMETRY_HEADERS: dict[str, str] = {
    "x-drone-uid": "X-Drone-Uid",
    "x-ts": "X-Ts",
    "x-nonce": "X-Nonce",
    "x-signature": "X-Signature",
    "x-sig-version": "X-Sig-Version",
}

OPTIONAL_TELEMETRY_HEADERS: dict[str, str] = {
    "x-device-id": "X-Device-Id",
}


def token_valid(provided_token: str | None, expected_token: str) -> bool:
    if not provided_token:
        return False
    return hmac.compare_digest(provided_token, expected_token)


def extract_forward_headers(headers: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    extracted: dict[str, str] = {}
    missing: list[str] = []

    for lower_name, canonical_name in REQUIRED_TELEMETRY_HEADERS.items():
        value = headers.get(lower_name)
        if value is None or value == "":
            missing.append(canonical_name)
            continue
        extracted[canonical_name] = value

    for lower_name, canonical_name in OPTIONAL_TELEMETRY_HEADERS.items():
        value = headers.get(lower_name)
        if value is None or value == "":
            continue
        extracted[canonical_name] = value

    return extracted, missing
