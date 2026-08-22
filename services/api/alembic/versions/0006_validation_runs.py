"""phase 7 validation runs

Revision ID: 0006_validation_runs
Revises: 0005_extraction_records
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_validation_runs"
down_revision = "0005_extraction_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("operation_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("ruleset_version", sa.String(length=32), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["extraction_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "run_number", name="uq_validation_runs_job_number"),
        sa.UniqueConstraint("operation_key"),
    )
    op.create_index("ix_validation_runs_job_status", "validation_runs", ["job_id", "status"])
    op.add_column("validation_results", sa.Column("validation_run_id", sa.Uuid()))
    op.add_column("validation_results", sa.Column("schema_version", sa.String(length=32)))
    op.add_column("validation_results", sa.Column("ruleset_version", sa.String(length=32)))
    op.add_column("validation_results", sa.Column("plan_version", sa.Integer()))
    op.add_column("validation_results", sa.Column("quality", sa.String(length=32)))
    op.add_column("validation_results", sa.Column("summary", sa.JSON()))
    op.create_foreign_key(
        "fk_validation_results_run",
        "validation_results",
        "validation_runs",
        ["validation_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_validation_run_record", "validation_results", ["validation_run_id", "record_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_validation_run_record", "validation_results", type_="unique")
    op.drop_constraint("fk_validation_results_run", "validation_results", type_="foreignkey")
    op.drop_column("validation_results", "summary")
    op.drop_column("validation_results", "quality")
    op.drop_column("validation_results", "plan_version")
    op.drop_column("validation_results", "ruleset_version")
    op.drop_column("validation_results", "schema_version")
    op.drop_column("validation_results", "validation_run_id")
    op.drop_index("ix_validation_runs_job_status", table_name="validation_runs")
    op.drop_table("validation_runs")
