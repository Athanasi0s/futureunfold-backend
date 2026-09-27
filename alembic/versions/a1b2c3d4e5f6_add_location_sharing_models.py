"""add location sharing models

Revision ID: a1b2c3d4e5f6
Revises: 6f3246840607
Create Date: 2026-03-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6f3246840607'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create location_shares table
    op.create_table(
        'location_shares',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'group_id', name='uq_location_share_user_group'),
    )
    op.create_index(op.f('ix_location_shares_user_id'), 'location_shares', ['user_id'])
    op.create_index(op.f('ix_location_shares_group_id'), 'location_shares', ['group_id'])

    # Add sharing_location column to group_members
    op.add_column('group_members', sa.Column('sharing_location', sa.Boolean(), server_default='false', nullable=False))

    # Add capacity column to venues
    op.add_column('venues', sa.Column('capacity', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('venues', 'capacity')
    op.drop_column('group_members', 'sharing_location')
    op.drop_index(op.f('ix_location_shares_group_id'), table_name='location_shares')
    op.drop_index(op.f('ix_location_shares_user_id'), table_name='location_shares')
    op.drop_table('location_shares')
