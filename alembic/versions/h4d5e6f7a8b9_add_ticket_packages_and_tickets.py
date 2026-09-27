"""add ticket_packages and tickets tables

Revision ID: h4d5e6f7a8b9
Revises: g3c4a1b2d5e6
Create Date: 2026-03-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'h4d5e6f7a8b9'
down_revision: Union[str, None] = 'g3c4a1b2d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ticket_status enum
    ticket_status = postgresql.ENUM('active', 'used', 'cancelled', name='ticket_status', create_type=False)
    ticket_status.create(op.get_bind(), checkfirst=True)

    # Create ticket_packages table
    op.create_table(
        'ticket_packages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ref_key', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('price_eur', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('stripe_price_id', sa.String(), nullable=False),
        sa.Column('max_quantity', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ref_key'),
    )
    op.create_index(op.f('ix_ticket_packages_id'), 'ticket_packages', ['id'], unique=False)

    # Create tickets table
    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('package_id', sa.Integer(), nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=False),
        sa.Column('qr_code', sa.String(), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'used', 'cancelled', name='ticket_status', create_type=False), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['package_id'], ['ticket_packages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('qr_code'),
        sa.UniqueConstraint('stripe_payment_intent_id'),
    )
    op.create_index(op.f('ix_tickets_id'), 'tickets', ['id'], unique=False)
    op.create_index(op.f('ix_tickets_user_id'), 'tickets', ['user_id'], unique=False)
    op.create_index(op.f('ix_tickets_package_id'), 'tickets', ['package_id'], unique=False)
    op.create_index(op.f('ix_tickets_stripe_payment_intent_id'), 'tickets', ['stripe_payment_intent_id'], unique=True)
    op.create_index(op.f('ix_tickets_qr_code'), 'tickets', ['qr_code'], unique=True)


def downgrade() -> None:
    op.drop_table('tickets')
    op.drop_table('ticket_packages')
    sa.Enum(name='ticket_status').drop(op.get_bind(), checkfirst=True)
