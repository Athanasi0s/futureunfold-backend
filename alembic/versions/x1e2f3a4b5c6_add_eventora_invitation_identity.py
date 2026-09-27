"""add EVENTORA invitation identity and one-time redemption records

Revision ID: x1e2f3a4b5c6
Revises: w9d0e1f2a3b4
Create Date: 2026-09-21 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "x1e2f3a4b5c6"
down_revision = "w9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("eventora_invitation_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("eventora_qr_code", sa.String(), nullable=True))
    op.create_index(
        "ix_users_eventora_invitation_id",
        "users",
        ["eventora_invitation_id"],
        unique=True,
    )
    op.create_index(
        "ix_users_eventora_qr_code",
        "users",
        ["eventora_qr_code"],
        unique=True,
    )
    op.create_table(
        "eventora_magic_link_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("invitation_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "redeemed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eventora_magic_link_redemptions_jti_hash",
        "eventora_magic_link_redemptions",
        ["jti_hash"],
        unique=True,
    )
    op.create_index(
        "ix_eventora_magic_link_redemptions_invitation_id",
        "eventora_magic_link_redemptions",
        ["invitation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eventora_magic_link_redemptions_invitation_id",
        table_name="eventora_magic_link_redemptions",
    )
    op.drop_index(
        "ix_eventora_magic_link_redemptions_jti_hash",
        table_name="eventora_magic_link_redemptions",
    )
    op.drop_table("eventora_magic_link_redemptions")
    op.drop_index("ix_users_eventora_qr_code", table_name="users")
    op.drop_index("ix_users_eventora_invitation_id", table_name="users")
    op.drop_column("users", "eventora_qr_code")
    op.drop_column("users", "eventora_invitation_id")
