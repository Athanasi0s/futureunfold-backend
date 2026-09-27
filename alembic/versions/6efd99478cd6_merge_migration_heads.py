"""merge migration heads

Revision ID: 6efd99478cd6
Revises: 0272725ac4be, ce5c5e59b8ce
Create Date: 2026-01-31 22:39:59.297154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6efd99478cd6'
down_revision: Union[str, None] = ('0272725ac4be', 'ce5c5e59b8ce')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
