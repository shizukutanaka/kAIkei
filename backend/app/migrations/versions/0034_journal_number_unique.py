"""仕訳番号を会社ごとに一意にする。

採番は既存番号を読んでから書くだけで、DBに一意制約が無かった。同じ会社で
同時に2件作ると両方が同じ番号を読み、同じ番号の仕訳が2件できる（実測で3件同時に
作ると3件とも JRN-00000001）。仕訳番号は監査で仕訳を追う識別子なので、重複すると
追跡できない。

既存データに重複がある場合は連番を振り直してから制約を張る。

Revision ID: 0034_journal_number_unique
Revises: 0033_invoice_number_per_company
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0034_journal_number_unique"
down_revision: str | None = "0033_invoice_number_per_company"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 既存の重複を解消する。同じ (会社, 番号) の2件目以降に、その会社で未使用の
    # 連番を振り直す。作成日時の古いものが元の番号を保つ。
    op.execute(
        """
        WITH duplicated AS (
            SELECT journal_header_id, company_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id, journal_number
                       ORDER BY created_at, journal_header_id
                   ) AS position
            FROM journal_headers
        ),
        highest AS (
            SELECT company_id,
                   COALESCE(MAX(CAST(SUBSTRING(journal_number FROM 5) AS BIGINT)), 0) AS top
            FROM journal_headers
            WHERE journal_number ~ '^JRN-[0-9]+$'
            GROUP BY company_id
        ),
        renumbered AS (
            SELECT d.journal_header_id,
                   'JRN-' || LPAD(
                       (h.top + ROW_NUMBER() OVER (PARTITION BY d.company_id ORDER BY d.journal_header_id))::text,
                       8, '0'
                   ) AS new_number
            FROM duplicated d
            JOIN highest h ON h.company_id = d.company_id
            WHERE d.position > 1
        )
        UPDATE journal_headers jh
        SET journal_number = r.new_number
        FROM renumbered r
        WHERE jh.journal_header_id = r.journal_header_id
        """
    )
    op.create_unique_constraint(
        "uq_journal_headers_company_number", "journal_headers", ["company_id", "journal_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_journal_headers_company_number", "journal_headers", type_="unique")
