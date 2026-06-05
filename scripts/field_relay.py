#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import socket
import sys
import time
import uuid
from collections.abc import Generator
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Field relay: receives raw telemetry (stdin-json or udp-json), "
            "builds signed packets, forwards to bridge/api ingest."
        )
    )
    parser.add_argument(
        "--target",
        choices=["bridge", "api"],
        default="bridge",
        help="Forward target type. bridge adds X-Bridge-Token.",
    )
    parser.add_argument(
        "--ingest-url",
        default="http://localhost:8100/bridge/v1/telemetry/ingest",
        help="Target ingest URL.",
    )
    parser.add_argument("--drone-uid", required=True, help="Drone UID used in signature headers.")
    parser.add_argument("--shared-secret", required=True, help="Per-drone shared secret.")
    parser.add_argument(
        "--bridge-token",
        default="",
        help="Required when --target bridge.",
    )
    parser.add_argument(
        "--input-mode",
        choices=["stdin-json", "udp-json"],
        default="stdin-json",
        help="Telemetry input mode.",
    )
    parser.add_argument("--udp-host", default="0.0.0.0", help="UDP bind host for udp-json mode.")
    parser.add_argument("--udp-port", type=int, default=15000, help="UDP bind port for udp-json mode.")
    parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout seconds.")
    return parser.parse_args()


def canonical_signing_input(drone_uid: str, ts_ms: str, nonce: str, body_hash_hex: str) -> str:
    return f"{drone_uid}\n{ts_ms}\n{nonce}\n{body_hash_hex}"


def hmac_hex(secret: str, canonical_input: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_input.encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_payload(raw: dict[str, Any], seq_fallback: int) -> dict[str, Any]:
    def pick(*keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in raw and raw[key] is not None:
                return raw[key]
        return default

    return {
        "lat": float(pick("lat")),
        "lon": float(pick("lon")),
        "alt_m": float(pick("alt_m", "alt", default=0.0)),
        "speed_mps": float(pick("speed_mps", "speed", default=0.0)),
        "heading_deg": float(pick("heading_deg", "heading", default=0.0)),
        "seq": int(pick("seq", default=seq_fallback)),
        "source": str(pick("source", default="field-relay")),
    }


def telemetry_stream_stdin() -> Generator[dict[str, Any], None, None]:
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print("[WARN] invalid JSON line ignored", flush=True)
            continue
        if isinstance(payload, dict):
            yield payload
        else:
            print("[WARN] non-object JSON ignored", flush=True)


def telemetry_stream_udp(host: str, port: int) -> Generator[dict[str, Any], None, None]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"[INFO] udp listener active on {host}:{port}", flush=True)
    try:
        while True:
            data, _ = sock.recvfrom(65535)
            text = data.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                print("[WARN] invalid UDP JSON ignored", flush=True)
                continue
            if isinstance(payload, dict):
                yield payload
            else:
                print("[WARN] non-object UDP JSON ignored", flush=True)
    finally:
        sock.close()


def build_headers(
    *,
    drone_uid: str,
    shared_secret: str,
    raw_body: bytes,
    ts_ms: str,
    nonce: str,
    target: str,
    bridge_token: str,
) -> dict[str, str]:
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
    if target == "bridge":
        headers["X-Bridge-Token"] = bridge_token
    return headers


def main() -> int:
    args = parse_args()

    if args.target == "bridge" and not args.bridge_token:
        print("[ERROR] --bridge-token is required when --target bridge", flush=True)
        return 2

    stream = telemetry_stream_stdin() if args.input_mode == "stdin-json" else telemetry_stream_udp(args.udp_host, args.udp_port)
    print(
        f"[INFO] relay start target={args.target} input={args.input_mode} drone_uid={args.drone_uid} url={args.ingest_url}",
        flush=True,
    )
    if args.input_mode == "stdin-json":
        print('[INFO] waiting telemetry lines on stdin. ex: {"lat":41.0,"lon":29.0,"alt_m":120}', flush=True)

    seq_counter = 0
    with httpx.Client(timeout=args.timeout) as client:
        for raw in stream:
            seq_counter += 1
            try:
                payload = normalize_payload(raw, seq_counter)
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] invalid telemetry payload ignored: {exc}", flush=True)
                continue

            raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ts_ms = str(int(time.time() * 1000))
            nonce = str(uuid.uuid4())
            headers = build_headers(
                drone_uid=args.drone_uid,
                shared_secret=args.shared_secret,
                raw_body=raw_body,
                ts_ms=ts_ms,
                nonce=nonce,
                target=args.target,
                bridge_token=args.bridge_token,
            )

            try:
                response = client.post(args.ingest_url, headers=headers, content=raw_body)
            except httpx.HTTPError as exc:
                print(f"[ERROR] forward failed: {exc.__class__.__name__}", flush=True)
                continue

            if response.headers.get("content-type", "").lower().find("application/json") >= 0:
                try:
                    data = response.json()
                except ValueError:
                    data = {}
            else:
                data = {}

            status = data.get("status", "-")
            reason = data.get("reason", data.get("detail", "-"))
            print(
                f"[FORWARD] http={response.status_code} seq={payload['seq']} status={status} reason={reason}",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

