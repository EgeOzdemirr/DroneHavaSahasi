from __future__ import annotations

import hashlib
import hmac
import time
import uuid


def canonical_signing_input(drone_uid: str, ts_ms: str, nonce: str, body_hash_hex: str) -> str:
    return f"{drone_uid}\n{ts_ms}\n{nonce}\n{body_hash_hex}"


def hmac_hex(secret: str, canonical_input: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_input.encode("utf-8"), hashlib.sha256).hexdigest()


def build_signed_headers(
    *,
    drone_uid: str,
    device_id: str | None,
    shared_secret: str,
    raw_body: bytes,
    target: str,
    bridge_token: str,
) -> dict[str, str]:
    ts_ms = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    body_hash_hex = hashlib.sha256(raw_body).hexdigest()
    canonical = canonical_signing_input(drone_uid, ts_ms, nonce, body_hash_hex)
    signature = hmac_hex(shared_secret, canonical)

    headers = {
        "X-Drone-Uid": drone_uid,
        "X-Ts": ts_ms,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "X-Sig-Version": "hmac-sha256-v1",
    }
    if device_id:
        headers["X-Device-Id"] = device_id
    if target == "bridge":
        headers["X-Bridge-Token"] = bridge_token
    return headers

