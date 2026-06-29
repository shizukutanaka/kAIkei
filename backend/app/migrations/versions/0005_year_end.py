"""Add year_end_adjustments table

Revision ID: 0005_year_end
Revises: 0004_bonus
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_year_end"
down_revision: Union[str, None] = "0004_bonus"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "year_end_adjustments",
        sa.Column("adjustment_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.employee_id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("adjustment_year", sa.Integer, nullable=False),
        sa.Column("annual_salary", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("annual_bonus", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("total_gross", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("withholding_tax_total", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("estimated_annual_tax", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("social_insurance_total", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("dependents", sa.Integer, server_default="0", nullable=False),
        sa.Column("dependent_deduction", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("adjustment_amount", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("year_end_adjustments")
