from __future__ import annotations

import json
import time
from collections.abc import Generator
from typing import Any

from edge_agent.config import EdgeAgentSettings, parse_settings
from edge_agent.mavlink_input import telemetry_stream_mavlink
from edge_agent.normalizer import normalize_payload
from edge_agent.sender import TelemetrySender
from edge_agent.signer import build_signed_headers
from edge_agent.spool import SQLiteSpool
from edge_agent.udp_input import telemetry_stream_udp


class EdgeAgentRunner:
    def __init__(self, settings: EdgeAgentSettings) -> None:
        self.settings = settings
        self.seq_counter = 0
        self.last_emit_monotonic = 0.0
        self.sample_interval_seconds = 1.0 / settings.rate_hz
        self.spool = SQLiteSpool(settings.spool_db_path, queue_max=settings.queue_max)
        self.sender = TelemetrySender(
            timeout_seconds=settings.timeout_seconds,
            tls_ca_file=settings.tls_ca_file,
            tls_client_cert_file=settings.tls_client_cert_file,
            tls_client_key_file=settings.tls_client_key_file,
            tls_insecure_skip_verify=settings.tls_insecure_skip_verify,
        )
        self.forwarded_count = 0

    def run(self) -> int:
        stream = self._stream()
        print(
            f"[INFO] edge-agent start input={self.settings.input_mode} "
            f"target={self.settings.target} drone_uid={self.settings.drone_uid}",
            flush=True,
        )
        print(f"[INFO] spool db={self.settings.spool_db_path}", flush=True)

        try:
            for raw in stream:
                now = time.monotonic()
                if (now - self.last_emit_monotonic) < self.sample_interval_seconds:
                    self._flush_once()
                    continue

                self.last_emit_monotonic = now
                next_seq = self.seq_counter + 1

                try:
                    payload = normalize_payload(
                        raw,
                        seq_fallback=next_seq,
                        default_source="edge-agent-mavlink" if self.settings.input_mode == "mavlink-uart" else "edge-agent-udp",
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[WARN] invalid payload ignored: {exc}", flush=True)
                    self._flush_once()
                    continue

                self.seq_counter = next_seq
                self._enqueue_payload(payload)
                self._flush_once()
        finally:
            self.sender.close()
        return 0

    def _stream(self) -> Generator[dict[str, Any], None, None]:
        if self.settings.input_mode == "udp-json":
            return telemetry_stream_udp(self.settings.udp_host, self.settings.udp_port)
        return telemetry_stream_mavlink(self.settings.mavlink_device, self.settings.mavlink_baud)

    def _enqueue_payload(self, payload: dict[str, Any]) -> None:
        raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = build_signed_headers(
            drone_uid=self.settings.drone_uid,
            device_id=self.settings.device_id,
            shared_secret=self.settings.shared_secret,
            raw_body=raw_body,
            target=self.settings.target,
            bridge_token=self.settings.bridge_token,
        )
        enqueued = self.spool.enqueue(headers=headers, raw_body=raw_body)
        if not enqueued:
            print("[WARN] spool queue full, payload dropped", flush=True)

    def _flush_once(self) -> None:
        events = self.spool.fetch_ready(limit=self.settings.flush_batch_size)
        for event in events:
            result = self.sender.send(ingest_url=self.settings.ingest_url, headers=event.headers, raw_body=event.body)
            next_attempts = event.attempts + 1

            if result.delivered:
                self.spool.mark_success(event.id)
                self.forwarded_count += 1
                if self.settings.log_every > 0 and self.forwarded_count % self.settings.log_every == 0:
                    print(
                        f"[INFO] forwarded={self.forwarded_count} outbox={self.spool.outbox_count()} dlq={self.spool.dead_letter_count()}",
                        flush=True,
                    )
                continue

            if result.retryable:
                if next_attempts >= self.settings.retry_max_attempts:
                    self.spool.move_to_dead_letter(event, error_reason=result.error_reason, attempts=next_attempts)
                    print(
                        f"[WARN] moved to dead_letter event_id={event.id} reason={result.error_reason}",
                        flush=True,
                    )
                    continue

                delay = min(
                    self.settings.retry_backoff_seconds * (2 ** max(0, event.attempts)),
                    self.settings.retry_backoff_max_seconds,
                )
                self.spool.mark_retry(
                    event.id,
                    attempts=next_attempts,
                    delay_seconds=delay,
                    error_reason=result.error_reason,
                )
                continue

            self.spool.move_to_dead_letter(event, error_reason=result.error_reason, attempts=next_attempts)
            print(
                f"[WARN] dropped non-retryable event_id={event.id} reason={result.error_reason}",
                flush=True,
            )


def main(argv: list[str] | None = None) -> int:
    settings = parse_settings(argv)
    runner = EdgeAgentRunner(settings)
    return runner.run()
