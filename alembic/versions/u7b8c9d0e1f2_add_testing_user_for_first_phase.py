"""add TestingUserForFirstPhase table

Revision ID: u7b8c9d0e1f2
Revises: t6a7b8c9d0e1
Create Date: 2026-04-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "u7b8c9d0e1f2"
down_revision = "t6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "TestingUserForFirstPhase",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_TestingUserForFirstPhase_user_id"),
        "TestingUserForFirstPhase",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_TestingUserForFirstPhase_user_id"),
        table_name="TestingUserForFirstPhase",
    )
    op.drop_table("TestingUserForFirstPhase")
