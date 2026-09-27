"""add google_calendar_tokens table

Revision ID: g3c4a1b2d5e6
Revises: c51f5a6a555d
Create Date: 2026-03-09 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g3c4a1b2d5e6'
down_revision: Union[str, None] = 'c51f5a6a555d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'google_calendar_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('access_token', sa.String(), nullable=False),
        sa.Column('refresh_token', sa.String(), nullable=False),
        sa.Column('token_expiry', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_valid', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_google_calendar_tokens_id'), 'google_calendar_tokens', ['id'], unique=False)
    op.create_index(op.f('ix_google_calendar_tokens_user_id'), 'google_calendar_tokens', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_google_calendar_tokens_user_id'), table_name='google_calendar_tokens')
    op.drop_index(op.f('ix_google_calendar_tokens_id'), table_name='google_calendar_tokens')
    op.drop_table('google_calendar_tokens')
