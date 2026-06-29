"""Add performance indexes

Revision ID: 0010_indexes
Revises: 0009_tax_returns
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010_indexes"
down_revision: Union[str, None] = "0009_tax_returns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Journal headers: company_id + transaction_date (list, trial balance, ordering)
    op.create_index("ix_journal_headers_company_date", "journal_headers", ["company_id", "transaction_date"])
    # Journal headers: company_id + approval_status (approval queue)
    op.create_index("ix_journal_headers_company_status", "journal_headers", ["company_id", "approval_status"])
    # Journal headers: company_id + source_type (auto-journal lookup)
    op.create_index("ix_journal_headers_company_source", "journal_headers", ["company_id", "source_type"])

    # Journal lines: account_id (trial balance aggregate)
    op.create_index("ix_journal_lines_account_id", "journal_lines", ["account_id"])
    # Journal lines: journal_header_id (join)
    op.create_index("ix_journal_lines_header_id", "journal_lines", ["journal_header_id"])

    # Accounts: company_id + is_active (account lookup)
    op.create_index("ix_accounts_company_active", "accounts", ["company_id", "is_active"])

    # Monthly balances: company_id + year + month
    op.create_index("ix_monthly_balances_company_period", "monthly_balances", ["company_id", "year", "month"])

    # Partners: company_id + is_deleted
    op.create_index("ix_partners_company_deleted", "partners", ["company_id", "is_deleted"])

    # Approval logs: journal_header_id
    op.create_index("ix_approval_logs_journal_id", "approval_logs", ["journal_header_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_logs_journal_id", table_name="approval_logs")
    op.drop_index("ix_partners_company_deleted", table_name="partners")
    op.drop_index("ix_monthly_balances_company_period", table_name="monthly_balances")
    op.drop_index("ix_accounts_company_active", table_name="accounts")
    op.drop_index("ix_journal_lines_header_id", table_name="journal_lines")
    op.drop_index("ix_journal_lines_account_id", table_name="journal_lines")
    op.drop_index("ix_journal_headers_company_source", table_name="journal_headers")
    op.drop_index("ix_journal_headers_company_status", table_name="journal_headers")
    op.drop_index("ix_journal_headers_company_date", table_name="journal_headers")
