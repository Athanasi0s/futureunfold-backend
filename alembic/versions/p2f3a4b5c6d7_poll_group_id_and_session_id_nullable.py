"""poll group_id and session_id nullable

Revision ID: p2f3a4b5c6d7
Revises: o1e2f3a4b5c6
Create Date: 2026-04-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "p2f3a4b5c6d7"
down_revision: Union[str, None] = "o1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make session_id nullable (polls can now belong to a group instead)
    op.alter_column("polls", "session_id", nullable=True)

    # Add group_id FK column
    op.add_column(
        "polls",
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_polls_group_id"), "polls", ["group_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_polls_group_id"), table_name="polls")
    op.drop_column("polls", "group_id")
    op.alter_column("polls", "session_id", nullable=False)
