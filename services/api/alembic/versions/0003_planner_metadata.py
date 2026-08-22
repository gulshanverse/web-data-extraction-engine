"""phase 4 planner metadata

Revision ID: 0003_planner_metadata
Revises: 0002_browser_metadata
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_planner_metadata"
down_revision = "0002_browser_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("extraction_plans", sa.Column("provider_name", sa.String(length=100)))
    op.add_column("extraction_plans", sa.Column("schema_version", sa.String(length=40)))
    op.add_column("extraction_plans", sa.Column("prompt_version", sa.String(length=80)))
    op.add_column("extraction_plans", sa.Column("plan_hash", sa.String(length=128)))
    op.create_index("ix_plans_job_hash", "extraction_plans", ["job_id", "plan_hash"])


def downgrade() -> None:
    op.drop_index("ix_plans_job_hash", table_name="extraction_plans")
    op.drop_column("extraction_plans", "plan_hash")
    op.drop_column("extraction_plans", "prompt_version")
    op.drop_column("extraction_plans", "schema_version")
    op.drop_column("extraction_plans", "provider_name")
