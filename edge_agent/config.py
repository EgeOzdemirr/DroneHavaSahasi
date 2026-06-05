from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class EdgeAgentSettings:
    target: str
    ingest_url: str
    drone_uid: str
    device_id: str | None
    shared_secret: str
    bridge_token: str
    input_mode: str
    udp_host: str
    udp_port: int
    mavlink_device: str
    mavlink_baud: int
    timeout_seconds: float
    tls_ca_file: str | None
    tls_client_cert_file: str | None
    tls_client_key_file: str | None
    tls_insecure_skip_verify: bool
    rate_hz: float
    spool_db_path: str
    retry_max_attempts: int
    retry_backoff_seconds: float
    retry_backoff_max_seconds: float
    queue_max: int
    flush_batch_size: int
    log_every: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Edge agent: reads telemetry from MAVLink UART or UDP JSON, "
            "signs packets, persists them in SQLite spool, and forwards to bridge/api."
        )
    )
    parser.add_argument("--target", choices=["bridge", "api"], default="bridge")
    parser.add_argument("--ingest-url", default="http://localhost:8100/bridge/v1/telemetry/ingest")
    parser.add_argument("--drone-uid", required=True)
    parser.add_argument("--device-id", default="", help="Optional device identity for X-Device-Id header.")
    parser.add_argument("--shared-secret", required=True)
    parser.add_argument("--bridge-token", default="", help="Required when --target bridge")

    parser.add_argument("--input-mode", choices=["mavlink-uart", "udp-json"], default="mavlink-uart")
    parser.add_argument("--udp-host", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=15000)
    parser.add_argument("--mavlink-device", default="/dev/ttyTHS1")
    parser.add_argument("--mavlink-baud", type=int, default=57600)

    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--tls-ca-file", default="", help="Custom CA bundle path for HTTPS verification.")
    parser.add_argument("--tls-client-cert-file", default="", help="Client certificate file for mTLS.")
    parser.add_argument("--tls-client-key-file", default="", help="Client private key file for mTLS.")
    parser.add_argument(
        "--tls-insecure-skip-verify",
        action="store_true",
        help="Disable TLS certificate verification (dev only).",
    )
    parser.add_argument("--rate-hz", type=float, default=1.0)
    parser.add_argument("--spool-db-path", default="./edge_agent_spool.db")
    parser.add_argument("--retry-max-attempts", type=int, default=8)
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--retry-backoff-max-seconds", type=float, default=30.0)
    parser.add_argument("--queue-max", type=int, default=10_000)
    parser.add_argument("--flush-batch-size", type=int, default=25)
    parser.add_argument("--log-every", type=int, default=20)
    return parser


def parse_settings(argv: list[str] | None = None) -> EdgeAgentSettings:
    args = _parser().parse_args(argv)

    if args.target == "bridge" and not args.bridge_token:
        raise SystemExit("--bridge-token is required when --target bridge")
    if args.rate_hz <= 0:
        raise SystemExit("--rate-hz must be > 0")
    if args.retry_max_attempts < 1:
        raise SystemExit("--retry-max-attempts must be >= 1")
    if args.retry_backoff_seconds < 0:
        raise SystemExit("--retry-backoff-seconds must be >= 0")
    if args.retry_backoff_max_seconds < 0:
        raise SystemExit("--retry-backoff-max-seconds must be >= 0")
    if args.retry_backoff_max_seconds < args.retry_backoff_seconds:
        raise SystemExit("--retry-backoff-max-seconds must be >= --retry-backoff-seconds")
    if bool(args.tls_client_cert_file) != bool(args.tls_client_key_file):
        raise SystemExit("--tls-client-cert-file and --tls-client-key-file must be provided together")
    if args.tls_insecure_skip_verify and args.tls_ca_file:
        raise SystemExit("--tls-insecure-skip-verify cannot be used together with --tls-ca-file")
    if args.flush_batch_size < 1:
        raise SystemExit("--flush-batch-size must be >= 1")
    if args.log_every < 1:
        raise SystemExit("--log-every must be >= 1")
    if len(args.device_id.strip()) > 120:
        raise SystemExit("--device-id length must be <= 120")

    return EdgeAgentSettings(
        target=args.target,
        ingest_url=args.ingest_url,
        drone_uid=args.drone_uid,
        device_id=args.device_id.strip() or None,
        shared_secret=args.shared_secret,
        bridge_token=args.bridge_token,
        input_mode=args.input_mode,
        udp_host=args.udp_host,
        udp_port=args.udp_port,
        mavlink_device=args.mavlink_device,
        mavlink_baud=args.mavlink_baud,
        timeout_seconds=args.timeout_seconds,
        tls_ca_file=args.tls_ca_file or None,
        tls_client_cert_file=args.tls_client_cert_file or None,
        tls_client_key_file=args.tls_client_key_file or None,
        tls_insecure_skip_verify=bool(args.tls_insecure_skip_verify),
        rate_hz=args.rate_hz,
        spool_db_path=args.spool_db_path,
        retry_max_attempts=args.retry_max_attempts,
        retry_backoff_seconds=args.retry_backoff_seconds,
        retry_backoff_max_seconds=args.retry_backoff_max_seconds,
        queue_max=args.queue_max,
        flush_batch_size=args.flush_batch_size,
        log_every=args.log_every,
    )
