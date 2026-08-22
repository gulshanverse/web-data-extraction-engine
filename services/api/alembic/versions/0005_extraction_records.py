"""phase 6 extraction records

Revision ID: 0005_extraction_records
Revises: 0004_discovery_inventory
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_extraction_records"
down_revision = "0004_discovery_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("extraction_status", sa.String(length=32)))
    op.add_column("pages", sa.Column("extraction_metadata", sa.JSON()))
    op.add_column("pages", sa.Column("extraction_started_at", sa.DateTime(timezone=True)))
    op.add_column("pages", sa.Column("extraction_completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_pages_job_extraction_status", "pages", ["job_id", "extraction_status"])
    op.add_column("records", sa.Column("record_identity", sa.String(length=128)))
    op.add_column("records", sa.Column("plan_version", sa.Integer()))
    op.add_column("records", sa.Column("strategy", sa.String(length=64)))
    op.add_column("records", sa.Column("provenance", sa.JSON()))
    op.add_column("records", sa.Column("extraction_metadata", sa.JSON()))
    op.create_unique_constraint("uq_records_job_identity", "records", ["job_id", "record_identity"])
    op.create_index("ix_records_job_plan", "records", ["job_id", "plan_version"])


def downgrade() -> None:
    op.drop_index("ix_records_job_plan", table_name="records")
    op.drop_constraint("uq_records_job_identity", "records", type_="unique")
    op.drop_column("records", "extraction_metadata")
    op.drop_column("records", "provenance")
    op.drop_column("records", "strategy")
    op.drop_column("records", "plan_version")
    op.drop_column("records", "record_identity")
    op.drop_index("ix_pages_job_extraction_status", table_name="pages")
    op.drop_column("pages", "extraction_completed_at")
    op.drop_column("pages", "extraction_started_at")
    op.drop_column("pages", "extraction_metadata")
    op.drop_column("pages", "extraction_status")
