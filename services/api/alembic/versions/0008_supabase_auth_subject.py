"""Add a durable Supabase Auth subject mapping without changing ownership relations.

Revision ID: 0008_supabase_auth_subject
Revises: 0007_export_lifecycle_metadata
"""

import sqlalchemy as sa
from alembic import op


revision = "0008_supabase_auth_subject"
down_revision = "0007_export_lifecycle_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_subject", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_auth_subject", "users", ["auth_subject"])


def downgrade() -> None:
    op.drop_constraint("uq_users_auth_subject", "users", type_="unique")
    op.drop_column("users", "auth_subject")
