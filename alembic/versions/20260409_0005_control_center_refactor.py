"""Refactor schema for control-center workflow

Revision ID: 20260409_0005
Revises: 20260312_0004
Create Date: 2026-04-09 00:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260409_0005"
down_revision: Union[str, None] = "20260312_0004"
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


def upgrade() -> None:
    op.drop_index("ix_sensor_contacts_ts", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contacts_sensor_contact_ts", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contact_events_track_uid", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contact_events_contact_id", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contact_events_sensor_id", table_name="sensor_contact_events")
    op.drop_table("sensor_contact_events")

    op.drop_index("ix_assignments_mission_id", table_name="mission_assignments")
    op.drop_table("mission_assignments")
    op.drop_index("ix_missions_window", table_name="missions")
    op.drop_index("ix_missions_ends_at", table_name="missions")
    op.drop_index("ix_missions_starts_at", table_name="missions")
    op.drop_table("missions")

    op.add_column(
        "drones",
        sa.Column("platform_role", platform_role_enum, nullable=False, server_default="recon"),
    )
    op.create_index("ix_drones_platform_role", "drones", ["platform_role"], unique=False)
    op.alter_column("drones", "platform_role", server_default=None)

    op.add_column(
        "telemetry_events",
        sa.Column("platform_role", platform_role_enum, nullable=False, server_default="recon"),
    )
    op.drop_column("telemetry_events", "decision_status")
    op.drop_column("telemetry_events", "confidence")
    op.alter_column("telemetry_events", "platform_role", server_default=None)

    op.add_column(
        "track_state",
        sa.Column("platform_role", platform_role_enum, nullable=False, server_default="recon"),
    )
    op.add_column("track_state", sa.Column("speed_mps", sa.Float(), nullable=False, server_default="0"))
    op.add_column("track_state", sa.Column("heading_deg", sa.Float(), nullable=False, server_default="0"))
    op.create_index("ix_track_state_platform_role", "track_state", ["platform_role"], unique=False)
    op.drop_column("track_state", "friend_status")
    op.drop_column("track_state", "confidence")
    op.drop_column("track_state", "reason")
    op.alter_column("track_state", "platform_role", server_default=None)
    op.alter_column("track_state", "speed_mps", server_default=None)
    op.alter_column("track_state", "heading_deg", server_default=None)

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
    op.create_index("ix_operator_stations_name", "operator_stations", ["name"], unique=False)

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
    op.create_index("ix_hostile_detections_recon_drone_uid", "hostile_detections", ["recon_drone_uid"], unique=False)
    op.create_index("ix_hostile_detections_contact_id", "hostile_detections", ["contact_id"], unique=False)
    op.create_index("ix_hostile_detections_assigned_operator_station_id", "hostile_detections", ["assigned_operator_station_id"], unique=False)
    op.create_index("ix_hostile_detections_status", "hostile_detections", ["status"], unique=False)
    op.create_index("ix_hostile_detection_status_updated", "hostile_detections", ["status", "updated_at"], unique=False)

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
    op.create_index("ix_intercept_tasks_hostile_detection_id", "intercept_tasks", ["hostile_detection_id"], unique=False)
    op.create_index("ix_intercept_tasks_operator_station_id", "intercept_tasks", ["operator_station_id"], unique=False)
    op.create_index("ix_intercept_tasks_operator_user_id", "intercept_tasks", ["operator_user_id"], unique=False)
    op.create_index("ix_intercept_tasks_interceptor_drone_id", "intercept_tasks", ["interceptor_drone_id"], unique=False)
    op.create_index("ix_intercept_tasks_status", "intercept_tasks", ["status"], unique=False)
    op.create_index("ix_intercept_task_status_assigned", "intercept_tasks", ["status", "assigned_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_intercept_task_status_assigned", table_name="intercept_tasks")
    op.drop_index("ix_intercept_tasks_status", table_name="intercept_tasks")
    op.drop_index("ix_intercept_tasks_interceptor_drone_id", table_name="intercept_tasks")
    op.drop_index("ix_intercept_tasks_operator_user_id", table_name="intercept_tasks")
    op.drop_index("ix_intercept_tasks_operator_station_id", table_name="intercept_tasks")
    op.drop_index("ix_intercept_tasks_hostile_detection_id", table_name="intercept_tasks")
    op.drop_table("intercept_tasks")

    op.drop_index("ix_hostile_detection_status_updated", table_name="hostile_detections")
    op.drop_index("ix_hostile_detections_status", table_name="hostile_detections")
    op.drop_index("ix_hostile_detections_assigned_operator_station_id", table_name="hostile_detections")
    op.drop_index("ix_hostile_detections_contact_id", table_name="hostile_detections")
    op.drop_index("ix_hostile_detections_recon_drone_uid", table_name="hostile_detections")
    op.drop_table("hostile_detections")

    op.drop_index("ix_operator_stations_name", table_name="operator_stations")
    op.drop_table("operator_stations")

    op.add_column(
        "track_state",
        sa.Column(
            "reason",
            sa.Enum(
                "ok",
                "not_in_registry",
                "bad_signature",
                "replay_detected",
                "clock_skew",
                "no_active_mission",
                "policy_violation",
                "link_lost",
                name="reasoncode",
                native_enum=False,
            ),
            nullable=False,
            server_default="ok",
        ),
    )
    op.add_column("track_state", sa.Column("confidence", sa.Integer(), nullable=False, server_default="100"))
    op.add_column(
        "track_state",
        sa.Column(
            "friend_status",
            sa.Enum(
                "AUTHORIZED",
                "REGISTERED_NOT_AUTHORIZED",
                "UNKNOWN",
                "SUSPICIOUS",
                name="friendstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="AUTHORIZED",
        ),
    )
    op.drop_index("ix_track_state_platform_role", table_name="track_state")
    op.drop_column("track_state", "heading_deg")
    op.drop_column("track_state", "speed_mps")
    op.drop_column("track_state", "platform_role")

    op.add_column("telemetry_events", sa.Column("confidence", sa.Integer(), nullable=False, server_default="100"))
    op.add_column(
        "telemetry_events",
        sa.Column(
            "decision_status",
            sa.Enum(
                "AUTHORIZED",
                "REGISTERED_NOT_AUTHORIZED",
                "UNKNOWN",
                "SUSPICIOUS",
                name="friendstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="AUTHORIZED",
        ),
    )
    op.drop_column("telemetry_events", "platform_role")

    op.drop_index("ix_drones_platform_role", table_name="drones")
    op.drop_column("drones", "platform_role")

    op.create_table(
        "missions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("area_geom", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_missions_starts_at", "missions", ["starts_at"], unique=False)
    op.create_index("ix_missions_ends_at", "missions", ["ends_at"], unique=False)
    op.create_index("ix_missions_window", "missions", ["starts_at", "ends_at"], unique=False)

    op.create_table(
        "mission_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("drone_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["drone_id"], ["drones.id"]),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "drone_id", name="uq_mission_assignment_mission_drone"),
    )
    op.create_index("ix_assignments_mission_id", "mission_assignments", ["mission_id"], unique=False)

    op.create_table(
        "sensor_contact_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sensor_id", sa.String(length=120), nullable=False),
        sa.Column("contact_id", sa.String(length=120), nullable=False),
        sa.Column("track_uid", sa.String(length=120), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt_m", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="sensor"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_contact_events_sensor_id", "sensor_contact_events", ["sensor_id"], unique=False)
    op.create_index("ix_sensor_contact_events_contact_id", "sensor_contact_events", ["contact_id"], unique=False)
    op.create_index("ix_sensor_contact_events_track_uid", "sensor_contact_events", ["track_uid"], unique=False)
    op.create_index(
        "ix_sensor_contacts_sensor_contact_ts",
        "sensor_contact_events",
        ["sensor_id", "contact_id", "timestamp"],
        unique=False,
    )
    op.create_index("ix_sensor_contacts_ts", "sensor_contact_events", ["timestamp"], unique=False)
