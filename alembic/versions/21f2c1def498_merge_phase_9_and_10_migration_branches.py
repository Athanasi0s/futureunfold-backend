"""merge phase 9 and 10 migration branches

Revision ID: 21f2c1def498
Revises: 9d71c2c8772e, p2f3a4b5c6d7
Create Date: 2026-04-15 02:04:26.008780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21f2c1def498'
down_revision: Union[str, None] = ('9d71c2c8772e', 'p2f3a4b5c6d7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
