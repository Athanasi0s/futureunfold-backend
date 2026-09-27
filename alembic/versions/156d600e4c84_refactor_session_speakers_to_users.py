"""refactor_session_speakers_to_users

Revision ID: 156d600e4c84
Revises: 2d7e81df3a58
Create Date: 2026-01-30 00:24:18.433241

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '156d600e4c84'
down_revision: Union[str, None] = '2d7e81df3a58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
