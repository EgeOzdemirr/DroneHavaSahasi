from __future__ import annotations

import json
import socket
from collections.abc import Generator
from typing import Any


def telemetry_stream_udp(host: str, port: int) -> Generator[dict[str, Any], None, None]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"[INFO] UDP listener active on {host}:{port}", flush=True)
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

