from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Drone, HostileDetection, InterceptTask, OperatorStation, TelemetryEvent, TrackState
from app.domain.enums import HostileDetectionStatus, InterceptTaskStatus, PlatformRole
from app.schemas.models import PlaybackResponse, TelemetryPlaybackPoint, TrackStateResponse

settings = get_settings()
EARTH_RADIUS_M = 6_371_000.0


@dataclass
class SimulationBundle:
    task: InterceptTask
    detection: HostileDetection
    station: OperatorStation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_utc(value: datetime) -> datetime:
    coerced = _as_utc(value)
    return coerced if coerced is not None else _now()


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


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _simulation_duration_seconds(distance_m: float) -> float:
    speed = max(settings.demo_interceptor_speed_mps, 1.0)
    return max(float(settings.demo_interceptor_min_duration_seconds), distance_m / speed)


def _simulation_start(task: InterceptTask) -> datetime | None:
    return _as_utc(task.accepted_at) or _as_utc(task.assigned_at)


def _accepted_simulation_rows(db: Session) -> list[SimulationBundle]:
    rows = db.execute(
        select(InterceptTask, HostileDetection, OperatorStation)
        .join(HostileDetection, HostileDetection.id == InterceptTask.hostile_detection_id)
        .join(OperatorStation, OperatorStation.id == InterceptTask.operator_station_id)
        .where(InterceptTask.status == InterceptTaskStatus.accepted)
    ).all()
    return [SimulationBundle(task=task, detection=detection, station=station) for task, detection, station in rows]


def advance_intercept_simulation(db: Session, *, now: datetime | None = None) -> bool:
    reference = _as_utc(now) or _now()
    changed = False
    for bundle in _accepted_simulation_rows(db):
        started_at = _simulation_start(bundle.task)
        if started_at is None:
            continue
        total_distance = haversine_m(
            bundle.station.lat,
            bundle.station.lon,
            bundle.detection.target_lat,
            bundle.detection.target_lon,
        )
        duration_seconds = _simulation_duration_seconds(total_distance)
        elapsed_seconds = max(0.0, (reference - started_at).total_seconds())
        if elapsed_seconds < duration_seconds:
            continue

        bundle.task.status = InterceptTaskStatus.completed
        bundle.task.completed_at = reference
        if not bundle.task.operator_note:
            bundle.task.operator_note = "Demo görev simüle edildi ve hedef imha edildi."
        bundle.detection.status = HostileDetectionStatus.resolved
        changed = True

    if changed:
        db.commit()
    return changed


def _simulate_point(bundle: SimulationBundle, sample_time: datetime) -> tuple[float, float, float, float, float]:
    started_at = _simulation_start(bundle.task) or sample_time
    total_distance = haversine_m(
        bundle.station.lat,
        bundle.station.lon,
        bundle.detection.target_lat,
        bundle.detection.target_lon,
    )
    duration_seconds = _simulation_duration_seconds(total_distance)
    elapsed_seconds = max(0.0, (_as_utc(sample_time) - started_at).total_seconds())
    progress = 1.0 if duration_seconds <= 0 else max(0.0, min(1.0, elapsed_seconds / duration_seconds))
    bearing_deg = initial_bearing_deg(
        bundle.station.lat,
        bundle.station.lon,
        bundle.detection.target_lat,
        bundle.detection.target_lon,
    )
    lat, lon = destination_point(bundle.station.lat, bundle.station.lon, bearing_deg, total_distance * progress)
    alt_m = bundle.detection.target_alt_m * progress
    speed_mps = 0.0 if progress >= 1.0 else total_distance / duration_seconds
    return lat, lon, alt_m, speed_mps, bearing_deg


def build_simulated_track_overrides(db: Session, *, now: datetime | None = None) -> dict[str, TrackStateResponse]:
    reference = _as_utc(now) or _now()
    rows = db.execute(
        select(InterceptTask, HostileDetection, OperatorStation, Drone, TrackState)
        .join(HostileDetection, HostileDetection.id == InterceptTask.hostile_detection_id)
        .join(OperatorStation, OperatorStation.id == InterceptTask.operator_station_id)
        .join(Drone, Drone.id == InterceptTask.interceptor_drone_id)
        .join(TrackState, TrackState.drone_uid == Drone.drone_uid)
        .where(InterceptTask.status.in_((InterceptTaskStatus.accepted, InterceptTaskStatus.completed)))
        .order_by(InterceptTask.assigned_at.desc())
    ).all()

    overrides: dict[str, TrackStateResponse] = {}
    for task, detection, station, drone, track in rows:
        bundle = SimulationBundle(task=task, detection=detection, station=station)
        sample_time = reference if task.status == InterceptTaskStatus.accepted else (_as_utc(task.completed_at) or reference)
        lat, lon, alt_m, speed_mps, bearing_deg = _simulate_point(bundle, sample_time)
        timestamp = sample_time if task.status == InterceptTaskStatus.accepted else (_as_utc(task.completed_at) or sample_time)
        overrides[drone.drone_uid] = TrackStateResponse(
            drone_uid=drone.drone_uid,
            platform_role=PlatformRole.interceptor,
            last_seen_at=timestamp,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            speed_mps=speed_mps,
            heading_deg=bearing_deg,
            updated_at=timestamp,
        )
    return overrides


def build_track_list_response(db: Session, *, now: datetime | None = None) -> list[TrackStateResponse]:
    advance_intercept_simulation(db, now=now)
    rows = db.execute(select(TrackState).order_by(TrackState.last_seen_at.desc())).scalars().all()
    responses = {
        item.drone_uid: TrackStateResponse(
            drone_uid=item.drone_uid,
            platform_role=item.platform_role,
            last_seen_at=_coerce_utc(item.last_seen_at),
            lat=item.lat,
            lon=item.lon,
            alt_m=item.alt_m,
            speed_mps=item.speed_mps,
            heading_deg=item.heading_deg,
            updated_at=_coerce_utc(item.updated_at),
        )
        for item in rows
    }
    responses.update(build_simulated_track_overrides(db, now=now))
    return sorted(responses.values(), key=lambda item: _coerce_utc(item.last_seen_at), reverse=True)


def build_playback_response(db: Session, *, drone_uid: str, minutes: int, now: datetime | None = None) -> PlaybackResponse:
    advance_intercept_simulation(db, now=now)
    reference = _as_utc(now) or _now()
    cutoff = reference - timedelta(minutes=minutes)
    actual_rows = db.execute(
        select(TelemetryEvent)
        .where(TelemetryEvent.drone_uid == drone_uid, TelemetryEvent.timestamp >= cutoff)
        .order_by(TelemetryEvent.timestamp.asc())
    ).scalars().all()

    points = [
        TelemetryPlaybackPoint(
            timestamp=_coerce_utc(item.timestamp),
            lat=item.lat,
            lon=item.lon,
            alt_m=item.alt_m,
            speed_mps=item.speed_mps,
            heading_deg=item.heading_deg,
            seq=item.seq,
            source=item.source,
        )
        for item in actual_rows
    ]

    rows = db.execute(
        select(InterceptTask, HostileDetection, OperatorStation, Drone)
        .join(HostileDetection, HostileDetection.id == InterceptTask.hostile_detection_id)
        .join(OperatorStation, OperatorStation.id == InterceptTask.operator_station_id)
        .join(Drone, Drone.id == InterceptTask.interceptor_drone_id)
        .where(
            Drone.drone_uid == drone_uid,
            InterceptTask.status.in_((InterceptTaskStatus.accepted, InterceptTaskStatus.completed)),
        )
        .order_by(InterceptTask.assigned_at.desc())
    ).all()

    for task, detection, station, _drone in rows:
        bundle = SimulationBundle(task=task, detection=detection, station=station)
        started_at = _simulation_start(task)
        if started_at is None:
            continue
        end_time = _as_utc(task.completed_at) or reference
        if end_time < cutoff:
            continue
        sample_start = max(started_at, cutoff)
        duration_seconds = max(1.0, _simulation_duration_seconds(haversine_m(station.lat, station.lon, detection.target_lat, detection.target_lon)))
        step_seconds = max(3, int(duration_seconds / 8))
        sample_time = sample_start
        seq = 0
        while sample_time <= end_time:
            lat, lon, alt_m, speed_mps, bearing_deg = _simulate_point(bundle, sample_time)
            points.append(
                TelemetryPlaybackPoint(
                    timestamp=sample_time,
                    lat=lat,
                    lon=lon,
                    alt_m=alt_m,
                    speed_mps=speed_mps,
                    heading_deg=bearing_deg,
                    seq=seq,
                    source="demo-sim",
                )
            )
            seq += 1
            sample_time += timedelta(seconds=step_seconds)
        if not points or points[-1].timestamp != end_time:
            lat, lon, alt_m, speed_mps, bearing_deg = _simulate_point(bundle, end_time)
            points.append(
                TelemetryPlaybackPoint(
                    timestamp=end_time,
                    lat=lat,
                    lon=lon,
                    alt_m=alt_m,
                    speed_mps=speed_mps,
                    heading_deg=bearing_deg,
                    seq=seq,
                    source="demo-sim",
                )
            )

    points.sort(key=lambda item: _coerce_utc(item.timestamp))
    return PlaybackResponse(drone_uid=drone_uid, points=points)
