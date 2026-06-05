from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.config import get_settings
from app.db.models import Device, Drone, User
from app.db.session import get_db
from app.domain.enums import DeviceStatus, UserRole
from app.schemas.models import DeviceHealthResponse, DeviceProvisionRequest, DeviceResponse, DeviceRotateCertRequest
from app.services.audit import write_audit_log

router = APIRouter(prefix="/v2/devices", tags=["devices-v2"])
settings = get_settings()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_device_response(device: Device) -> DeviceResponse:
    return DeviceResponse(
        id=device.id,
        device_id=device.device_id,
        drone_id=device.drone_id,
        drone_uid=device.drone.drone_uid,
        cert_fingerprint=device.cert_fingerprint,
        status=device.status,
        last_seen_at=device.last_seen_at,
        last_error_at=device.last_error_at,
        last_error_reason=device.last_error_reason,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


@router.post("/provision", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def provision_device(
    payload: DeviceProvisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> DeviceResponse:
    existing = db.execute(select(Device).where(Device.device_id == payload.device_id)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cihaz kimliği zaten mevcut")

    drone = db.execute(select(Drone).where(Drone.drone_uid == payload.drone_uid)).scalar_one_or_none()
    if not drone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drone bulunamadı")

    device = Device(
        device_id=payload.device_id,
        drone_id=drone.id,
        cert_fingerprint=payload.cert_fingerprint,
        status=DeviceStatus.active,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="device_provision",
        entity_type="device",
        entity_id=device.id,
        details={
            "device_id": device.device_id,
            "drone_uid": drone.drone_uid,
        },
    )
    return _to_device_response(device)


@router.post("/{device_id}/rotate-cert", response_model=DeviceResponse)
def rotate_device_cert(
    device_id: str,
    payload: DeviceRotateCertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> DeviceResponse:
    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if payload.cert_fingerprint == device.cert_fingerprint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cert_fingerprint_unchanged")

    device.cert_fingerprint = payload.cert_fingerprint
    device.last_error_at = None
    device.last_error_reason = None
    db.commit()
    db.refresh(device)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="device_rotate_cert",
        entity_type="device",
        entity_id=device.id,
        details={"device_id": device.device_id},
    )
    return _to_device_response(device)


@router.get("/{device_id}/health", response_model=DeviceHealthResponse)
def get_device_health(
    device_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> DeviceHealthResponse:
    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    now = datetime.now(timezone.utc)
    seconds_since_last_seen: int | None = None
    if device.last_seen_at is not None:
        seconds_since_last_seen = max(0, int((now - _as_utc(device.last_seen_at)).total_seconds()))

    if device.status == DeviceStatus.revoked:
        health = "revoked"
    elif seconds_since_last_seen is None:
        health = "never_seen"
    elif seconds_since_last_seen <= settings.link_lost_seconds:
        health = "online"
    else:
        health = "stale"

    return DeviceHealthResponse(
        device_id=device.device_id,
        drone_uid=device.drone.drone_uid,
        status=device.status,
        health=health,
        last_seen_at=device.last_seen_at,
        seconds_since_last_seen=seconds_since_last_seen,
        last_error_at=device.last_error_at,
        last_error_reason=device.last_error_reason,
        updated_at=device.updated_at,
    )
