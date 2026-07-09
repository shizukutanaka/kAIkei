"""Add bank_statement_lines table for bank import and reconciliation

Revision ID: 0014_bank_statements
Revises: 0013_webhooks
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_bank_statements"
down_revision: Union[str, None] = "0013_webhooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_statement_lines",
        sa.Column("bank_statement_line_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("value_date", sa.Date, nullable=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("balance", sa.Numeric(15, 4), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("counterparty_name", sa.String(200), nullable=True),
        sa.Column("is_reconciled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "reconciled_journal_line_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("journal_lines.journal_line_id"),
            nullable=True,
        ),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="csv"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bank_statement_lines_company", "bank_statement_lines", ["company_id"])
    op.create_index(
        "ix_bank_statement_lines_unreconciled",
        "bank_statement_lines",
        ["company_id", "is_reconciled"],
    )


def downgrade() -> None:
    op.drop_index("ix_bank_statement_lines_unreconciled", table_name="bank_statement_lines")
    op.drop_index("ix_bank_statement_lines_company", table_name="bank_statement_lines")
    op.drop_table("bank_statement_lines")
