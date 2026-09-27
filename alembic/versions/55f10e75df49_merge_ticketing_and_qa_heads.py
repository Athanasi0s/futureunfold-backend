"""merge ticketing and qa heads

Revision ID: 55f10e75df49
Revises: dff922812e5c, h4d5e6f7a8b9
Create Date: 2026-03-11 22:30:38.125370

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55f10e75df49'
down_revision: Union[str, None] = ('dff922812e5c', 'h4d5e6f7a8b9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
