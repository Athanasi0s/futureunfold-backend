"""merge_migration_heads

Revision ID: 6f3246840607
Revises: 864b664bfe45, c8c773a92987
Create Date: 2026-03-05 16:37:34.952852

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f3246840607'
down_revision: Union[str, None] = ('864b664bfe45', 'c8c773a92987')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
