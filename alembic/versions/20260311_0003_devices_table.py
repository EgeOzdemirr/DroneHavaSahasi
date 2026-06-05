"""Add devices table for v2 device management

Revision ID: 20260311_0003
Revises: 20260311_0002
Create Date: 2026-03-11 17:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260311_0003"
down_revision: Union[str, None] = "20260311_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("drone_id", sa.String(length=36), nullable=False),
        sa.Column("cert_fingerprint", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", name="devicestatus", native_enum=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_reason", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["drone_id"], ["drones.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index("ix_devices_device_id", "devices", ["device_id"], unique=False)
    op.create_index("ix_devices_drone_id", "devices", ["drone_id"], unique=False)
    op.create_index("ix_devices_status", "devices", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_devices_status", table_name="devices")
    op.drop_index("ix_devices_drone_id", table_name="devices")
    op.drop_index("ix_devices_device_id", table_name="devices")
    op.drop_table("devices")

