"""merge palettes-reports migration branch

Revision ID: 9d71c2c8772e
Revises: 3650c153fca7, n0d1e2f3a4b5
Create Date: 2026-03-27 18:01:34.917693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d71c2c8772e'
down_revision: Union[str, None] = ('3650c153fca7', 'n0d1e2f3a4b5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
