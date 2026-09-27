"""add moderator to user_roles enum

Revision ID: q3a4b5c6d7e8
Revises: 21f2c1def498
Create Date: 2026-04-15

This revision extends the PostgreSQL `user_roles` enum with the value
'moderator'. PostgreSQL forbids `ALTER TYPE ... ADD VALUE` inside a
transaction block, so we wrap the statement in Alembic's
`autocommit_block()` which runs the DDL outside the alembic-managed
transaction. The `IF NOT EXISTS` guard makes this migration idempotent
and safe to re-run.

This revision contains ONLY the enum extension. The accompanying
`token_version` column and backend RBAC code ships in a separate
Alembic revision + Fly.io release (Plan 02), because bundling this DDL
with any other schema change or with code that references
`UserRole.moderator` risks LookupError if the enum value commits after
the code references it. Two-revision, two-deploy sequencing is the
only safe path.

NOTE: The `revision` identifier is kept to 12 chars to fit Postgres
`alembic_version.version_num` which is declared VARCHAR(32). An earlier
deploy attempt (commit 8e68c77) used the full filename as the revision
id (51 chars) which succeeded at running the ALTER TYPE inside the
autocommit block but then failed at the subsequent UPDATE of
alembic_version with psycopg2 StringDataRightTruncation. On retry with
the shortened id below, the ALTER TYPE is a no-op (IF NOT EXISTS
guard) and the alembic head update fits the column width.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
# Short 12-char id — must fit alembic_version.version_num VARCHAR(32).
revision: str = "q3a4b5c6d7e8"
down_revision: Union[str, None] = "21f2c1def498"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL forbids ALTER TYPE ... ADD VALUE inside a transaction.
    # autocommit_block() runs this statement outside the alembic-managed txn.
    # IF NOT EXISTS makes the migration idempotent.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_roles ADD VALUE IF NOT EXISTS 'moderator'")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE statement. Removing an
    # enum value would require recreating the type and migrating all
    # referencing rows. Downgrade is intentionally unsupported in v1.
    pass
