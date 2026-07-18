"""Add office_tasks table for the monthly-operations engine

Revision ID: 0021_office_tasks
Revises: 0020_ai_inference_logs
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0021_office_tasks"
down_revision: Union[str, None] = "0020_ai_inference_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "office_tasks",
        sa.Column("office_task_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(40), nullable=False),
        sa.Column("assigned_to", sa.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
        sa.Column("period", sa.String(7), nullable=True),
        sa.Column("task_metadata", JSONB, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_office_tasks_company", "office_tasks", ["company_id"])
    op.create_index("ix_office_tasks_period", "office_tasks", ["company_id", "period"])
    op.create_index("ix_office_tasks_assignee", "office_tasks", ["assigned_to", "status"])


def downgrade() -> None:
    op.drop_index("ix_office_tasks_assignee", table_name="office_tasks")
    op.drop_index("ix_office_tasks_period", table_name="office_tasks")
    op.drop_index("ix_office_tasks_company", table_name="office_tasks")
    op.drop_table("office_tasks")
