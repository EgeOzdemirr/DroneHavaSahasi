"""Initial schema

Revision ID: 20260305_0001
Revises:
Create Date: 2026-03-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260305_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("admin", "operator", "viewer", name="userrole", native_enum=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    op.create_table(
        "drone_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key_id", sa.String(length=120), nullable=False),
        sa.Column(
            "algo",
            sa.Enum("hmac-sha256-v1", name="signaturealgorithm", native_enum=False),
            nullable=False,
            server_default="hmac-sha256-v1",
        ),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("active", "inactive", name="keystatus", native_enum=False), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id"),
    )
    op.create_index("ix_drone_keys_key_id", "drone_keys", ["key_id"], unique=False)

    op.create_table(
        "drones",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("drone_uid", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=120), nullable=False),
        sa.Column("status", sa.Enum("active", "inactive", name="dronestatus", native_enum=False), nullable=False, server_default="active"),
        sa.Column("key_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["drone_keys.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("drone_uid"),
    )

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
        "telemetry_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drone_uid", sa.String(length=120), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt_m", sa.Float(), nullable=False),
        sa.Column("speed_mps", sa.Float(), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="drone"),
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        ),
        sa.Column(
            "reason_code",
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
        ),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("ingest_source", sa.String(length=120), nullable=False, server_default="http"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telemetry_events_drone_uid", "telemetry_events", ["drone_uid"], unique=False)
    op.create_index("ix_telemetry_drone_timestamp", "telemetry_events", ["drone_uid", "timestamp"], unique=False)
    op.create_index("ix_telemetry_timestamp", "telemetry_events", ["timestamp"], unique=False)

    op.create_table(
        "track_state",
        sa.Column("drone_uid", sa.String(length=120), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt_m", sa.Float(), nullable=False),
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
        ),
        sa.Column("confidence", sa.Integer(), nullable=False),
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
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("drone_uid"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("drone_uid", sa.String(length=120), nullable=False),
        sa.Column("alert_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.Enum("open", "ack", "resolved", name="alertstatus", native_enum=False), nullable=False, server_default="open"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "reason_code",
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
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["acked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_drone_uid", "alerts", ["drone_uid"], unique=False)
    op.create_index("ix_alerts_status_created", "alerts", ["status", "created_at"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_username", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_actor_username", "audit_log", ["actor_username"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor_username", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_alerts_status_created", table_name="alerts")
    op.drop_index("ix_alerts_drone_uid", table_name="alerts")
    op.drop_table("alerts")

    op.drop_table("track_state")

    op.drop_index("ix_telemetry_timestamp", table_name="telemetry_events")
    op.drop_index("ix_telemetry_drone_timestamp", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_drone_uid", table_name="telemetry_events")
    op.drop_table("telemetry_events")

    op.drop_index("ix_assignments_mission_id", table_name="mission_assignments")
    op.drop_table("mission_assignments")

    op.drop_index("ix_missions_window", table_name="missions")
    op.drop_index("ix_missions_ends_at", table_name="missions")
    op.drop_index("ix_missions_starts_at", table_name="missions")
    op.drop_table("missions")

    op.drop_table("drones")

    op.drop_index("ix_drone_keys_key_id", table_name="drone_keys")
    op.drop_table("drone_keys")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

