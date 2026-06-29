"""Add invoices and invoice_lines tables

Revision ID: 0008_invoices
Revises: 0007_expenses
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_invoices"
down_revision: Union[str, None] = "0007_expenses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.partner_id"), nullable=True),
        sa.Column("invoice_number", sa.String(50), nullable=False, unique=True),
        sa.Column("invoice_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("subtotal", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), server_default="10.00", nullable=False),
        sa.Column("tax_amount", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invoices_company_date", "invoices", ["company_id", "invoice_date"])

    op.create_table(
        "invoice_lines",
        sa.Column("line_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Numeric(15, 3), server_default="1", nullable=False),
        sa.Column("unit_price", sa.Numeric(15, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(15, 4), nullable=False),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_lines_invoice_id", table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index("ix_invoices_company_date", table_name="invoices")
    op.drop_table("invoices")
