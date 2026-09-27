"""rename panathenea-electric theme preset to electric-blue

Data-only migration paired with festapp-mobile#18, which renamed the preset
id in `constants/theme-presets.ts`. Rewrites every place the old id can be
stored in the database so admins and users don't need to re-pick the theme:

  1. `app_config` row for `active_theme_preset_id` (JSON scalar string)
  2. `app_config` row for `user_theme_options` (JSON array containing the id)
  3. `users.theme_preference` column (plain string)

Idempotent: all three UPDATEs are guarded by exact-match filters, so re-
running on a DB that has already been migrated is a no-op.

Revision ID: v8c9d0e1f2a3
Revises: u7b8c9d0e1f2
Create Date: 2026-04-21 00:00:00.000000
"""
from alembic import op

revision = "v8c9d0e1f2a3"
down_revision = "u7b8c9d0e1f2"
branch_labels = None
depends_on = None


OLD_ID = "panathenea-electric"
NEW_ID = "electric-blue"


def upgrade() -> None:
    # 1. app_config.active_theme_preset_id — JSON scalar string
    op.execute(
        f"""
        UPDATE app_config
        SET value = '"{NEW_ID}"'::jsonb
        WHERE key = 'active_theme_preset_id'
          AND value = '"{OLD_ID}"'::jsonb
        """
    )

    # 2. app_config.user_theme_options — JSON array containing the id.
    # Rebuild the array with each element swapped only when it equals OLD_ID.
    op.execute(
        f"""
        UPDATE app_config
        SET value = (
            SELECT jsonb_agg(
                CASE
                    WHEN elem = '"{OLD_ID}"'::jsonb THEN '"{NEW_ID}"'::jsonb
                    ELSE elem
                END
            )
            FROM jsonb_array_elements(value) AS elem
        )
        WHERE key = 'user_theme_options'
          AND value @> '["{OLD_ID}"]'::jsonb
        """
    )

    # 3. users.theme_preference — plain string column
    op.execute(
        f"""
        UPDATE users
        SET theme_preference = '{NEW_ID}'
        WHERE theme_preference = '{OLD_ID}'
        """
    )


def downgrade() -> None:
    # Symmetric rewrite back to the old id, should anyone ever need to roll
    # back (the mobile alias in festapp-mobile#18 kept the old id working at
    # runtime, so a rollback is survivable).
    op.execute(
        f"""
        UPDATE app_config
        SET value = '"{OLD_ID}"'::jsonb
        WHERE key = 'active_theme_preset_id'
          AND value = '"{NEW_ID}"'::jsonb
        """
    )

    op.execute(
        f"""
        UPDATE app_config
        SET value = (
            SELECT jsonb_agg(
                CASE
                    WHEN elem = '"{NEW_ID}"'::jsonb THEN '"{OLD_ID}"'::jsonb
                    ELSE elem
                END
            )
            FROM jsonb_array_elements(value) AS elem
        )
        WHERE key = 'user_theme_options'
          AND value @> '["{NEW_ID}"]'::jsonb
        """
    )

    op.execute(
        f"""
        UPDATE users
        SET theme_preference = '{OLD_ID}'
        WHERE theme_preference = '{NEW_ID}'
        """
    )
