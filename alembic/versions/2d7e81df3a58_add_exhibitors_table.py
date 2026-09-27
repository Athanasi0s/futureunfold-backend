"""add_exhibitors_table

Revision ID: 2d7e81df3a58
Revises: 39d18624946b
Create Date: 2026-01-29 22:15:17.604491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d7e81df3a58'
down_revision: Union[str, None] = '39d18624946b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create exhibitors table
    op.create_table(
        'exhibitors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('booth_code', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_exhibitors_user_id'), 'exhibitors', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_exhibitors_user_id'), table_name='exhibitors')
    op.drop_table('exhibitors')
