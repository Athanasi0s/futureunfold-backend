"""merge scheduling and polls migrations

Revision ID: d41dff57c3e7
Revises: 5f3820d1005c, 6efd99478cd6
Create Date: 2026-02-04 09:50:05.298098

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd41dff57c3e7'
down_revision: Union[str, None] = ('5f3820d1005c', '6efd99478cd6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
