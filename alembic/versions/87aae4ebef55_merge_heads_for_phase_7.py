"""merge heads for phase 7

Revision ID: 87aae4ebef55
Revises: c6cb6d73e0e2, j6f7a8b9c0d1
Create Date: 2026-03-14 17:13:09.910354

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87aae4ebef55'
down_revision: Union[str, None] = ('c6cb6d73e0e2', 'j6f7a8b9c0d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
