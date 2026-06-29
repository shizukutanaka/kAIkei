"""Add tax_returns table

Revision ID: 0009_tax_returns
Revises: 0008_invoices
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_tax_returns"
down_revision: Union[str, None] = "0008_invoices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_returns",
        sa.Column("return_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("tax_year", sa.Integer, nullable=False),
        sa.Column("filing_type", sa.String(20), server_default="general", nullable=False),
        sa.Column("taxable_sales", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("non_taxable_sales", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("export_taxable_sales", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("total_sales", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("purchases_subject_to_tax", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("purchases_not_subject_to_tax", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("total_purchases", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("output_tax", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("input_tax", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("tax_adjustment", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("tax_payable", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="calculated", nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tax_returns_company_year", "tax_returns", ["company_id", "tax_year"])


def downgrade() -> None:
    op.drop_index("ix_tax_returns_company_year", table_name="tax_returns")
    op.drop_table("tax_returns")
