"""add is_cancelled and cancelled_at to sessions

Revision ID: s5c6d7e8f9a0
Revises: r4b5c6d7e8f9
Create Date: 2026-04-15

Phase 12 Plan 01 (D-01): add a soft-cancel flag + timestamp to `sessions`.
`is_cancelled` has a server_default of false so existing rows backfill to
false on migration without a separate data migration step. `cancelled_at`
is nullable and populated by the application layer when cancellation
actually occurs (Plan 02 POST /admin/sessions/{id}/cancel).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s5c6d7e8f9a0"
down_revision: Union[str, None] = "r4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "is_cancelled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "cancelled_at")
    op.drop_column("sessions", "is_cancelled")
