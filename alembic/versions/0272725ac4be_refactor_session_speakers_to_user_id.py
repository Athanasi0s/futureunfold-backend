"""refactor_session_speakers_to_user_id

Revision ID: 0272725ac4be
Revises: 156d600e4c84
Create Date: 2026-01-30 00:35:03.441730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0272725ac4be'
down_revision: Union[str, None] = '156d600e4c84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old constraint and index
    op.drop_constraint('uq_session_speaker', 'session_speakers', type_='unique')
    op.drop_constraint('session_speakers_speaker_id_fkey', 'session_speakers', type_='foreignkey')
    op.drop_index('ix_session_speakers_speaker_id', table_name='session_speakers')
    
    # Rename speaker_id to user_id
    op.alter_column('session_speakers', 'speaker_id', new_column_name='user_id')
    
    # Update data: convert speaker_id (from speakers table) to user_id
    # speakers.id -> speakers.user_id
    op.execute("""
        UPDATE session_speakers ss
        SET user_id = s.user_id
        FROM speakers s
        WHERE ss.user_id = s.id
    """)
    
    # Add new FK constraint to users table
    op.create_foreign_key(
        'session_speakers_user_id_fkey',
        'session_speakers',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Add new unique constraint and index
    op.create_unique_constraint('uq_session_user', 'session_speakers', ['session_id', 'user_id'])
    op.create_index('ix_session_speakers_user_id', 'session_speakers', ['user_id'])


def downgrade() -> None:
    # Reverse the migration
    op.drop_constraint('uq_session_user', 'session_speakers', type_='unique')
    op.drop_constraint('session_speakers_user_id_fkey', 'session_speakers', type_='foreignkey')
    op.drop_index('ix_session_speakers_user_id', table_name='session_speakers')
    
    op.alter_column('session_speakers', 'user_id', new_column_name='speaker_id')
    
    # Note: downgrade won't restore the original speaker_id values
    op.create_foreign_key(
        'session_speakers_speaker_id_fkey',
        'session_speakers',
        'speakers',
        ['speaker_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_unique_constraint('uq_session_speaker', 'session_speakers', ['session_id', 'speaker_id'])
    op.create_index('ix_session_speakers_speaker_id', 'session_speakers', ['speaker_id'])
