"""Add user password reset flags

Revision ID: 20260311_0002
Revises: 20260305_0001
Create Date: 2026-03-11 13:00:00.000000
"""

from typing import Sequence, Union
import os

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260311_0002"
down_revision: Union[str, None] = "20260305_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )

    bootstrap_username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    users = sa.table(
        "users",
        sa.column("username", sa.String(length=120)),
        sa.column("must_change_password", sa.Boolean()),
    )
    op.execute(
        users.update()
        .where(users.c.username == bootstrap_username)
        .values(must_change_password=True)
    )

    op.alter_column("users", "must_change_password", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "must_change_password")
