"""add notification_preferences and group_suggestions_sent

Revision ID: j6f7a8b9c0d1
Revises: i5e6f7a8b9c0
Create Date: 2026-03-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j6f7a8b9c0d1"
down_revision: Union[str, None] = "i5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category", name="uq_user_notif_pref"),
    )
    op.create_index(op.f("ix_notification_preferences_user_id"), "notification_preferences", ["user_id"], unique=False)

    op.create_table(
        "group_suggestions_sent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "group_id", name="uq_group_suggestion_sent"),
    )
    op.create_index(op.f("ix_group_suggestions_sent_user_id"), "group_suggestions_sent", ["user_id"], unique=False)
    op.create_index(op.f("ix_group_suggestions_sent_group_id"), "group_suggestions_sent", ["group_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_group_suggestions_sent_group_id"), table_name="group_suggestions_sent")
    op.drop_index(op.f("ix_group_suggestions_sent_user_id"), table_name="group_suggestions_sent")
    op.drop_table("group_suggestions_sent")
    op.drop_index(op.f("ix_notification_preferences_user_id"), table_name="notification_preferences")
    op.drop_table("notification_preferences")
