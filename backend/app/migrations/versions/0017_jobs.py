"""Add scheduled jobs and job executions

Revision ID: 0017_jobs
Revises: 0016_webhooks
Create Date: 2026-06-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_jobs"
down_revision: str | None = "0016_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("scheduled_job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("run_hour", sa.Integer(), nullable=False),
        sa.Column("run_day", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "job_executions",
        sa.Column("job_execution_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scheduled_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scheduled_jobs.scheduled_job_id"), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scheduled_jobs_company_id_is_active", "scheduled_jobs", ["company_id", "is_active"])
    op.create_index("ix_job_executions_company_id_status", "job_executions", ["company_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_job_executions_company_id_status", table_name="job_executions")
    op.drop_index("ix_scheduled_jobs_company_id_is_active", table_name="scheduled_jobs")
    op.drop_table("job_executions")
    op.drop_table("scheduled_jobs")
