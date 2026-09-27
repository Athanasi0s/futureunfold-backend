"""add token_version to users and seed moderator_permissions

Revision ID: r4b5c6d7e8f9
Revises: q3a4b5c6d7e8
Create Date: 2026-04-15

Second of the two Phase 11 migrations. Plan 01's Revision A
(`q3a4b5c6d7e8`) added the `'moderator'` value to the `user_roles` enum.
This Revision B adds the `token_version` column on `users` (required
for the JWT invalidation mechanism in `deps.get_current_user`) and
seeds the `moderator_permissions` AppConfig row with all three scope
keys set to False. The seed uses `ON CONFLICT (key) DO NOTHING` so
re-runs or pre-existing rows are safe.

Ships in the same Fly.io deploy as the backend RBAC code that
references `UserRole.moderator` (safe because Revision A already added
that enum value to production in a prior, separate release).

NOTE: The `revision` identifier is kept to 12 chars to fit the
Postgres `alembic_version.version_num VARCHAR(32)` column — see Plan 01
summary for the failure mode when this limit is exceeded.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
# Short 12-char id — must fit alembic_version.version_num VARCHAR(32).
revision: str = "r4b5c6d7e8f9"
down_revision: Union[str, None] = "q3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add token_version column, NOT NULL with server default 0.
    # The server_default backfills all existing rows to 0 atomically.
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # 2) Seed the global moderator_permissions AppConfig row.
    # ON CONFLICT makes this idempotent; if the row already exists from
    # any prior environment-specific seeding, we leave its value alone.
    op.execute(
        """
        INSERT INTO app_config (key, value)
        VALUES (
            'moderator_permissions',
            '{"validate_ticket": false, "ticket_packages": false, "user_reports": false}'::jsonb
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM app_config WHERE key = 'moderator_permissions'")
    op.drop_column("users", "token_version")
