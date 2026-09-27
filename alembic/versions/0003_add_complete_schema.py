"""add_complete_schema

Revision ID: 0003
Revises: a00cd5929ba4
Create Date: 2026-01-25

Adds:
- User fields: linkedin_url, avatar_url, bio, company, last_seen
- Speakers table
- Sessions table
- Session_speakers table
- User_agenda table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = 'a00cd5929ba4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add missing columns to users
    op.add_column('users', sa.Column('linkedin_url', sa.String(), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(), nullable=True))
    op.add_column('users', sa.Column('bio', sa.String(), nullable=True))
    op.add_column('users', sa.Column('company', sa.String(), nullable=True))
    op.add_column('users', sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    
    # 2. Speakers table
    op.create_table(
        'speakers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_speakers_user_id'), 'speakers', ['user_id'], unique=True)
    
    # 3. Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('venue_id', sa.Integer(), nullable=True),
        sa.Column('map_feature_id', sa.Integer(), nullable=True),
        sa.Column('slides_url', sa.String(length=500), nullable=True),
        sa.Column('slides_unlocked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('poll_id', sa.String(length=255), nullable=True),
        sa.Column('topic_tags', postgresql.ARRAY(sa.String(length=100)), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['venue_id'], ['venues.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['map_feature_id'], ['map_features.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sessions_start_time'), 'sessions', ['start_time'], unique=False)
    op.create_index(op.f('ix_sessions_venue_id'), 'sessions', ['venue_id'], unique=False)
    op.create_index(op.f('ix_sessions_map_feature_id'), 'sessions', ['map_feature_id'], unique=False)
    
    # 4. Session-Speaker join table
    op.create_table(
        'session_speakers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('speaker_id', sa.Integer(), nullable=False),
        sa.Column('is_moderator', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['speaker_id'], ['speakers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'speaker_id', name='uq_session_speaker'),
    )
    op.create_index(op.f('ix_session_speakers_session_id'), 'session_speakers', ['session_id'], unique=False)
    op.create_index(op.f('ix_session_speakers_speaker_id'), 'session_speakers', ['speaker_id'], unique=False)
    
    # 5. User Agenda
    op.create_table(
        'user_agenda',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'session_id', name='uq_user_agenda'),
    )
    op.create_index(op.f('ix_user_agenda_user_id'), 'user_agenda', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_agenda_session_id'), 'user_agenda', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_table('user_agenda')
    op.drop_table('session_speakers')
    op.drop_table('sessions')
    op.drop_table('speakers')
    op.drop_column('users', 'last_seen')
    op.drop_column('users', 'company')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'linkedin_url')
