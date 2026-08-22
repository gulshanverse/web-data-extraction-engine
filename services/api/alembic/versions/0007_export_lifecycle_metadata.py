"""Complete durable export and generated-file metadata.

Revision ID: 0007_export_lifecycle_metadata
Revises: 0006_validation_runs
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0007_export_lifecycle_metadata"
down_revision = "0006_validation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("validation_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("export_jobs", sa.Column("options", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("export_jobs", sa.Column("error_message", sa.String(length=500)))
    op.add_column("export_jobs", sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("export_jobs", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_export_jobs_validation_run",
        "export_jobs",
        "validation_runs",
        ["validation_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("generated_files", sa.Column("filename", sa.String(length=255), nullable=True))

    op.execute("UPDATE export_jobs SET validation_run_id = (SELECT id FROM validation_runs WHERE validation_runs.job_id = export_jobs.job_id ORDER BY run_number DESC LIMIT 1)")
    op.execute("UPDATE generated_files SET filename = 'export' WHERE filename IS NULL")
    op.alter_column("export_jobs", "validation_run_id", nullable=False)
    op.alter_column("generated_files", "filename", nullable=False)
    op.alter_column("export_jobs", "options", server_default=None)
    op.alter_column("export_jobs", "attempt", server_default=None)


def downgrade() -> None:
    op.drop_column("generated_files", "filename")
    op.drop_constraint("fk_export_jobs_validation_run", "export_jobs", type_="foreignkey")
    op.drop_column("export_jobs", "started_at")
    op.drop_column("export_jobs", "attempt")
    op.drop_column("export_jobs", "error_message")
    op.drop_column("export_jobs", "options")
    op.drop_column("export_jobs", "validation_run_id")
