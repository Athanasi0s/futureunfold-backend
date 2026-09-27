"""add report details and status columns

Revision ID: m9c0d1e2f3a4
Revises: l8b9c0d1e2f3
Create Date: 2026-03-27 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m9c0d1e2f3a4"
down_revision: Union[str, None] = "l8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_reports", sa.Column("details", sa.String(500), nullable=True))
    op.add_column(
        "user_reports",
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
    )


def downgrade() -> None:
    op.drop_column("user_reports", "status")
    op.drop_column("user_reports", "details")
