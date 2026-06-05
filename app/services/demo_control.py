from __future__ import annotations

import secrets
import math
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Device, Drone, DroneKey, HostileDetection, InterceptTask, OperatorStation, TelemetryEvent, TrackState, User
from app.domain.enums import DroneStatus, KeyStatus, PlatformRole, ReasonCode, SignatureAlgorithm, UserRole
from app.schemas.models import (
    DemoDetectionCreateRequest,
    DemoDetectionCreateResponse,
    DemoOperatorIdentity,
    DemoResetResponse,
    DemoScenarioSeedRequest,
    DemoScenarioSeedResponse,
    DemoStationSeedRequest,
    HostileContactIngestRequest,
)
from app.security.auth import hash_password
from app.security.crypto import encrypt_secret
from app.services.intercept_control import DetectionTaskResult, InterceptControlError, ingest_recon_contact, normalize_bearing
from app.services.intercept_simulation import haversine_m, initial_bearing_deg

DEMO_RECON_UID = "DEMO-RECON-01"
DEMO_OPERATOR_PASSWORD = "***REMOVED***"
DEMO_DRONE_PREFIX = "DEMO-%"
DEMO_OPERATOR_PREFIX = "demo_operator_%"
DEMO_CONTACT_PREFIX = "HST-DEMO%"


class DemoControlError(Exception):
    pass


def _delete_all(db: Session, rows: list[object]) -> int:
    for row in rows:
        db.delete(row)
    return len(rows)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _deg_to_mil(value: float) -> float:
    return (value * 6400.0) / 360.0


def _new_key_id() -> str:
    return f"key-{uuid4().hex[:16]}"


def _ensure_drone(db: Session, *, drone_uid: str, unit: str, platform_role: PlatformRole) -> Drone:
    drone = db.execute(select(Drone).where(Drone.drone_uid == drone_uid)).scalar_one_or_none()
    if drone is not None:
        drone.unit = unit
        drone.platform_role = platform_role
        drone.status = DroneStatus.active
        return drone

    key = DroneKey(
        key_id=_new_key_id(),
        algo=SignatureAlgorithm.hmac_sha256_v1,
        secret_enc=encrypt_secret(secrets.token_urlsafe(24)),
        status=KeyStatus.active,
    )
    db.add(key)
    db.flush()
    drone = Drone(
        drone_uid=drone_uid,
        unit=unit,
        platform_role=platform_role,
        status=DroneStatus.active,
        key_id=key.id,
    )
    db.add(drone)
    db.flush()
    return drone


def _ensure_operator_user(db: Session, *, username: str) -> User:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is not None:
        user.role = UserRole.operator
        user.is_active = True
        user.must_change_password = False
        user.password_hash = hash_password(DEMO_OPERATOR_PASSWORD)
        return user

    user = User(
        username=username,
        password_hash=hash_password(DEMO_OPERATOR_PASSWORD),
        role=UserRole.operator,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def _upsert_track(
    db: Session,
    *,
    drone_uid: str,
    platform_role: PlatformRole,
    lat: float,
    lon: float,
    alt_m: float,
    heading_deg: float,
    speed_mps: float,
    source: str,
) -> None:
    timestamp = _now()
    state = db.execute(select(TrackState).where(TrackState.drone_uid == drone_uid)).scalar_one_or_none()
    if state is None:
        state = TrackState(
            drone_uid=drone_uid,
            platform_role=platform_role,
            last_seen_at=timestamp,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            speed_mps=speed_mps,
            heading_deg=heading_deg,
        )
        db.add(state)
    else:
        state.platform_role = platform_role
        state.last_seen_at = timestamp
        state.lat = lat
        state.lon = lon
        state.alt_m = alt_m
        state.speed_mps = speed_mps
        state.heading_deg = heading_deg

    db.add(
        TelemetryEvent(
            timestamp=timestamp,
            drone_uid=drone_uid,
            platform_role=platform_role,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            speed_mps=speed_mps,
            heading_deg=heading_deg,
            seq=0,
            source=source,
            signature_valid=True,
            reason_code=ReasonCode.ok,
            ingest_source="demo",
        )
    )


def _ensure_station(
    db: Session,
    *,
    slot_index: int,
    payload: DemoStationSeedRequest,
) -> DemoOperatorIdentity:
    username = f"demo_operator_{slot_index}"
    drone_uid = f"DEMO-INT-{slot_index:02d}"

    user = _ensure_operator_user(db, username=username)
    drone = _ensure_drone(
        db,
        drone_uid=drone_uid,
        unit=f"demo-interceptor-{slot_index}",
        platform_role=PlatformRole.interceptor,
    )

    station = db.execute(select(OperatorStation).where(OperatorStation.user_id == user.id)).scalar_one_or_none()
    if station is None:
        station = OperatorStation(
            user_id=user.id,
            name=payload.name.strip(),
            lat=payload.lat,
            lon=payload.lon,
            assigned_interceptor_drone_id=drone.id,
            is_active=True,
        )
        db.add(station)
    else:
        station.name = payload.name.strip()
        station.lat = payload.lat
        station.lon = payload.lon
        station.assigned_interceptor_drone_id = drone.id
        station.is_active = True

    _upsert_track(
        db,
        drone_uid=drone_uid,
        platform_role=PlatformRole.interceptor,
        lat=payload.lat,
        lon=payload.lon,
        alt_m=0.0,
        heading_deg=0.0,
        speed_mps=0.0,
        source="demo-station",
    )
    return DemoOperatorIdentity(
        username=username,
        password=DEMO_OPERATOR_PASSWORD,
        station_name=payload.name.strip(),
        interceptor_drone_uid=drone_uid,
    )


def seed_demo_scenario(db: Session, payload: DemoScenarioSeedRequest) -> DemoScenarioSeedResponse:
    if not payload.stations:
        raise DemoControlError("En az bir operatör istasyonu gereklidir")

    recon = _ensure_drone(
        db,
        drone_uid=DEMO_RECON_UID,
        unit="demo-recon",
        platform_role=PlatformRole.recon,
    )
    _upsert_track(
        db,
        drone_uid=recon.drone_uid,
        platform_role=PlatformRole.recon,
        lat=payload.recon_lat,
        lon=payload.recon_lon,
        alt_m=payload.recon_alt_m,
        heading_deg=payload.recon_heading_deg,
        speed_mps=payload.recon_speed_mps,
        source="demo-recon",
    )

    operators = [_ensure_station(db, slot_index=index, payload=station) for index, station in enumerate(payload.stations, start=1)]
    db.commit()
    return DemoScenarioSeedResponse(
        recon_drone_uid=recon.drone_uid,
        recon_lat=payload.recon_lat,
        recon_lon=payload.recon_lon,
        recon_heading_deg=payload.recon_heading_deg,
        operators=operators,
    )


def reset_demo_scenario(db: Session) -> DemoResetResponse:
    demo_drones = db.execute(select(Drone).where(Drone.drone_uid.like(DEMO_DRONE_PREFIX))).scalars().all()
    demo_drone_ids = [item.id for item in demo_drones]
    demo_drone_uids = [item.drone_uid for item in demo_drones]
    demo_key_ids = {item.key_id for item in demo_drones}

    demo_users = db.execute(select(User).where(User.username.like(DEMO_OPERATOR_PREFIX))).scalars().all()
    demo_user_ids = [item.id for item in demo_users]

    demo_detections = db.execute(
        select(HostileDetection).where(
            or_(
                HostileDetection.recon_drone_uid == DEMO_RECON_UID,
                HostileDetection.contact_id.like(DEMO_CONTACT_PREFIX),
            )
        )
    ).scalars().all()
    demo_detection_ids = [item.id for item in demo_detections]

    task_filters = []
    if demo_detection_ids:
        task_filters.append(InterceptTask.hostile_detection_id.in_(demo_detection_ids))
    if demo_user_ids:
        task_filters.append(InterceptTask.operator_user_id.in_(demo_user_ids))
    if demo_drone_ids:
        task_filters.append(InterceptTask.interceptor_drone_id.in_(demo_drone_ids))
    demo_tasks = db.execute(select(InterceptTask).where(or_(*task_filters))).scalars().all() if task_filters else []

    station_filters = []
    if demo_user_ids:
        station_filters.append(OperatorStation.user_id.in_(demo_user_ids))
    if demo_drone_ids:
        station_filters.append(OperatorStation.assigned_interceptor_drone_id.in_(demo_drone_ids))
    demo_stations = db.execute(select(OperatorStation).where(or_(*station_filters))).scalars().all() if station_filters else []

    telemetry_events = (
        db.execute(select(TelemetryEvent).where(TelemetryEvent.drone_uid.in_(demo_drone_uids))).scalars().all()
        if demo_drone_uids
        else []
    )
    tracks = (
        db.execute(select(TrackState).where(TrackState.drone_uid.in_(demo_drone_uids))).scalars().all()
        if demo_drone_uids
        else []
    )
    devices = db.execute(select(Device).where(Device.drone_id.in_(demo_drone_ids))).scalars().all() if demo_drone_ids else []

    deleted_tasks = _delete_all(db, demo_tasks)
    db.flush()
    deleted_detections = _delete_all(db, demo_detections)
    deleted_stations = _delete_all(db, demo_stations)
    deleted_telemetry_events = _delete_all(db, telemetry_events)
    deleted_tracks = _delete_all(db, tracks)
    _delete_all(db, devices)
    db.flush()

    deleted_drones = _delete_all(db, demo_drones)
    db.flush()

    deleted_keys = 0
    if demo_key_ids:
        orphan_keys = db.execute(
            select(DroneKey).where(
                DroneKey.id.in_(demo_key_ids),
                ~DroneKey.drones.any(),
            )
        ).scalars().all()
        deleted_keys = _delete_all(db, orphan_keys)

    deleted_users = _delete_all(db, demo_users)
    db.commit()

    return DemoResetResponse(
        deleted_tasks=deleted_tasks,
        deleted_detections=deleted_detections,
        deleted_stations=deleted_stations,
        deleted_tracks=deleted_tracks,
        deleted_telemetry_events=deleted_telemetry_events,
        deleted_drones=deleted_drones,
        deleted_users=deleted_users,
        deleted_keys=deleted_keys,
        message="Demo kayıtları sıfırlandı.",
    )


def create_demo_detection(db: Session, payload: DemoDetectionCreateRequest) -> DemoDetectionCreateResponse:
    recon_uid = payload.recon_drone_uid or DEMO_RECON_UID
    track = db.execute(select(TrackState).where(TrackState.drone_uid == recon_uid)).scalar_one_or_none()
    if track is None:
        raise DemoControlError("Demo keşif izi bulunamadı. Önce senaryoyu kurun.")
    if track.platform_role != PlatformRole.recon:
        raise DemoControlError("Seçilen keşif drone'u keşif platformu değil")

    if recon_uid == DEMO_RECON_UID:
        # Demo presentations may sit idle between scenario setup and target confirmation.
        # Keep the scripted recon track fresh without weakening the production ingest path.
        track.last_seen_at = _now()
        db.flush()

    range_m = haversine_m(track.lat, track.lon, payload.target_lat, payload.target_lon)
    if range_m <= 1.0:
        raise DemoControlError("Hedef keşif izine çok yakın")

    true_bearing_deg = initial_bearing_deg(track.lat, track.lon, payload.target_lat, payload.target_lon)
    relative_bearing_deg = normalize_bearing(true_bearing_deg - track.heading_deg)
    altitude_delta = payload.target_alt_m - track.alt_m
    elevation_deg = math.degrees(math.atan2(altitude_delta, range_m))

    try:
        result: DetectionTaskResult = ingest_recon_contact(
            db,
            HostileContactIngestRequest(
                recon_drone_uid=recon_uid,
                contact_id=payload.contact_id,
                bearing_mil=_deg_to_mil(relative_bearing_deg),
                range_m=range_m,
                elevation_mil=_deg_to_mil(elevation_deg),
                confidence=payload.confidence,
            ),
        )
    except InterceptControlError as exc:
        raise DemoControlError(str(exc)) from exc

    assigned_username = None
    assigned_station_name = None
    assigned_station = None
    if result.detection.assigned_operator_station_id:
        station = db.execute(
            select(OperatorStation, User)
            .join(User, User.id == OperatorStation.user_id)
            .where(OperatorStation.id == result.detection.assigned_operator_station_id)
        ).first()
        if station is not None:
            station_row, user = station
            assigned_station = station_row
            assigned_station_name = station_row.name
            assigned_username = user.username

    from app.services.field_layer_effects import list_active_field_layers
    from app.services.intercept_control import build_detection_response  # local import avoids circular import

    return DemoDetectionCreateResponse(
        detection=build_detection_response(result.detection, assigned_station, field_layers=list_active_field_layers(db)),
        assigned_task_id=None if result.task is None else result.task.id,
        assigned_operator_username=assigned_username,
        assigned_station_name=assigned_station_name,
    )
