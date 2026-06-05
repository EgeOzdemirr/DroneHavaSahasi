"""Add persistent field layers

Revision ID: 20260513_0007
Revises: 20260409_0006
Create Date: 2026-05-13 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260513_0007"
down_revision: Union[str, None] = "20260409_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


field_layer_type_enum = sa.Enum(
    "base_perimeter",
    "safe_corridor",
    "patrol_area",
    "restricted_area",
    "custom",
    name="fieldlayertype",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "field_layers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("layer_type", field_layer_type_enum, nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_field_layers_name", "field_layers", ["name"])
    op.create_index("ix_field_layers_layer_type", "field_layers", ["layer_type"])
    op.create_index("ix_field_layers_is_active", "field_layers", ["is_active"])
    op.create_index("ix_field_layers_created_by", "field_layers", ["created_by"])
    op.create_index("ix_field_layers_type_active", "field_layers", ["layer_type", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_field_layers_type_active", table_name="field_layers")
    op.drop_index("ix_field_layers_created_by", table_name="field_layers")
    op.drop_index("ix_field_layers_is_active", table_name="field_layers")
    op.drop_index("ix_field_layers_layer_type", table_name="field_layers")
    op.drop_index("ix_field_layers_name", table_name="field_layers")
    op.drop_table("field_layers")
