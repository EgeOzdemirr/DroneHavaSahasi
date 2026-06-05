from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Drone, FieldLayer, HostileDetection, InterceptTask, OperatorStation, TrackState, User
from app.domain.enums import (
    DroneStatus,
    HostileDetectionStatus,
    InterceptTaskStatus,
    PlatformRole,
    UserRole,
)
from app.schemas.models import (
    HostileContactIngestRequest,
    HostileDetectionResponse,
    InterceptTaskResponse,
    OperatorStationResponse,
)
from app.services.field_layer_effects import build_field_layer_effects
from app.services.intercept_simulation import advance_intercept_simulation

settings = get_settings()
MIL_FULL_CIRCLE = 6400.0
EARTH_RADIUS_M = 6_371_000.0


class InterceptControlError(Exception):
    pass


@dataclass
class DetectionTaskResult:
    detection: HostileDetection
    task: InterceptTask | None


def mil_to_deg(value: float) -> float:
    return (value * 360.0) / MIL_FULL_CIRCLE


def normalize_bearing(deg: float) -> float:
    return deg % 360.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    d_lat = lat2_rad - lat1_rad
    d_lon = lon2_rad - lon1_rad
    a = math.sin(d_lat / 2.0) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def destination_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    angular_distance = distance_m / EARTH_RADIUS_M
    bearing_rad = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), ((math.degrees(lon2) + 540.0) % 360.0) - 180.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_fresh_recon_track(db: Session, recon_drone_uid: str, now: datetime) -> TrackState:
    track = db.execute(select(TrackState).where(TrackState.drone_uid == recon_drone_uid)).scalar_one_or_none()
    if track is None:
        raise InterceptControlError("Keşif izi bulunamadı")
    if track.platform_role != PlatformRole.recon:
        raise InterceptControlError("Düşman teması yalnızca keşif izlerinden bildirilebilir")
    age_seconds = abs((_as_utc(now) - _as_utc(track.last_seen_at)).total_seconds())
    if age_seconds > settings.recon_track_max_age_seconds:
        raise InterceptControlError("Keşif izi güncel değil")
    return track


def _station_load_query() -> Select:
    return (
        select(OperatorStation, User, Drone)
        .join(User, User.id == OperatorStation.user_id)
        .join(Drone, Drone.id == OperatorStation.assigned_interceptor_drone_id, isouter=True)
    )


def list_operator_station_rows(db: Session) -> list[tuple[OperatorStation, User, Drone | None]]:
    stmt = _station_load_query().order_by(OperatorStation.is_active.desc(), OperatorStation.name.asc())
    return list(db.execute(stmt).all())


def list_detection_rows(db: Session) -> list[tuple[HostileDetection, OperatorStation | None]]:
    advance_intercept_simulation(db)
    stmt = (
        select(HostileDetection, OperatorStation)
        .join(OperatorStation, OperatorStation.id == HostileDetection.assigned_operator_station_id, isouter=True)
        .order_by(HostileDetection.updated_at.desc())
    )
    return list(db.execute(stmt).all())


def list_task_rows(db: Session, *, operator_user_id: str | None = None) -> list[tuple[InterceptTask, HostileDetection, OperatorStation, User, Drone]]:
    advance_intercept_simulation(db)
    stmt = (
        select(InterceptTask, HostileDetection, OperatorStation, User, Drone)
        .join(HostileDetection, HostileDetection.id == InterceptTask.hostile_detection_id)
        .join(OperatorStation, OperatorStation.id == InterceptTask.operator_station_id)
        .join(User, User.id == InterceptTask.operator_user_id)
        .join(Drone, Drone.id == InterceptTask.interceptor_drone_id)
        .order_by(InterceptTask.assigned_at.desc())
    )
    if operator_user_id is not None:
        stmt = stmt.where(InterceptTask.operator_user_id == operator_user_id)
    return list(db.execute(stmt).all())


def choose_nearest_operator_station(
    db: Session,
    *,
    target_lat: float,
    target_lon: float,
    exclude_station_id: str | None = None,
) -> OperatorStation | None:
    candidates = list_operator_station_rows(db)
    best: tuple[float, int, str, OperatorStation] | None = None

    for station, user, drone in candidates:
        if not station.is_active:
            continue
        if exclude_station_id and station.id == exclude_station_id:
            continue
        if user.role != UserRole.operator:
            continue
        if drone is None or drone.status != DroneStatus.active or drone.platform_role != PlatformRole.interceptor:
            continue

        distance = haversine_m(station.lat, station.lon, target_lat, target_lon)
        open_task_count = (
            db.execute(
                select(func.count(InterceptTask.id)).where(
                    InterceptTask.operator_station_id == station.id,
                    InterceptTask.status.in_((InterceptTaskStatus.pending, InterceptTaskStatus.accepted)),
                )
            ).scalar_one()
            or 0
        )
        candidate = (distance, open_task_count, station.name, station)
        if best is None or candidate < best:
            best = candidate

    return None if best is None else best[3]


def _active_task_for_detection(db: Session, detection_id: str) -> InterceptTask | None:
    stmt = (
        select(InterceptTask)
        .where(
            InterceptTask.hostile_detection_id == detection_id,
            InterceptTask.status.in_((InterceptTaskStatus.pending, InterceptTaskStatus.accepted)),
        )
        .order_by(InterceptTask.assigned_at.desc())
    )
    return db.execute(stmt).scalars().first()


def ingest_recon_contact(db: Session, payload: HostileContactIngestRequest) -> DetectionTaskResult:
    reported_at = payload.timestamp or _now()
    track = _require_fresh_recon_track(db, payload.recon_drone_uid, reported_at)

    relative_bearing_deg = mil_to_deg(payload.bearing_mil)
    elevation_deg = mil_to_deg(payload.elevation_mil)
    true_bearing_deg = normalize_bearing(track.heading_deg + relative_bearing_deg)
    target_lat, target_lon = destination_point(track.lat, track.lon, true_bearing_deg, payload.range_m)
    target_alt_m = track.alt_m + math.tan(math.radians(elevation_deg)) * payload.range_m

    detection = db.execute(
        select(HostileDetection).where(
            HostileDetection.recon_drone_uid == payload.recon_drone_uid,
            HostileDetection.contact_id == payload.contact_id,
        )
    ).scalar_one_or_none()

    if detection is None:
        detection = HostileDetection(
            recon_drone_uid=payload.recon_drone_uid,
            contact_id=payload.contact_id,
            bearing_mil=payload.bearing_mil,
            range_m=payload.range_m,
            elevation_mil=payload.elevation_mil,
            true_bearing_deg=true_bearing_deg,
            target_lat=target_lat,
            target_lon=target_lon,
            target_alt_m=target_alt_m,
            confidence=payload.confidence,
            status=HostileDetectionStatus.open,
            last_reported_at=reported_at,
        )
        db.add(detection)
        db.flush()
    else:
        detection.bearing_mil = payload.bearing_mil
        detection.range_m = payload.range_m
        detection.elevation_mil = payload.elevation_mil
        detection.true_bearing_deg = true_bearing_deg
        detection.target_lat = target_lat
        detection.target_lon = target_lon
        detection.target_alt_m = target_alt_m
        detection.confidence = payload.confidence
        detection.last_reported_at = reported_at
        if detection.status in {HostileDetectionStatus.resolved, HostileDetectionStatus.cancelled}:
            detection.status = HostileDetectionStatus.open
            detection.assigned_operator_station_id = None

    chosen_station = choose_nearest_operator_station(db, target_lat=target_lat, target_lon=target_lon)
    current_task = _active_task_for_detection(db, detection.id)
    created_or_reused_task: InterceptTask | None = current_task

    if chosen_station is None:
        detection.status = HostileDetectionStatus.open
        detection.assigned_operator_station_id = None
        if current_task and current_task.status == InterceptTaskStatus.pending:
            current_task.status = InterceptTaskStatus.expired
        created_or_reused_task = None
    else:
        detection.status = HostileDetectionStatus.assigned
        detection.assigned_operator_station_id = chosen_station.id

        if current_task and current_task.operator_station_id == chosen_station.id:
            created_or_reused_task = current_task
        else:
            if current_task and current_task.status in {InterceptTaskStatus.pending, InterceptTaskStatus.accepted}:
                current_task.status = InterceptTaskStatus.expired

            created_or_reused_task = InterceptTask(
                hostile_detection_id=detection.id,
                operator_station_id=chosen_station.id,
                operator_user_id=chosen_station.user_id,
                interceptor_drone_id=chosen_station.assigned_interceptor_drone_id,
                status=InterceptTaskStatus.pending,
            )
            db.add(created_or_reused_task)

    db.commit()
    db.refresh(detection)
    if created_or_reused_task is not None:
        db.refresh(created_or_reused_task)
    return DetectionTaskResult(detection=detection, task=created_or_reused_task)


def _get_task_bundle(db: Session, task_id: str) -> tuple[InterceptTask, HostileDetection, OperatorStation, User, Drone]:
    advance_intercept_simulation(db)
    row = db.execute(
        select(InterceptTask, HostileDetection, OperatorStation, User, Drone)
        .join(HostileDetection, HostileDetection.id == InterceptTask.hostile_detection_id)
        .join(OperatorStation, OperatorStation.id == InterceptTask.operator_station_id)
        .join(User, User.id == InterceptTask.operator_user_id)
        .join(Drone, Drone.id == InterceptTask.interceptor_drone_id)
        .where(InterceptTask.id == task_id)
    ).first()
    if row is None:
        raise InterceptControlError("Angajman görevi bulunamadı")
    return row


def accept_task(db: Session, *, task_id: str, operator_user_id: str | None, note: str | None = None) -> InterceptTask:
    task, detection, _station, _user, _drone = _get_task_bundle(db, task_id)
    if operator_user_id and task.operator_user_id != operator_user_id:
        raise InterceptControlError("Görev başka bir operatöre atanmış")
    if task.status != InterceptTaskStatus.pending:
        raise InterceptControlError("Yalnızca bekleyen görevler kabul edilebilir")

    task.status = InterceptTaskStatus.accepted
    task.accepted_at = _now()
    if note:
        task.operator_note = note
    detection.status = HostileDetectionStatus.assigned

    db.commit()
    db.refresh(task)
    return task


def reject_task(db: Session, *, task_id: str, operator_user_id: str | None, note: str | None = None) -> InterceptTask:
    task, detection, _station, _user, _drone = _get_task_bundle(db, task_id)
    if operator_user_id and task.operator_user_id != operator_user_id:
        raise InterceptControlError("Görev başka bir operatöre atanmış")
    if task.status not in {InterceptTaskStatus.pending, InterceptTaskStatus.accepted}:
        raise InterceptControlError("Görev mevcut durumunda reddedilemez")

    task.status = InterceptTaskStatus.rejected
    task.rejected_at = _now()
    task.operator_note = note
    detection.status = HostileDetectionStatus.open
    detection.assigned_operator_station_id = None

    db.commit()
    db.refresh(task)
    return task


def complete_task(db: Session, *, task_id: str, operator_user_id: str | None, note: str | None = None) -> InterceptTask:
    task, detection, _station, _user, _drone = _get_task_bundle(db, task_id)
    if operator_user_id and task.operator_user_id != operator_user_id:
        raise InterceptControlError("Görev başka bir operatöre atanmış")
    if task.status not in {InterceptTaskStatus.pending, InterceptTaskStatus.accepted}:
        raise InterceptControlError("Görev mevcut durumunda tamamlanamaz")

    now = _now()
    if task.accepted_at is None:
        task.accepted_at = now
    task.status = InterceptTaskStatus.completed
    task.completed_at = now
    task.operator_note = note
    detection.status = HostileDetectionStatus.resolved

    db.commit()
    db.refresh(task)
    return task


def build_operator_station_response(station: OperatorStation, user: User, drone: Drone | None) -> OperatorStationResponse:
    return OperatorStationResponse(
        id=station.id,
        user_id=station.user_id,
        username=user.username,
        name=station.name,
        lat=station.lat,
        lon=station.lon,
        assigned_interceptor_drone_id=station.assigned_interceptor_drone_id,
        assigned_interceptor_drone_uid=None if drone is None else drone.drone_uid,
        is_active=station.is_active,
        created_at=station.created_at,
        updated_at=station.updated_at,
    )


def build_detection_response(
    detection: HostileDetection,
    station: OperatorStation | None = None,
    *,
    field_layers: list[FieldLayer] | None = None,
) -> HostileDetectionResponse:
    effects = build_field_layer_effects(field_layers or [], lat=detection.target_lat, lon=detection.target_lon)
    return HostileDetectionResponse(
        id=detection.id,
        recon_drone_uid=detection.recon_drone_uid,
        contact_id=detection.contact_id,
        bearing_mil=detection.bearing_mil,
        range_m=detection.range_m,
        elevation_mil=detection.elevation_mil,
        true_bearing_deg=detection.true_bearing_deg,
        target_lat=detection.target_lat,
        target_lon=detection.target_lon,
        target_alt_m=detection.target_alt_m,
        confidence=detection.confidence,
        status=detection.status,
        assigned_operator_station_id=detection.assigned_operator_station_id,
        assigned_operator_station_name=None if station is None else station.name,
        field_layer_effects=effects,
        last_reported_at=detection.last_reported_at,
        created_at=detection.created_at,
        updated_at=detection.updated_at,
    )


def build_task_response(
    task: InterceptTask,
    detection: HostileDetection,
    station: OperatorStation,
    user: User,
    drone: Drone,
    *,
    field_layers: list[FieldLayer] | None = None,
) -> InterceptTaskResponse:
    effects = build_field_layer_effects(field_layers or [], lat=detection.target_lat, lon=detection.target_lon)
    return InterceptTaskResponse(
        id=task.id,
        hostile_detection_id=task.hostile_detection_id,
        contact_id=detection.contact_id,
        recon_drone_uid=detection.recon_drone_uid,
        operator_station_id=task.operator_station_id,
        operator_station_name=station.name,
        operator_user_id=task.operator_user_id,
        operator_username=user.username,
        interceptor_drone_id=task.interceptor_drone_id,
        interceptor_drone_uid=drone.drone_uid,
        status=task.status,
        assigned_at=task.assigned_at,
        accepted_at=task.accepted_at,
        completed_at=task.completed_at,
        rejected_at=task.rejected_at,
        expires_at=task.expires_at,
        operator_note=task.operator_note,
        bearing_mil=detection.bearing_mil,
        range_m=detection.range_m,
        elevation_mil=detection.elevation_mil,
        true_bearing_deg=detection.true_bearing_deg,
        target_lat=detection.target_lat,
        target_lon=detection.target_lon,
        target_alt_m=detection.target_alt_m,
        confidence=detection.confidence,
        field_layer_effects=effects,
    )
