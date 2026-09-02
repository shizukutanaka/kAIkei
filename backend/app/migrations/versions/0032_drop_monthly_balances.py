"""月次残高キャッシュ（monthly_balances）を削除する。

転記時に加算するだけの集計キャッシュで、取消（void）しても減算されなかった。
月次残高・予実比較・帳簿検算がこれを読んでおり、同じ画面の試算表タブ
（仕訳から直接集計）と数字が食い違っていた。キャッシュに減算を足すのではなく、
`app/services/ledger_totals.py` で仕訳から集計する方式に一本化し、
同期すべき第二の真実を無くす。

Revision ID: 0032_drop_monthly_balances
Revises: 0031_employee_dependents
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_drop_monthly_balances"
down_revision: str | None = "0031_employee_dependents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_monthly_balances_company_period", table_name="monthly_balances")
    op.drop_table("monthly_balances")


def downgrade() -> None:
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
    op.create_index(
        "ix_monthly_balances_company_period", "monthly_balances", ["company_id", "year", "month"]
    )
