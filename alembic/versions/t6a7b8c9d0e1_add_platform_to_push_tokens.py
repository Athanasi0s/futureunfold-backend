"""add platform to push_tokens

Revision ID: t6a7b8c9d0e1
Revises: s5c6d7e8f9a0
Create Date: 2026-04-16 00:00:00.000000

Phase 13 Plan 02 — PUSH-04 device breakdown depends on this column.
Legacy rows keep NULL until users re-register (happens on every authed app open
via useNotificationListener.ts). No backfill needed.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "t6a7b8c9d0e1"
down_revision = "s5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Προσθήκη nullable platform column — παλαιές εγγραφές μένουν NULL μέχρι
    # την επόμενη εγγραφή από τη συσκευή του χρήστη.
    op.add_column(
        "push_tokens",
        sa.Column("platform", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("push_tokens", "platform")
