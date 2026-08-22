"""phase 3 browser metadata and artifact references

Revision ID: 0002_browser_metadata
Revises: 0001_phase2_job_foundation
Create Date: 2026-08-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_browser_metadata"
down_revision = "0001_phase2_job_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("final_url", sa.Text()))
    op.add_column("pages", sa.Column("http_status", sa.Integer()))
    op.add_column("pages", sa.Column("content_type", sa.String(length=200)))
    op.add_column("pages", sa.Column("title", sa.String(length=500)))
    op.add_column("pages", sa.Column("viewport", postgresql.JSONB()))
    op.add_column("pages", sa.Column("navigation_time_ms", sa.Integer()))
    op.add_column("pages", sa.Column("redirect_count", sa.Integer()))
    op.add_column("pages", sa.Column("browser_metadata", postgresql.JSONB()))
    op.create_table(
        "browser_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pages.id", ondelete="SET NULL")),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=200), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("storage_key", name="uq_browser_artifacts_storage_key"),
    )
    op.create_index("ix_browser_artifacts_job_created", "browser_artifacts", ["job_id", "created_at"])


def downgrade() -> None:
    op.drop_table("browser_artifacts")
    for column in ["browser_metadata", "redirect_count", "navigation_time_ms", "viewport", "title", "content_type", "http_status", "final_url"]:
        op.drop_column("pages", column)
