"""add user role enum

Revision ID: b0c0d2_add_user_role_enum
Revises: 0003
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b0c0d2_add_user_role_enum'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # Create the Enum type in Postgres
    op.execute("CREATE TYPE user_roles AS ENUM ('attendee', 'speaker', 'exhibitor', 'admin')")
    
    # Alter the column to use the new type
    # First, removing server default to avoid issues during type conversion if needed
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    
    # Convert role column to the new Enum type using the USING clause
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_roles USING role::user_roles")
    
    # Restore server default
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'attendee'")


def downgrade():
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR USING role::text")
    op.execute("DROP TYPE user_roles")
