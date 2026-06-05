from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.db.models import Drone, OperatorStation, User
from app.db.session import get_db
from app.domain.enums import PlatformRole, UserRole
from app.schemas.models import OperatorStationCreateRequest, OperatorStationPatchRequest, OperatorStationResponse
from app.services.audit import write_audit_log
from app.services.intercept_control import build_operator_station_response, list_operator_station_rows

router = APIRouter(prefix="/v1/operator-stations", tags=["operator-stations"])


def _station_response(db: Session, station_id: str) -> OperatorStationResponse:
    row = db.execute(
        select(OperatorStation, User, Drone)
        .join(User, User.id == OperatorStation.user_id)
        .join(Drone, Drone.id == OperatorStation.assigned_interceptor_drone_id, isouter=True)
        .where(OperatorStation.id == station_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operatör istasyonu bulunamadı")
    station, user, drone = row
    return build_operator_station_response(station, user, drone)


def _validate_operator_station_payload(
    db: Session,
    *,
    user_id: str | None,
    drone_id: str | None,
) -> tuple[User | None, Drone | None]:
    user: User | None = None
    drone: Drone | None = None

    if user_id is not None:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operatör kullanıcısı bulunamadı")
        if user.role != UserRole.operator:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="İstasyon kullanıcısı operatör rolünde olmalıdır")

    if drone_id is not None:
        drone = db.execute(select(Drone).where(Drone.id == drone_id)).scalar_one_or_none()
        if drone is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Önleyici drone bulunamadı")
        if drone.platform_role != PlatformRole.interceptor:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Atanan drone önleyici rolünde olmalıdır")

    return user, drone


@router.get("", response_model=list[OperatorStationResponse])
def list_operator_stations(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[OperatorStationResponse]:
    return [build_operator_station_response(station, user, drone) for station, user, drone in list_operator_station_rows(db)]


@router.post("", response_model=OperatorStationResponse, status_code=status.HTTP_201_CREATED)
def create_operator_station(
    payload: OperatorStationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> OperatorStationResponse:
    if current_user.role == UserRole.operator and payload.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operatörler yalnızca kendi istasyonlarını oluşturabilir")

    _validate_operator_station_payload(db, user_id=payload.user_id, drone_id=payload.assigned_interceptor_drone_id)
    station = OperatorStation(
        user_id=payload.user_id,
        name=payload.name.strip(),
        lat=payload.lat,
        lon=payload.lon,
        assigned_interceptor_drone_id=payload.assigned_interceptor_drone_id,
        is_active=payload.is_active,
    )
    db.add(station)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Operatör istasyonu adı, kullanıcı veya drone zaten kullanımda")
    db.refresh(station)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="operator_station_create",
        entity_type="operator_station",
        entity_id=station.id,
        details={"name": station.name},
    )
    return _station_response(db, station.id)


@router.patch("/{station_id}", response_model=OperatorStationResponse)
def patch_operator_station(
    station_id: str,
    payload: OperatorStationPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> OperatorStationResponse:
    station = db.execute(select(OperatorStation).where(OperatorStation.id == station_id)).scalar_one_or_none()
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operatör istasyonu bulunamadı")
    if current_user.role == UserRole.operator and station.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operatörler yalnızca kendi istasyonlarını güncelleyebilir")

    new_user_id = None
    new_drone_id = payload.assigned_interceptor_drone_id if "assigned_interceptor_drone_id" in payload.model_fields_set else None
    _validate_operator_station_payload(db, user_id=new_user_id, drone_id=new_drone_id)

    if payload.name is not None:
        station.name = payload.name.strip()
    if payload.lat is not None:
        station.lat = payload.lat
    if payload.lon is not None:
        station.lon = payload.lon
    if "assigned_interceptor_drone_id" in payload.model_fields_set:
        station.assigned_interceptor_drone_id = payload.assigned_interceptor_drone_id
    if payload.is_active is not None:
        station.is_active = payload.is_active

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Operatör istasyonu güncellemesi mevcut bir kayıtla çakışıyor")
    db.refresh(station)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="operator_station_patch",
        entity_type="operator_station",
        entity_id=station.id,
        details=payload.model_dump(exclude_none=True),
    )
    return _station_response(db, station.id)
