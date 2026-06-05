from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Device, Drone, TelemetryEvent, TrackState
from app.domain.enums import DeviceStatus, ReasonCode
from app.schemas.models import TelemetryPayload
from app.security.crypto import decrypt_secret
from app.security.hmac_signatures import body_sha256_hex, canonical_signing_input, verify_hmac_hex
from app.services.alerts import resolve_open_alert
from app.services.nonce_store import NonceStore

settings = get_settings()
nonce_store = NonceStore()


class TelemetryValidationError(Exception):
    def __init__(self, message: str, reason_code: ReasonCode):
        super().__init__(message)
        self.reason_code = reason_code


def _parse_packet_time(ts_ms: str) -> datetime:
    try:
        value = int(ts_ms)
    except ValueError as exc:
        raise TelemetryValidationError("X-Ts must be unix milliseconds", ReasonCode.clock_skew) from exc
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _clock_ok(packet_time: datetime) -> bool:
    now = datetime.now(timezone.utc)
    delta = abs((now - packet_time).total_seconds())
    return delta <= settings.telemetry_allowed_skew_seconds


def _signature_ok(
    *,
    drone: Drone,
    drone_uid: str,
    ts_ms: str,
    nonce: str,
    provided_sig: str,
    raw_body: bytes,
) -> bool:
    secret = decrypt_secret(drone.key.secret_enc)
    digest = body_sha256_hex(raw_body)
    signing_input = canonical_signing_input(drone_uid, ts_ms, nonce, digest)
    return verify_hmac_hex(secret, signing_input, provided_sig)


def _update_device_health(
    *,
    db: Session,
    device_id: str | None,
    drone_uid: str,
    packet_time: datetime,
    reason_code: ReasonCode,
) -> None:
    if not device_id:
        return

    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        return

    if device.status == DeviceStatus.revoked:
        device.last_error_at = packet_time
        device.last_error_reason = "revoked_device_telemetry"
        return

    if device.drone.drone_uid != drone_uid:
        device.last_error_at = packet_time
        device.last_error_reason = "device_uid_mismatch"
        return

    if reason_code == ReasonCode.ok:
        device.last_seen_at = packet_time
        device.last_error_at = None
        device.last_error_reason = None
        return

    device.last_error_at = packet_time
    device.last_error_reason = reason_code.value


def process_telemetry(
    db: Session,
    *,
    headers: dict[str, str],
    payload: TelemetryPayload,
    raw_body: bytes,
) -> TelemetryEvent:
    drone_uid = headers.get("x-drone-uid")
    device_id = headers.get("x-device-id")
    ts_ms = headers.get("x-ts")
    nonce = headers.get("x-nonce")
    signature = headers.get("x-signature")
    sig_version = headers.get("x-sig-version")

    if not drone_uid or not ts_ms or not nonce or not signature or not sig_version:
        raise TelemetryValidationError("Missing required telemetry signature headers", ReasonCode.bad_signature)
    if sig_version.lower() != "hmac-sha256-v1":
        raise TelemetryValidationError("Unsupported signature version", ReasonCode.bad_signature)

    packet_time = _parse_packet_time(ts_ms)
    drone = db.execute(select(Drone).where(Drone.drone_uid == drone_uid)).scalar_one_or_none()
    if drone is None:
        raise TelemetryValidationError("Drone bulunamadı", ReasonCode.not_in_registry)

    if not _clock_ok(packet_time):
        _update_device_health(
            db=db,
            device_id=device_id,
            drone_uid=drone_uid,
            packet_time=packet_time,
            reason_code=ReasonCode.clock_skew,
        )
        db.commit()
        raise TelemetryValidationError("Clock skew detected", ReasonCode.clock_skew)

    if not nonce_store.register_once(drone_uid, nonce):
        _update_device_health(
            db=db,
            device_id=device_id,
            drone_uid=drone_uid,
            packet_time=packet_time,
            reason_code=ReasonCode.replay_detected,
        )
        db.commit()
        raise TelemetryValidationError("Replay detected", ReasonCode.replay_detected)

    if not _signature_ok(
        drone=drone,
        drone_uid=drone_uid,
        ts_ms=ts_ms,
        nonce=nonce,
        provided_sig=signature,
        raw_body=raw_body,
    ):
        _update_device_health(
            db=db,
            device_id=device_id,
            drone_uid=drone_uid,
            packet_time=packet_time,
            reason_code=ReasonCode.bad_signature,
        )
        db.commit()
        raise TelemetryValidationError("Signature validation failed", ReasonCode.bad_signature)

    event = TelemetryEvent(
        timestamp=packet_time,
        drone_uid=drone_uid,
        platform_role=drone.platform_role,
        lat=payload.lat,
        lon=payload.lon,
        alt_m=payload.alt_m,
        speed_mps=payload.speed_mps,
        heading_deg=payload.heading_deg,
        seq=payload.seq,
        source=payload.source,
        signature_valid=True,
        reason_code=ReasonCode.ok,
        ingest_source="http",
    )
    db.add(event)

    state = db.execute(select(TrackState).where(TrackState.drone_uid == drone_uid)).scalar_one_or_none()
    if state:
        state.platform_role = drone.platform_role
        state.last_seen_at = packet_time
        state.lat = payload.lat
        state.lon = payload.lon
        state.alt_m = payload.alt_m
        state.speed_mps = payload.speed_mps
        state.heading_deg = payload.heading_deg
    else:
        db.add(
            TrackState(
                drone_uid=drone_uid,
                platform_role=drone.platform_role,
                last_seen_at=packet_time,
                lat=payload.lat,
                lon=payload.lon,
                alt_m=payload.alt_m,
                speed_mps=payload.speed_mps,
                heading_deg=payload.heading_deg,
            )
        )

    _update_device_health(
        db=db,
        device_id=device_id,
        drone_uid=drone_uid,
        packet_time=packet_time,
        reason_code=ReasonCode.ok,
    )
    resolve_open_alert(db, drone_uid=drone_uid, alert_type="link_lost")

    db.commit()
    db.refresh(event)
    return event
