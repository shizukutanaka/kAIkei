"""帳簿の貸借一致検査。

以前はここに「月次残高キャッシュとの突き合わせ（cache drift）」もあった。
期待値を `approval_status == "approved"` の仕訳から作る一方、キャッシュは
**転記（"posted"）**の時にしか書かれなかったので、転記した瞬間に必ず drift に
なった。常に赤い検算は誰も見ない。キャッシュごと削除し、月次残高は仕訳から
直接集計する方式（`app/services/ledger_totals.py`）に一本化した。

残したのは貸借一致の検査だけ。これは承認状態に依らない不変条件なので、
削除・取消以外の全ての仕訳を対象にする。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.ledger_consistency import LedgerConsistencyService


def _header(
    company_id,
    journal_header_id,
    transaction_date,
    approval_status="approved",
    is_deleted=False,
    is_voided=False,
):
    return SimpleNamespace(
        company_id=company_id,
        journal_header_id=journal_header_id,
        transaction_date=transaction_date,
        approval_status=approval_status,
        is_deleted=is_deleted,
        is_voided=is_voided,
    )


def _line(journal_header_id, account_id, debit_credit, amount, is_deleted=False):
    return SimpleNamespace(
        journal_header_id=journal_header_id,
        account_id=account_id,
        debit_credit=debit_credit,
        amount=Decimal(str(amount)),
        is_deleted=is_deleted,
    )


class TestLedgerConsistencyService:
    def test_check_is_ok_when_every_entry_balances(self):
        company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()
        other_account_id = uuid4()

        headers = [
            _header(company_id, header_id, date(2026, 6, 10)),
            _header(company_id, uuid4(), date(2026, 7, 1)),  # 基準日より後
        ]
        lines = [
            _line(header_id, account_id, "debit", "100"),
            _line(header_id, other_account_id, "credit", "100"),
            _line(headers[1].journal_header_id, account_id, "debit", "999"),
        ]

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=date(2026, 6, 30),
            journal_headers=headers,
            journal_lines=lines,
        )

        assert result.status == "ok"
        assert result.balance_check.headers_checked == 1
        assert result.balance_check.imbalanced_count == 0
        assert result.balance_check.total_debit == Decimal("100")
        assert result.balance_check.total_credit == Decimal("100")

    def test_check_reports_an_imbalanced_header(self):
        company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=date(2026, 6, 30),
            journal_headers=[_header(company_id, header_id, date(2026, 6, 10))],
            journal_lines=[
                _line(header_id, account_id, "debit", "120"),
                _line(header_id, account_id, "credit", "100"),
            ],
        )

        assert result.status == "imbalanced"
        assert result.balance_check.imbalanced_count == 1
        assert result.balance_check.imbalanced_entries[0].journal_header_id == header_id
        assert result.balance_check.imbalanced_entries[0].difference == Decimal("20")

    def test_an_unapproved_entry_is_still_checked(self):
        """貸借一致は承認状態に依らない不変条件。

        以前は "approved" だけを見ていたので、下書きのまま壊れている仕訳
        （インポートや自動生成の産物）を検算が素通りしていた。
        """
        company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=date(2026, 6, 30),
            journal_headers=[
                _header(company_id, header_id, date(2026, 6, 10), approval_status="draft")
            ],
            journal_lines=[
                _line(header_id, account_id, "debit", "120"),
                _line(header_id, account_id, "credit", "100"),
            ],
        )

        assert result.balance_check.headers_checked == 1
        assert result.status == "imbalanced"

    def test_voided_and_deleted_entries_are_skipped(self):
        company_id = uuid4()
        voided_id = uuid4()
        deleted_id = uuid4()
        account_id = uuid4()

        headers = [
            _header(company_id, voided_id, date(2026, 6, 10), is_voided=True),
            _header(company_id, deleted_id, date(2026, 6, 10), is_deleted=True),
        ]
        lines = [
            _line(voided_id, account_id, "debit", "120"),
            _line(voided_id, account_id, "credit", "100"),
            _line(deleted_id, account_id, "debit", "77"),
        ]

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=date(2026, 6, 30),
            journal_headers=headers,
            journal_lines=lines,
        )

        assert result.status == "ok"
        assert result.balance_check.headers_checked == 0

    def test_another_companys_entries_are_skipped(self):
        company_id = uuid4()
        other_company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=date(2026, 6, 30),
            journal_headers=[_header(other_company_id, header_id, date(2026, 6, 10))],
            journal_lines=[
                _line(header_id, account_id, "debit", "120"),
                _line(header_id, account_id, "credit", "100"),
            ],
        )

        assert result.balance_check.headers_checked == 0
        assert result.status == "ok"
