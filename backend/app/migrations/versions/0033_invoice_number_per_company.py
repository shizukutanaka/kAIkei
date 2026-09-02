"""請求書番号の一意制約を「全社で一意」から「会社ごとに一意」へ変更する。

アプリ側の重複チェックは `company_id` と `invoice_number` の組で見ていたが、
DB制約は `invoice_number` 単独の UNIQUE だった。各社が 001 から採番するのは
普通なので、2社目以降はありふれた番号を登録できず、アプリのチェックを通過した
後に IntegrityError が捕捉されないまま 500 になっていた。

Revision ID: 0033_invoice_number_per_company
Revises: 0032_drop_monthly_balances
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0033_invoice_number_per_company"
down_revision: str | None = "0032_drop_monthly_balances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("invoices_invoice_number_key", "invoices", type_="unique")
    op.create_unique_constraint(
        "uq_invoices_company_number", "invoices", ["company_id", "invoice_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_invoices_company_number", "invoices", type_="unique")
    op.create_unique_constraint("invoices_invoice_number_key", "invoices", ["invoice_number"])
