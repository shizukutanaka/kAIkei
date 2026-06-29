"""Add expense_reports and expense_items tables

Revision ID: 0007_expenses
Revises: 0006_attendance
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_expenses"
down_revision: Union[str, None] = "0006_attendance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense_reports",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.employee_id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="submitted", nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "expense_items",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("expense_reports.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("expense_date", sa.Date, nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_expense_items_report_id", "expense_items", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_expense_items_report_id", table_name="expense_items")
    op.drop_table("expense_items")
    op.drop_table("expense_reports")
