"""add demographics to users

Revision ID: o1e2f3a4b5c6
Revises: n0d1e2f3a4b5
Create Date: 2026-04-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "o1e2f3a4b5c6"
down_revision: Union[str, None] = "n0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "gender")
    op.drop_column("users", "date_of_birth")
