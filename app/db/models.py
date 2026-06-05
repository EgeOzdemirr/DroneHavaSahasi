from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import (
    AlertStatus,
    DeviceStatus,
    DroneStatus,
    FieldLayerType,
    HostileDetectionStatus,
    InterceptTaskStatus,
    KeyStatus,
    PlatformRole,
    ReasonCode,
    SignatureAlgorithm,
    UserRole,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    operator_station: Mapped["OperatorStation | None"] = relationship(back_populates="user")


class DroneKey(Base):
    __tablename__ = "drone_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    algo: Mapped[SignatureAlgorithm] = mapped_column(
        Enum(SignatureAlgorithm, native_enum=False),
        default=SignatureAlgorithm.hmac_sha256_v1,
        nullable=False,
    )
    secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[KeyStatus] = mapped_column(Enum(KeyStatus, native_enum=False), default=KeyStatus.active, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    drones: Mapped[list["Drone"]] = relationship(back_populates="key")


class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    drone_uid: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(120), nullable=False)
    platform_role: Mapped[PlatformRole] = mapped_column(
        Enum(PlatformRole, native_enum=False),
        default=PlatformRole.recon,
        nullable=False,
        index=True,
    )
    status: Mapped[DroneStatus] = mapped_column(Enum(DroneStatus, native_enum=False), default=DroneStatus.active, nullable=False)
    key_id: Mapped[str] = mapped_column(String(36), ForeignKey("drone_keys.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    key: Mapped[DroneKey] = relationship(back_populates="drones")
    devices: Mapped[list["Device"]] = relationship(back_populates="drone")
    operator_station: Mapped["OperatorStation | None"] = relationship(back_populates="assigned_interceptor_drone")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    device_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    drone_id: Mapped[str] = mapped_column(String(36), ForeignKey("drones.id"), nullable=False, index=True)
    cert_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, native_enum=False),
        default=DeviceStatus.active,
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    drone: Mapped[Drone] = relationship(back_populates="devices")


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    drone_uid: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    platform_role: Mapped[PlatformRole] = mapped_column(Enum(PlatformRole, native_enum=False), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt_m: Mapped[float] = mapped_column(Float, nullable=False)
    speed_mps: Mapped[float] = mapped_column(Float, nullable=False)
    heading_deg: Mapped[float] = mapped_column(Float, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="drone")
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason_code: Mapped[ReasonCode] = mapped_column(Enum(ReasonCode, native_enum=False), nullable=False)
    ingest_source: Mapped[str] = mapped_column(String(120), nullable=False, default="http")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_telemetry_drone_timestamp", "drone_uid", "timestamp"),
        Index("ix_telemetry_timestamp", "timestamp"),
    )


class TrackState(Base):
    __tablename__ = "track_state"

    drone_uid: Mapped[str] = mapped_column(String(120), primary_key=True)
    platform_role: Mapped[PlatformRole] = mapped_column(Enum(PlatformRole, native_enum=False), nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt_m: Mapped[float] = mapped_column(Float, nullable=False)
    speed_mps: Mapped[float] = mapped_column(Float, nullable=False)
    heading_deg: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    drone_uid: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus, native_enum=False), nullable=False, default=AlertStatus.open)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[ReasonCode | None] = mapped_column(Enum(ReasonCode, native_enum=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    __table_args__ = (Index("ix_alerts_status_created", "status", "created_at"),)


class OperatorStation(Base):
    __tablename__ = "operator_stations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    assigned_interceptor_drone_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("drones.id"),
        nullable=True,
        unique=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user: Mapped[User] = relationship(back_populates="operator_station")
    assigned_interceptor_drone: Mapped[Drone | None] = relationship(back_populates="operator_station")


class HostileDetection(Base):
    __tablename__ = "hostile_detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recon_drone_uid: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    bearing_mil: Mapped[float] = mapped_column(Float, nullable=False)
    range_m: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_mil: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_lat: Mapped[float] = mapped_column(Float, nullable=False)
    target_lon: Mapped[float] = mapped_column(Float, nullable=False)
    target_alt_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    true_bearing_deg: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[HostileDetectionStatus] = mapped_column(
        Enum(HostileDetectionStatus, native_enum=False),
        nullable=False,
        default=HostileDetectionStatus.open,
        index=True,
    )
    assigned_operator_station_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("operator_stations.id"),
        nullable=True,
        index=True,
    )
    last_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("recon_drone_uid", "contact_id", name="uq_hostile_detection_recon_contact"),
        Index("ix_hostile_detection_status_updated", "status", "updated_at"),
    )


class InterceptTask(Base):
    __tablename__ = "intercept_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    hostile_detection_id: Mapped[str] = mapped_column(String(36), ForeignKey("hostile_detections.id"), nullable=False, index=True)
    operator_station_id: Mapped[str] = mapped_column(String(36), ForeignKey("operator_stations.id"), nullable=False, index=True)
    operator_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    interceptor_drone_id: Mapped[str] = mapped_column(String(36), ForeignKey("drones.id"), nullable=False, index=True)
    status: Mapped[InterceptTaskStatus] = mapped_column(
        Enum(InterceptTaskStatus, native_enum=False),
        nullable=False,
        default=InterceptTaskStatus.pending,
        index=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_intercept_task_status_assigned", "status", "assigned_at"),)


class FieldLayer(Base):
    __tablename__ = "field_layers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    layer_type: Mapped[FieldLayerType] = mapped_column(Enum(FieldLayerType, native_enum=False), nullable=False, index=True)
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)
    style: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_field_layers_type_active", "layer_type", "is_active"),)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_username: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
