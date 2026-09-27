"""make users.full_name NOT NULL

A speaker-role user with full_name = NULL reached production via a seed
script that wrote directly to the DB (bypassing RegisterIn validation
entirely), and crashed the mobile app's initials rendering (.charAt(0) on
null) in every screen that lists users. RegisterIn.full_name was already
Optional, and PATCH /me let a client explicitly null out their own name too
- neither gap is closed by mobile-side validation, since seed scripts and
admin tooling write straight to the DB. Adding the constraint here is the
one fix that actually holds regardless of code path.

Backfills any existing NULLs (falls back to the email local-part) before
adding the constraint, since ALTER COLUMN ... SET NOT NULL fails outright
if any row still violates it.

Revision ID: w9d0e1f2a3b4
Revises: v8c9d0e1f2a3
Create Date: 2026-07-23 00:00:00.000000
"""
from alembic import op

revision = "w9d0e1f2a3b4"
down_revision = "v8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET full_name = split_part(email, '@', 1)
        WHERE full_name IS NULL
        """
    )
    op.alter_column("users", "full_name", nullable=False)


def downgrade() -> None:
    op.alter_column("users", "full_name", nullable=True)
