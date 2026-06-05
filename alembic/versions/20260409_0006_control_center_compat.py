"""Compatibility migration for existing 20260409_0005 databases

Revision ID: 20260409_0006
Revises: 20260409_0005
Create Date: 2026-04-09 12:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260409_0006"
down_revision: Union[str, None] = "20260409_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


platform_role_enum = sa.Enum("recon", "interceptor", name="platformrole", native_enum=False)
hostile_detection_status_enum = sa.Enum(
    "open",
    "assigned",
    "resolved",
    "cancelled",
    name="hostiledetectionstatus",
    native_enum=False,
)
intercept_task_status_enum = sa.Enum(
    "pending",
    "accepted",
    "rejected",
    "completed",
    "expired",
    name="intercepttaskstatus",
    native_enum=False,
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_table_if_exists(table_name: str) -> None:
    if _has_table(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    if _has_table("drones") and not _has_column("drones", "platform_role"):
        op.add_column(
            "drones",
            sa.Column("platform_role", platform_role_enum, nullable=False, server_default="recon"),
        )
        op.alter_column("drones", "platform_role", server_default=None)
    if _has_table("drones"):
        _create_index_if_missing("ix_drones_platform_role", "drones", ["platform_role"])

    if _has_table("telemetry_events") and not _has_column("telemetry_events", "platform_role"):
        op.add_column(
            "telemetry_events",
            sa.Column("platform_role", platform_role_enum, nullable=False, server_default="recon"),
        )
        op.alter_column("telemetry_events", "platform_role", server_default=None)
    if _has_column("telemetry_events", "decision_status"):
        op.drop_column("telemetry_events", "decision_status")
    if _has_column("telemetry_events", "confidence"):
        op.drop_column("telemetry_events", "confidence")

    if _has_table("track_state") and not _has_column("track_state", "platform_role"):
        op.add_column(
            "track_state",
            sa.Column("platform_role", platform_role_enum, nullable=False, server_default="recon"),
        )
        op.alter_column("track_state", "platform_role", server_default=None)
    if _has_table("track_state") and not _has_column("track_state", "speed_mps"):
        op.add_column("track_state", sa.Column("speed_mps", sa.Float(), nullable=False, server_default="0"))
        op.alter_column("track_state", "speed_mps", server_default=None)
    if _has_table("track_state") and not _has_column("track_state", "heading_deg"):
        op.add_column("track_state", sa.Column("heading_deg", sa.Float(), nullable=False, server_default="0"))
        op.alter_column("track_state", "heading_deg", server_default=None)
    if _has_column("track_state", "friend_status"):
        op.drop_column("track_state", "friend_status")
    if _has_column("track_state", "confidence"):
        op.drop_column("track_state", "confidence")
    if _has_column("track_state", "reason"):
        op.drop_column("track_state", "reason")
    if _has_table("track_state"):
        _create_index_if_missing("ix_track_state_platform_role", "track_state", ["platform_role"])

    _drop_table_if_exists("engagement_logs")
    _drop_table_if_exists("engagement_targets")
    _drop_table_if_exists("fire_positions")
    _drop_table_if_exists("weapon_systems")
    _drop_table_if_exists("sensor_contact_events")
    _drop_table_if_exists("mission_assignments")
    _drop_table_if_exists("missions")

    if not _has_table("operator_stations"):
        op.create_table(
            "operator_stations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("lat", sa.Float(), nullable=False),
            sa.Column("lon", sa.Float(), nullable=False),
            sa.Column("assigned_interceptor_drone_id", sa.String(length=36), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["assigned_interceptor_drone_id"], ["drones.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("assigned_interceptor_drone_id"),
            sa.UniqueConstraint("user_id"),
            sa.UniqueConstraint("name"),
        )
    _create_index_if_missing("ix_operator_stations_name", "operator_stations", ["name"])

    if not _has_table("hostile_detections"):
        op.create_table(
            "hostile_detections",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("recon_drone_uid", sa.String(length=120), nullable=False),
            sa.Column("contact_id", sa.String(length=120), nullable=False),
            sa.Column("bearing_mil", sa.Float(), nullable=False),
            sa.Column("range_m", sa.Float(), nullable=False),
            sa.Column("elevation_mil", sa.Float(), nullable=False, server_default="0"),
            sa.Column("target_lat", sa.Float(), nullable=False),
            sa.Column("target_lon", sa.Float(), nullable=False),
            sa.Column("target_alt_m", sa.Float(), nullable=False, server_default="0"),
            sa.Column("true_bearing_deg", sa.Float(), nullable=False),
            sa.Column("confidence", sa.Integer(), nullable=False),
            sa.Column("status", hostile_detection_status_enum, nullable=False, server_default="open"),
            sa.Column("assigned_operator_station_id", sa.String(length=36), nullable=True),
            sa.Column("last_reported_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["assigned_operator_station_id"], ["operator_stations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("recon_drone_uid", "contact_id", name="uq_hostile_detection_recon_contact"),
        )
    _create_index_if_missing("ix_hostile_detections_recon_drone_uid", "hostile_detections", ["recon_drone_uid"])
    _create_index_if_missing("ix_hostile_detections_contact_id", "hostile_detections", ["contact_id"])
    _create_index_if_missing(
        "ix_hostile_detections_assigned_operator_station_id",
        "hostile_detections",
        ["assigned_operator_station_id"],
    )
    _create_index_if_missing("ix_hostile_detections_status", "hostile_detections", ["status"])
    _create_index_if_missing("ix_hostile_detection_status_updated", "hostile_detections", ["status", "updated_at"])

    if not _has_table("intercept_tasks"):
        op.create_table(
            "intercept_tasks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("hostile_detection_id", sa.String(length=36), nullable=False),
            sa.Column("operator_station_id", sa.String(length=36), nullable=False),
            sa.Column("operator_user_id", sa.String(length=36), nullable=False),
            sa.Column("interceptor_drone_id", sa.String(length=36), nullable=False),
            sa.Column("status", intercept_task_status_enum, nullable=False, server_default="pending"),
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("operator_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["hostile_detection_id"], ["hostile_detections.id"]),
            sa.ForeignKeyConstraint(["interceptor_drone_id"], ["drones.id"]),
            sa.ForeignKeyConstraint(["operator_station_id"], ["operator_stations.id"]),
            sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_intercept_tasks_hostile_detection_id", "intercept_tasks", ["hostile_detection_id"])
    _create_index_if_missing("ix_intercept_tasks_operator_station_id", "intercept_tasks", ["operator_station_id"])
    _create_index_if_missing("ix_intercept_tasks_operator_user_id", "intercept_tasks", ["operator_user_id"])
    _create_index_if_missing("ix_intercept_tasks_interceptor_drone_id", "intercept_tasks", ["interceptor_drone_id"])
    _create_index_if_missing("ix_intercept_tasks_status", "intercept_tasks", ["status"])
    _create_index_if_missing("ix_intercept_task_status_assigned", "intercept_tasks", ["status", "assigned_at"])


def downgrade() -> None:
    pass
