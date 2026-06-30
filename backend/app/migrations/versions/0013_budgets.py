"""Add budgets and budget_lines tables

Revision ID: 0013_budgets
Revises: 0012_audit_logs
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013_budgets"
down_revision: Union[str, None] = "0012_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_budgets_company_year", "budgets", ["company_id", "fiscal_year"])

    op.create_table(
        "budget_lines",
        sa.Column("budget_line_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.budget_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id"), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("budgeted_amount", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_budget_lines_budget_id", "budget_lines", ["budget_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_lines_budget_id", table_name="budget_lines")
    op.drop_table("budget_lines")
    op.drop_index("ix_budgets_company_year", table_name="budgets")
    op.drop_table("budgets")
