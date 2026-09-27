"""add user theme_preference

Revision ID: l8b9c0d1e2f3
Revises: k7a8b9c0d1e2
Create Date: 2026-03-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "l8b9c0d1e2f3"
down_revision: Union[str, None] = "k7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("theme_preference", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "theme_preference")
