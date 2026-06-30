"""Add bank_accounts, bank_statement_details and payment_requests tables

Revision ID: 0014_bank_reconciliation
Revises: 0013_budgets
Create Date: 2026-06-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_bank_reconciliation"
down_revision: str | None = "0013_budgets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_accounts",
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("bank_code", sa.String(4), nullable=False),
        sa.Column("branch_code", sa.String(3), nullable=False),
        sa.Column("account_type", sa.String(10), nullable=False),
        sa.Column("account_no_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("account_name", sa.String(100), nullable=False),
        sa.Column("account_name_kana", sa.String(40), nullable=False),
        sa.Column("currency_code", sa.String(3), server_default="JPY", nullable=False),
        sa.Column("valid_from", sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("auto_fetch_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bank_accounts_company_id", "bank_accounts", ["company_id"])

    op.create_table(
        "bank_statement_details",
        sa.Column("statement_detail_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column(
            "bank_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bank_accounts.bank_account_id"),
            nullable=False,
        ),
        sa.Column("value_date", sa.Date(), nullable=False),
        sa.Column("withdraw_amount", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("deposit_amount", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("sender_name_kana", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_reconciled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "reconciled_journal_header_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_headers.journal_header_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_bank_statement_details_company_unreconciled",
        "bank_statement_details",
        ["company_id", "is_reconciled"],
    )
    op.create_index("ix_bank_statement_details_bank_account_id", "bank_statement_details", ["bank_account_id"])

    op.create_table(
        "payment_requests",
        sa.Column("payment_request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.partner_id"), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "bank_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bank_accounts.bank_account_id"),
            nullable=True,
        ),
        sa.Column("dest_bank_code", sa.String(4), nullable=True),
        sa.Column("dest_branch_code", sa.String(3), nullable=True),
        sa.Column("dest_account_type", sa.String(10), nullable=True),
        sa.Column("dest_account_no", sa.String(7), nullable=True),
        sa.Column("dest_account_name_kana", sa.String(30), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column(
            "journal_header_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_headers.journal_header_id"),
            nullable=True,
        ),
        sa.Column("zengin_export_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payment_requests_company_status", "payment_requests", ["company_id", "status"])
    op.create_index("ix_payment_requests_payment_date", "payment_requests", ["payment_date"])


def downgrade() -> None:
    op.drop_index("ix_payment_requests_payment_date", table_name="payment_requests")
    op.drop_index("ix_payment_requests_company_status", table_name="payment_requests")
    op.drop_table("payment_requests")
    op.drop_index("ix_bank_statement_details_bank_account_id", table_name="bank_statement_details")
    op.drop_index("ix_bank_statement_details_company_unreconciled", table_name="bank_statement_details")
    op.drop_table("bank_statement_details")
    op.drop_index("ix_bank_accounts_company_id", table_name="bank_accounts")
    op.drop_table("bank_accounts")
