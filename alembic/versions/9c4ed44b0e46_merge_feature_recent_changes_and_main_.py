"""merge feature/recent-changes and main heads

Revision ID: 9c4ed44b0e46
Revises: 43173707aa26, 644b1ae24542
Create Date: 2026-02-10 21:23:45.556607

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c4ed44b0e46'
down_revision: Union[str, None] = ('43173707aa26', '644b1ae24542')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
