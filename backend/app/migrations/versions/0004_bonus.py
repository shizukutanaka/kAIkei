"""Add bonus_records table

Revision ID: 0004_bonus
Revises: 0003_payroll
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_bonus"
down_revision: Union[str, None] = "0003_payroll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bonus_records",
        sa.Column("bonus_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.employee_id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("bonus_year", sa.Integer, nullable=False),
        sa.Column("bonus_term", sa.String(20), nullable=False),
        sa.Column("bonus_amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("bonus_base_months", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("performance_factor", sa.Numeric(3, 2), server_default="1.00", nullable=False),
        sa.Column("income_tax", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("social_insurance", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("total_deductions", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("net_pay", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bonus_records")
