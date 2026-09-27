"""add admin_notes to user_reports

Revision ID: n0d1e2f3a4b5
Revises: m9c0d1e2f3a4
Create Date: 2026-03-27 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "n0d1e2f3a4b5"
down_revision: Union[str, None] = "m9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_reports", sa.Column("admin_notes", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_reports", "admin_notes")
