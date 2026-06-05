"""Add sensor contact events table

Revision ID: 20260312_0004
Revises: 20260311_0003
Create Date: 2026-03-12 09:50:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260312_0004"
down_revision: Union[str, None] = "20260311_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_sensor_contacts_ts", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contacts_sensor_contact_ts", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contact_events_track_uid", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contact_events_contact_id", table_name="sensor_contact_events")
    op.drop_index("ix_sensor_contact_events_sensor_id", table_name="sensor_contact_events")
    op.drop_table("sensor_contact_events")

