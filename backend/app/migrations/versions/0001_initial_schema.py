"""Initial schema - all tables

Revision ID: 0001
Revises:
Create Date: 2026-06-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_name", sa.String(200), nullable=False),
        sa.Column("tenant_code", sa.String(50), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "companies",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("company_code", sa.String(50), nullable=False),
        sa.Column("legal_name", sa.String(300)),
        sa.Column("tax_id", sa.String(20)),
        sa.Column("invoice_registration_number", sa.String(20)),
        sa.Column("fiscal_year_start_month", sa.Integer, nullable=False, server_default="4"),
        sa.Column("tax_method", sa.String(30), nullable=False, server_default="general"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "accounts",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("account_code", sa.String(20), nullable=False),
        sa.Column("account_name", sa.String(100), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("debit_credit", sa.String(10), nullable=False),
        sa.Column("parent_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("valid_from", sa.Date, server_default=sa.func.current_date(), nullable=False),
        sa.Column("valid_to", sa.Date),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sub_accounts",
        sa.Column("sub_account_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id"), nullable=False),
        sa.Column("sub_account_code", sa.String(20), nullable=False),
        sa.Column("sub_account_name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("valid_from", sa.Date, server_default=sa.func.current_date(), nullable=False),
        sa.Column("valid_to", sa.Date),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "tax_rules",
        sa.Column("tax_rule_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("tax_code", sa.String(20), nullable=False),
        sa.Column("tax_name", sa.String(100), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("tax_type", sa.String(20), nullable=False),
        sa.Column("is_inclusive", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("valid_from", sa.Date, server_default=sa.func.current_date(), nullable=False),
        sa.Column("valid_to", sa.Date),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "journal_headers",
        sa.Column("journal_header_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("journal_number", sa.String(50), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("voucher_type", sa.String(20), nullable=False, server_default="transfer"),
        sa.Column("summary", sa.Text),
        sa.Column("approval_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("is_voided", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "journal_lines",
        sa.Column("journal_line_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("journal_header_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journal_headers.journal_header_id"), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("debit_credit", sa.String(10), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id"), nullable=False),
        sa.Column("sub_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sub_accounts.sub_account_id")),
        sa.Column("department_id", postgresql.UUID(as_uuid=True)),
        sa.Column("tax_rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tax_rules.tax_rule_id")),
        sa.Column("amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(15, 4), nullable=False, server_default="0"),
        sa.Column("description", sa.Text),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "monthly_balances",
        sa.Column("balance_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("debit_total", sa.Numeric(15, 4), nullable=False, server_default="0"),
        sa.Column("credit_total", sa.Numeric(15, 4), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "approval_workflows",
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("trigger_type", sa.String(30), nullable=False, server_default="amount_threshold"),
        sa.Column("threshold_amount", sa.Numeric(15, 4), nullable=False, server_default="0"),
        sa.Column("required_approver_roles", sa.Text, nullable=False, server_default="approver,admin"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "approval_logs",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("journal_header_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journal_headers.journal_header_id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("approval_logs")
    op.drop_table("approval_workflows")
    op.drop_table("monthly_balances")
    op.drop_table("journal_lines")
    op.drop_table("journal_headers")
    op.drop_table("tax_rules")
    op.drop_table("sub_accounts")
    op.drop_table("accounts")
    op.drop_table("companies")
    op.drop_table("users")
    op.drop_table("tenants")
