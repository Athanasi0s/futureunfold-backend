"""merge speakers and rewards branches

Revision ID: 43173707aa26
Revises: 0f27203c2b2d, e9175373026b
Create Date: 2026-02-07 16:11:58.926479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43173707aa26'
down_revision: Union[str, None] = ('0f27203c2b2d', 'e9175373026b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
