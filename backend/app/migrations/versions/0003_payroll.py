"""Add employees, payroll_records, and partners tables

Revision ID: 0003_payroll
Revises: 0002_fixed_assets
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_payroll"
down_revision: Union[str, None] = "0002_fixed_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("employee_code", sa.String(50), nullable=False),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("position", sa.String(100), nullable=True),
        sa.Column("employment_type", sa.String(20), server_default="full_time", nullable=False),
        sa.Column("base_salary", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("hourly_rate", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("hire_date", sa.Date, nullable=False),
        sa.Column("termination_date", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "payroll_records",
        sa.Column("payroll_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.employee_id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("payroll_year", sa.Integer, nullable=False),
        sa.Column("payroll_month", sa.Integer, nullable=False),
        sa.Column("base_salary", sa.Numeric(15, 4), nullable=False),
        sa.Column("overtime_hours", sa.Numeric(8, 2), server_default="0", nullable=False),
        sa.Column("overtime_pay", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("total_gross", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("income_tax", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("social_insurance", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("total_deductions", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("net_pay", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "partners",
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("partner_code", sa.String(50), nullable=False),
        sa.Column("partner_name", sa.String(200), nullable=False),
        sa.Column("partner_type", sa.String(20), nullable=False),
        sa.Column("postal_code", sa.String(10), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("contact_person", sa.String(100), nullable=True),
        sa.Column("payment_terms", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("partners")
    op.drop_table("payroll_records")
    op.drop_table("employees")
