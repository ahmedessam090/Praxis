"""add screener groups (custom-groups model)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-16 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.add_column(
        "screener_candidates",
        sa.Column("group_name", sa.String(length=64), server_default="", nullable=False),
    )
    op.create_index(
        "ix_screener_candidates_group_name", "screener_candidates", ["group_name"]
    )
    op.create_table(
        "screener_groups",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="custom", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("screener_groups")
    op.drop_index("ix_screener_candidates_group_name", table_name="screener_candidates")
    op.drop_column("screener_candidates", "group_name")
