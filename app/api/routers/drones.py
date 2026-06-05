import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.db.models import Drone, DroneKey, User
from app.db.session import get_db
from app.domain.enums import KeyStatus, SignatureAlgorithm, UserRole
from app.schemas.models import DroneCreateRequest, DronePatchRequest, DroneProvisionResponse, DroneResponse
from app.security.crypto import encrypt_secret
from app.services.audit import write_audit_log
from app.services.drone_registry import delete_drone_from_registry

router = APIRouter(prefix="/v1/drones", tags=["drones"])


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def _new_key_id() -> str:
    return f"key-{uuid4().hex[:16]}"


@router.post("", response_model=DroneProvisionResponse, status_code=status.HTTP_201_CREATED)
def create_drone(
    payload: DroneCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> DroneProvisionResponse:
    existing = db.execute(select(Drone).where(Drone.drone_uid == payload.drone_uid)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Drone kimliği zaten mevcut")

    shared_secret = payload.shared_secret or _new_secret()
    key = DroneKey(
        key_id=_new_key_id(),
        algo=SignatureAlgorithm.hmac_sha256_v1,
        secret_enc=encrypt_secret(shared_secret),
        status=KeyStatus.active,
    )
    db.add(key)
    db.flush()

    drone = Drone(
        drone_uid=payload.drone_uid,
        unit=payload.unit,
        platform_role=payload.platform_role,
        status=payload.status,
        key_id=key.id,
    )
    db.add(drone)
    db.commit()
    db.refresh(drone)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="drone_create",
        entity_type="drone",
        entity_id=drone.id,
        details={"drone_uid": drone.drone_uid, "unit": drone.unit},
    )
    return DroneProvisionResponse(
        drone=DroneResponse.model_validate(drone),
        key_id=key.key_id,
        shared_secret=shared_secret,
    )


@router.get("", response_model=list[DroneResponse])
def list_drones(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[DroneResponse]:
    items = db.execute(select(Drone).order_by(Drone.created_at.desc())).scalars().all()
    return [DroneResponse.model_validate(item) for item in items]


@router.patch("/{drone_id}", response_model=DroneResponse)
def patch_drone(
    drone_id: str,
    payload: DronePatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> DroneResponse:
    drone = db.execute(select(Drone).where(Drone.id == drone_id)).scalar_one_or_none()
    if not drone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drone bulunamadı")

    if payload.unit is not None:
        drone.unit = payload.unit
    if payload.platform_role is not None:
        drone.platform_role = payload.platform_role
    if payload.status is not None:
        drone.status = payload.status
    db.commit()
    db.refresh(drone)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="drone_patch",
        entity_type="drone",
        entity_id=drone.id,
        details=payload.model_dump(exclude_none=True),
    )
    return DroneResponse.model_validate(drone)


@router.post("/{drone_id}/keys/rotate", response_model=DroneProvisionResponse)
def rotate_drone_key(
    drone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> DroneProvisionResponse:
    drone = db.execute(select(Drone).where(Drone.id == drone_id)).scalar_one_or_none()
    if not drone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drone bulunamadı")

    old_key = db.execute(select(DroneKey).where(DroneKey.id == drone.key_id)).scalar_one_or_none()
    if old_key:
        old_key.status = KeyStatus.inactive

    shared_secret = _new_secret()
    key = DroneKey(
        key_id=_new_key_id(),
        algo=SignatureAlgorithm.hmac_sha256_v1,
        secret_enc=encrypt_secret(shared_secret),
        status=KeyStatus.active,
    )
    db.add(key)
    db.flush()
    drone.key_id = key.id
    db.commit()
    db.refresh(drone)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="drone_key_rotate",
        entity_type="drone",
        entity_id=drone.id,
        details={"new_key_id": key.key_id},
    )
    return DroneProvisionResponse(
        drone=DroneResponse.model_validate(drone),
        key_id=key.key_id,
        shared_secret=shared_secret,
    )


@router.delete("/{drone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_drone(
    drone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> None:
    result = delete_drone_from_registry(
        db,
        drone_id=drone_id,
        actor_username=current_user.username,
        via="api",
    )
    if result.ok:
        return
    if result.reason == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drone bulunamadı")
    if result.reason == "linked_operator_station":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Drone bir operatör istasyonuna bağlı olduğu için silme işlemi engellendi",
        )
    if result.reason == "has_devices":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Drone üzerinde bağlı cihaz kaydı bulunduğu için silme işlemi engellendi",
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Drone silme işlemi başarısız")
