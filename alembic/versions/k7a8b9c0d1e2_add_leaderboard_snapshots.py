"""add leaderboard_snapshots table

Revision ID: k7a8b9c0d1e2
Revises: j6f7a8b9c0d1
Create Date: 2026-03-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k7a8b9c0d1e2"
down_revision: Union[str, None] = "j6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leaderboard_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_date", "category", "user_id",
            name="uq_snapshot_date_cat_user",
        ),
    )
    op.create_index("ix_snapshot_date_category", "leaderboard_snapshots", ["snapshot_date", "category"])
    op.create_index(op.f("ix_leaderboard_snapshots_user_id"), "leaderboard_snapshots", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_leaderboard_snapshots_user_id"), table_name="leaderboard_snapshots")
    op.drop_index("ix_snapshot_date_category", table_name="leaderboard_snapshots")
    op.drop_table("leaderboard_snapshots")
