from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx


def _sha256_hex(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def _canonical_input(drone_uid: str, ts_ms: str, nonce: str, body_hash_hex: str) -> str:
    return f"{drone_uid}\n{ts_ms}\n{nonce}\n{body_hash_hex}"


def _hmac_hex(secret: str, text: str) -> str:
    return hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def _telemetry_headers(
    *,
    drone_uid: str,
    device_id: str | None,
    secret: str,
    raw_body: bytes,
    nonce: str,
) -> dict[str, str]:
    ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    body_hash = _sha256_hex(raw_body)
    canonical = _canonical_input(drone_uid, ts_ms, nonce, body_hash)
    signature = _hmac_hex(secret, canonical)
    headers = {
        "X-Drone-Uid": drone_uid,
        "X-Ts": ts_ms,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "X-Sig-Version": "hmac-sha256-v1",
    }
    if device_id:
        headers["X-Device-Id"] = device_id
    return headers


def _json_request(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    expected_status: int | None = None,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    content: bytes | None = None,
) -> tuple[httpx.Response, dict[str, Any] | None]:
    response = client.request(
        method=method,
        url=url,
        headers=headers,
        json=json_body,
        content=content,
    )
    body: dict[str, Any] | None = None
    if "application/json" in response.headers.get("content-type", "").lower():
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = None
    if expected_status is not None and response.status_code != expected_status:
        raise RuntimeError(f"{method} {url} expected {expected_status}, got {response.status_code}: {response.text}")
    return response, body


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VPN+mTLS Jetson->Bridge->API E2E smoke test")
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--bridge-url", default="http://localhost:8100")
    parser.add_argument("--bridge-token", default=os.getenv("BRIDGE_SOURCE_TOKEN", "change-me-bridge-token"))
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--device-id", default="")
    parser.add_argument("--allow-bootstrap-password-change", action="store_true")
    parser.add_argument("--new-password", default="")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--tls-ca-file", default="")
    parser.add_argument("--tls-client-cert-file", default="")
    parser.add_argument("--tls-client-key-file", default="")
    parser.add_argument("--tls-insecure-skip-verify", action="store_true")
    parser.add_argument("--skip-replay-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


@dataclass(slots=True)
class SmokeContext:
    api_base: str
    bridge_base: str
    bridge_token: str
    username: str
    password: str
    device_id: str | None
    allow_bootstrap_password_change: bool
    new_password: str
    timeout_seconds: float
    skip_replay_check: bool
    dry_run: bool


def _print_step(message: str) -> None:
    print(f"[STEP] {message}")


def _print_ok(message: str) -> None:
    print(f"[ OK ] {message}")


def _build_verify(args: argparse.Namespace) -> bool | str:
    if args.tls_insecure_skip_verify:
        return False
    if args.tls_ca_file:
        return args.tls_ca_file
    return True


def _build_cert(args: argparse.Namespace) -> tuple[str, str] | None:
    if not args.tls_client_cert_file and not args.tls_client_key_file:
        return None
    if not args.tls_client_cert_file or not args.tls_client_key_file:
        raise RuntimeError("Both --tls-client-cert-file and --tls-client-key-file are required together.")
    return (args.tls_client_cert_file, args.tls_client_key_file)


def _ensure_password_change_if_needed(
    *,
    api_client: httpx.Client,
    context: SmokeContext,
    token: str,
    password_change_required: bool,
) -> tuple[str, str]:
    current_password = context.password
    current_token = token

    if not password_change_required:
        return current_password, current_token

    if not context.allow_bootstrap_password_change:
        raise RuntimeError(
            "Login requires password change. Re-run with --allow-bootstrap-password-change "
            "(and optionally --new-password)."
        )

    target_password = context.new_password or f"Admin-{secrets.token_urlsafe(12)}"
    if len(target_password) < 12:
        raise RuntimeError("Provided --new-password must be at least 12 chars.")

    _print_step("Bootstrap password change required, performing /v1/auth/change-password")
    _, _ = _json_request(
        api_client,
        method="POST",
        url=f"{context.api_base}/v1/auth/change-password",
        expected_status=200,
        headers={"Authorization": f"Bearer {current_token}"},
        json_body={"current_password": current_password, "new_password": target_password},
    )
    _print_ok("Password changed")

    _print_step("Re-login with updated password")
    _, relogin_body = _json_request(
        api_client,
        method="POST",
        url=f"{context.api_base}/v1/auth/login",
        expected_status=200,
        json_body={"username": context.username, "password": target_password},
    )
    assert relogin_body is not None
    current_token = str(relogin_body["access_token"])
    if bool(relogin_body.get("password_change_required", False)):
        raise RuntimeError("Password still marked as change-required after update.")
    _print_ok("Re-login successful")

    print(f"[INFO] Updated password in this run: {target_password}")
    return target_password, current_token


def run() -> int:
    args = _build_arg_parser().parse_args()
    context = SmokeContext(
        api_base=args.api_base_url.rstrip("/"),
        bridge_base=args.bridge_url.rstrip("/"),
        bridge_token=args.bridge_token,
        username=args.username,
        password=args.password,
        device_id=(args.device_id.strip() or None),
        allow_bootstrap_password_change=bool(args.allow_bootstrap_password_change),
        new_password=args.new_password,
        timeout_seconds=args.timeout_seconds,
        skip_replay_check=bool(args.skip_replay_check),
        dry_run=bool(args.dry_run),
    )

    verify = _build_verify(args)
    cert = _build_cert(args)

    if context.dry_run:
        print("[DRY-RUN] Configuration")
        print(json.dumps(
            {
                "api_base_url": context.api_base,
                "bridge_url": context.bridge_base,
                "bridge_token_set": bool(context.bridge_token),
                "username": context.username,
                "device_id": context.device_id,
                "allow_bootstrap_password_change": context.allow_bootstrap_password_change,
                "timeout_seconds": context.timeout_seconds,
                "skip_replay_check": context.skip_replay_check,
                "tls_verify": verify if isinstance(verify, bool) else "custom-ca-file",
                "tls_client_cert": bool(cert),
            },
            indent=2,
        ))
        return 0

    api_client = httpx.Client(timeout=context.timeout_seconds)
    bridge_client = httpx.Client(timeout=context.timeout_seconds, verify=verify, cert=cert)
    try:
        _print_step("Bridge health check")
        _, _ = _json_request(
            bridge_client,
            method="GET",
            url=f"{context.bridge_base}/bridge/v1/health",
            expected_status=200,
        )
        _print_ok("Bridge health ok")

        _print_step("API login")
        _, login_body = _json_request(
            api_client,
            method="POST",
            url=f"{context.api_base}/v1/auth/login",
            expected_status=200,
            json_body={"username": context.username, "password": context.password},
        )
        assert login_body is not None
        token = str(login_body["access_token"])
        password_change_required = bool(login_body.get("password_change_required", False))
        _print_ok("Login ok")

        current_password, token = _ensure_password_change_if_needed(
            api_client=api_client,
            context=context,
            token=token,
            password_change_required=password_change_required,
        )

        auth_headers = {"Authorization": f"Bearer {token}"}
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        drone_uid = f"E2E-{run_id}"

        _print_step("Create drone + mission")
        _, drone_body = _json_request(
            api_client,
            method="POST",
            url=f"{context.api_base}/v1/drones",
            expected_status=201,
            headers=auth_headers,
            json_body={"drone_uid": drone_uid, "unit": "E2E", "status": "active"},
        )
        assert drone_body is not None
        drone_id = str(drone_body["drone"]["id"])
        shared_secret = str(drone_body["shared_secret"])

        now = datetime.now(timezone.utc)
        _, mission_body = _json_request(
            api_client,
            method="POST",
            url=f"{context.api_base}/v1/missions",
            expected_status=201,
            headers=auth_headers,
            json_body={
                "name": f"E2E Mission {run_id}",
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(minutes=30)).isoformat(),
            },
        )
        assert mission_body is not None
        mission_id = str(mission_body["id"])

        _, _ = _json_request(
            api_client,
            method="POST",
            url=f"{context.api_base}/v1/missions/{mission_id}/assignments",
            expected_status=201,
            headers=auth_headers,
            json_body={"drone_id": drone_id, "role": "recon"},
        )
        _, _ = _json_request(
            api_client,
            method="POST",
            url=f"{context.api_base}/v1/missions/{mission_id}/approve",
            expected_status=200,
            headers=auth_headers,
        )
        _print_ok("Drone and mission ready")

        if context.device_id:
            _print_step("Provision device identity")
            _, _ = _json_request(
                api_client,
                method="POST",
                url=f"{context.api_base}/v2/devices/provision",
                expected_status=201,
                headers=auth_headers,
                json_body={
                    "device_id": context.device_id,
                    "drone_uid": drone_uid,
                    "cert_fingerprint": f"sha256:e2e-{run_id}",
                },
            )
            _print_ok("Device provisioned")

        payload_obj = {
            "lat": 41.015,
            "lon": 28.979,
            "alt_m": 120.0,
            "speed_mps": 13.2,
            "heading_deg": 90.0,
            "seq": 1,
            "source": "vpn-mtls-e2e-smoke",
        }
        raw_body = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
        nonce = str(uuid4())
        signed_headers = _telemetry_headers(
            drone_uid=drone_uid,
            device_id=context.device_id,
            secret=shared_secret,
            raw_body=raw_body,
            nonce=nonce,
        )

        _print_step("Bridge ingest with valid token")
        headers_ok = dict(signed_headers)
        headers_ok["X-Bridge-Token"] = context.bridge_token
        _, ingest_body = _json_request(
            bridge_client,
            method="POST",
            url=f"{context.bridge_base}/bridge/v1/telemetry/ingest",
            expected_status=202,
            headers=headers_ok,
            content=raw_body,
        )
        if not ingest_body or ingest_body.get("status") != "AUTHORIZED":
            raise RuntimeError(f"Expected AUTHORIZED ingest response, got: {ingest_body}")
        _print_ok("Bridge ingest AUTHORIZED")

        if context.skip_replay_check:
            _print_ok("Replay check skipped by flag")
        else:
            _print_step("Replay check via bridge")
            _, replay_body = _json_request(
                bridge_client,
                method="POST",
                url=f"{context.bridge_base}/bridge/v1/telemetry/ingest",
                expected_status=202,
                headers=headers_ok,
                content=raw_body,
            )
            if not replay_body or replay_body.get("reason") != "replay_detected":
                raise RuntimeError(f"Expected replay_detected, got: {replay_body}")
            _print_ok("Replay detection ok")

        _print_step("Invalid bridge token check")
        headers_bad = dict(signed_headers)
        headers_bad["X-Bridge-Token"] = f"{context.bridge_token}-bad"
        response_bad, _ = _json_request(
            bridge_client,
            method="POST",
            url=f"{context.bridge_base}/bridge/v1/telemetry/ingest",
            headers=headers_bad,
            content=raw_body,
        )
        if response_bad.status_code != 401:
            raise RuntimeError(f"Expected 401 for bad bridge token, got {response_bad.status_code}")
        _print_ok("Invalid token blocked (401)")

        _print_step("Track summary sanity check")
        _, summary_body = _json_request(
            api_client,
            method="GET",
            url=f"{context.api_base}/v1/tracks/summary",
            expected_status=200,
            headers=auth_headers,
        )
        assert summary_body is not None
        if int(summary_body.get("authorized", 0)) < 1:
            raise RuntimeError(f"Expected authorized>=1 in summary, got: {summary_body}")
        _print_ok("Summary updated")

        if context.device_id:
            _print_step("Device health check")
            _, device_health = _json_request(
                api_client,
                method="GET",
                url=f"{context.api_base}/v2/devices/{context.device_id}/health",
                expected_status=200,
                headers=auth_headers,
            )
            if not device_health or device_health.get("health") not in ("online", "stale"):
                raise RuntimeError(f"Expected device health online/stale, got: {device_health}")
            _print_ok("Device health updated")

        print("[DONE] VPN+mTLS E2E smoke completed successfully")
        if current_password != context.password:
            print("[WARN] Bootstrap password was changed during this run.")
        return 0
    finally:
        api_client.close()
        bridge_client.close()


if __name__ == "__main__":
    raise SystemExit(run())
