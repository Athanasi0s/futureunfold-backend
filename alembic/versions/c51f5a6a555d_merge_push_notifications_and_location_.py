"""merge_push_notifications_and_location_heads

Revision ID: c51f5a6a555d
Revises: 0f2150774064, a1b2c3d4e5f6
Create Date: 2026-03-09 18:23:26.422550

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c51f5a6a555d'
down_revision: Union[str, None] = ('0f2150774064', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
