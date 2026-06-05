from datetime import datetime
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import (
    AlertStatus,
    DeviceStatus,
    DroneStatus,
    FieldLayerType,
    HostileDetectionStatus,
    InterceptTaskStatus,
    PlatformRole,
    ReasonCode,
    UserRole,
)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    password_change_required: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    username: str
    password_change_required: bool = False


class DroneCreateRequest(BaseModel):
    drone_uid: str
    unit: str
    platform_role: PlatformRole = PlatformRole.recon
    status: DroneStatus = DroneStatus.active
    shared_secret: str | None = None


class DronePatchRequest(BaseModel):
    unit: str | None = None
    platform_role: PlatformRole | None = None
    status: DroneStatus | None = None


class DroneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drone_uid: str
    unit: str
    platform_role: PlatformRole
    status: DroneStatus
    key_id: str
    created_at: datetime


class DroneProvisionResponse(BaseModel):
    drone: DroneResponse
    key_id: str
    shared_secret: str


class DeviceProvisionRequest(BaseModel):
    device_id: str
    drone_uid: str
    cert_fingerprint: str


class DeviceRotateCertRequest(BaseModel):
    cert_fingerprint: str


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    drone_id: str
    drone_uid: str
    cert_fingerprint: str
    status: DeviceStatus
    last_seen_at: datetime | None
    last_error_at: datetime | None
    last_error_reason: str | None
    created_at: datetime
    updated_at: datetime


class DeviceHealthResponse(BaseModel):
    device_id: str
    drone_uid: str
    status: DeviceStatus
    health: str
    last_seen_at: datetime | None
    seconds_since_last_seen: int | None
    last_error_at: datetime | None
    last_error_reason: str | None
    updated_at: datetime


class TelemetryPayload(BaseModel):
    lat: float
    lon: float
    alt_m: float
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    seq: int = 0
    source: str = "drone"


class TelemetryIngestResponse(BaseModel):
    drone_uid: str
    platform_role: PlatformRole
    signature_valid: bool
    reason: ReasonCode
    timestamp: datetime


class TrackStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    drone_uid: str
    platform_role: PlatformRole
    last_seen_at: datetime
    lat: float
    lon: float
    alt_m: float
    speed_mps: float
    heading_deg: float
    updated_at: datetime


class TrackSummaryResponse(BaseModel):
    total: int
    recon: int
    interceptor: int
    last_update: datetime | None


class OpenSkyAircraftResponse(BaseModel):
    icao24: str
    callsign: str | None
    origin_country: str | None
    lat: float
    lon: float
    baro_altitude_m: float | None
    geo_altitude_m: float | None
    velocity_mps: float | None
    true_track_deg: float | None
    vertical_rate_mps: float | None
    on_ground: bool | None
    last_contact: datetime | None
    category: int | None


class TelemetryPlaybackPoint(BaseModel):
    timestamp: datetime
    lat: float
    lon: float
    alt_m: float
    speed_mps: float
    heading_deg: float
    seq: int
    source: str


class PlaybackResponse(BaseModel):
    drone_uid: str
    points: list[TelemetryPlaybackPoint]


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drone_uid: str
    alert_type: str
    status: AlertStatus
    message: str
    reason_code: ReasonCode | None
    created_at: datetime
    acked_at: datetime | None
    acked_by: str | None


class AlertAckResponse(BaseModel):
    id: str
    status: AlertStatus
    acked_at: datetime | None
    acked_by: str | None


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_username: str
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any]
    success: bool
    created_at: datetime


class OperatorStationCreateRequest(BaseModel):
    user_id: str
    name: str
    lat: float
    lon: float
    assigned_interceptor_drone_id: str | None = None
    is_active: bool = True


class OperatorStationPatchRequest(BaseModel):
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    assigned_interceptor_drone_id: str | None = None
    is_active: bool | None = None


class OperatorStationResponse(BaseModel):
    id: str
    user_id: str
    username: str
    name: str
    lat: float
    lon: float
    assigned_interceptor_drone_id: str | None
    assigned_interceptor_drone_uid: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DemoStationSeedRequest(BaseModel):
    name: str
    lat: float
    lon: float


class DemoOperatorIdentity(BaseModel):
    username: str
    password: str
    station_name: str
    interceptor_drone_uid: str


class DemoScenarioSeedRequest(BaseModel):
    recon_lat: float
    recon_lon: float
    recon_alt_m: float = 1200.0
    recon_heading_deg: float = 90.0
    recon_speed_mps: float = 35.0
    stations: list[DemoStationSeedRequest]


class DemoScenarioSeedResponse(BaseModel):
    recon_drone_uid: str
    recon_lat: float
    recon_lon: float
    recon_heading_deg: float
    operators: list[DemoOperatorIdentity]


class HostileContactIngestRequest(BaseModel):
    recon_drone_uid: str
    contact_id: str
    bearing_mil: float
    range_m: float
    elevation_mil: float = 0.0
    confidence: int = Field(default=50, ge=0, le=100)
    timestamp: datetime | None = None


class FieldLayerEffectResponse(BaseModel):
    layer_id: str
    layer_name: str
    layer_type: FieldLayerType
    severity: str
    label: str


class HostileDetectionResponse(BaseModel):
    id: str
    recon_drone_uid: str
    contact_id: str
    bearing_mil: float
    range_m: float
    elevation_mil: float
    true_bearing_deg: float
    target_lat: float
    target_lon: float
    target_alt_m: float
    confidence: int
    status: HostileDetectionStatus
    assigned_operator_station_id: str | None
    assigned_operator_station_name: str | None
    field_layer_effects: list[FieldLayerEffectResponse] = Field(default_factory=list)
    last_reported_at: datetime
    created_at: datetime
    updated_at: datetime


class DemoDetectionCreateRequest(BaseModel):
    target_lat: float
    target_lon: float
    target_alt_m: float = 350.0
    contact_id: str
    recon_drone_uid: str | None = None
    confidence: int = Field(default=85, ge=0, le=100)


class DemoDetectionCreateResponse(BaseModel):
    detection: HostileDetectionResponse
    assigned_task_id: str | None
    assigned_operator_username: str | None
    assigned_station_name: str | None


class DemoResetResponse(BaseModel):
    deleted_tasks: int
    deleted_detections: int
    deleted_stations: int
    deleted_tracks: int
    deleted_telemetry_events: int
    deleted_drones: int
    deleted_users: int
    deleted_keys: int
    message: str


class TaskActionRequest(BaseModel):
    operator_note: str | None = None


class InterceptTaskResponse(BaseModel):
    id: str
    hostile_detection_id: str
    contact_id: str
    recon_drone_uid: str
    operator_station_id: str
    operator_station_name: str
    operator_user_id: str
    operator_username: str
    interceptor_drone_id: str
    interceptor_drone_uid: str
    status: InterceptTaskStatus
    assigned_at: datetime
    accepted_at: datetime | None
    completed_at: datetime | None
    rejected_at: datetime | None
    expires_at: datetime | None
    operator_note: str | None
    bearing_mil: float
    range_m: float
    elevation_mil: float
    true_bearing_deg: float
    target_lat: float
    target_lon: float
    target_alt_m: float
    confidence: int
    field_layer_effects: list[FieldLayerEffectResponse] = Field(default_factory=list)


def _validate_geojson_polygon(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("geometry must be a GeoJSON Polygon object")
    if value.get("type") != "Polygon":
        raise ValueError("geometry.type must be Polygon")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("geometry.coordinates must contain at least one ring")
    for ring in coordinates:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("polygon rings must contain at least four coordinates")
        if ring[0] != ring[-1]:
            raise ValueError("polygon rings must be closed")
        for point in ring:
            if not isinstance(point, list | tuple) or len(point) < 2:
                raise ValueError("polygon coordinates must be [lon, lat] pairs")
            try:
                lon = float(point[0])
                lat = float(point[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("polygon coordinates must be numeric") from exc
            if not math.isfinite(lat) or not math.isfinite(lon):
                raise ValueError("polygon coordinates must be finite")
            if lat < -90 or lat > 90 or lon < -180 or lon > 180:
                raise ValueError("polygon coordinates are out of range")
    return value


class FieldLayerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    layer_type: FieldLayerType
    geometry: dict[str, Any]
    style: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_geojson_polygon(value)

    @field_validator("style")
    @classmethod
    def validate_style(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("style must be an object")
        return value


class FieldLayerPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    layer_type: FieldLayerType | None = None
    geometry: dict[str, Any] | None = None
    style: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return _validate_geojson_polygon(value)

    @field_validator("style")
    @classmethod
    def validate_style(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and not isinstance(value, dict):
            raise ValueError("style must be an object")
        return value


class FieldLayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    layer_type: FieldLayerType
    geometry: dict[str, Any]
    style: dict[str, Any]
    is_active: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
