"""phase 5 discovery inventory

Revision ID: 0004_discovery_inventory
Revises: 0003_planner_metadata
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_discovery_inventory"
down_revision = "0003_planner_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("discovered_via", sa.String(length=40)))
    op.add_column("pages", sa.Column("depth", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pages", sa.Column("parent_page_id", sa.UUID()))
    op.create_foreign_key("fk_pages_parent_page", "pages", "pages", ["parent_page_id"], ["id"], ondelete="SET NULL")
    op.add_column("pages", sa.Column("deduplication_key", sa.String(length=128)))
    op.add_column("pages", sa.Column("policy_decision", sa.String(length=80)))
    op.add_column("pages", sa.Column("relevance_score", sa.Float()))
    op.add_column("pages", sa.Column("relevance_reason", sa.String(length=500)))
    op.add_column("pages", sa.Column("discovery_metadata", sa.JSON()))
    op.add_column("pages", sa.Column("visited_at", sa.DateTime(timezone=True)))
    op.create_index("ix_pages_job_depth", "pages", ["job_id", "depth"])
    op.create_index("ix_pages_job_discovery_status", "pages", ["job_id", "status"])
    op.create_index("ix_pages_deduplication_key", "pages", ["deduplication_key"])
    op.alter_column("pages", "depth", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_pages_deduplication_key", table_name="pages")
    op.drop_index("ix_pages_job_discovery_status", table_name="pages")
    op.drop_index("ix_pages_job_depth", table_name="pages")
    op.drop_column("pages", "visited_at")
    op.drop_column("pages", "discovery_metadata")
    op.drop_column("pages", "relevance_reason")
    op.drop_column("pages", "relevance_score")
    op.drop_column("pages", "policy_decision")
    op.drop_column("pages", "deduplication_key")
    op.drop_constraint("fk_pages_parent_page", "pages", type_="foreignkey")
    op.drop_column("pages", "parent_page_id")
    op.drop_column("pages", "depth")
    op.drop_column("pages", "discovered_via")
