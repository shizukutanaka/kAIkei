from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.ledger_consistency import LedgerConsistencyService


def _header(company_id, journal_header_id, transaction_date, approval_status="approved", is_deleted=False):
    return SimpleNamespace(
        company_id=company_id,
        journal_header_id=journal_header_id,
        transaction_date=transaction_date,
        approval_status=approval_status,
        is_deleted=is_deleted,
    )


def _line(journal_header_id, account_id, debit_credit, amount, is_deleted=False):
    return SimpleNamespace(
        journal_header_id=journal_header_id,
        account_id=account_id,
        debit_credit=debit_credit,
        amount=Decimal(str(amount)),
        is_deleted=is_deleted,
    )


def _balance(company_id, account_id, year, month, debit_total, credit_total, is_deleted=False):
    return SimpleNamespace(
        company_id=company_id,
        account_id=account_id,
        year=year,
        month=month,
        debit_total=Decimal(str(debit_total)),
        credit_total=Decimal(str(credit_total)),
        is_deleted=is_deleted,
    )


class TestLedgerConsistencyService:
    def test_check_ok_when_balanced_and_cache_matches(self):
        company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()
        other_account_id = uuid4()
        target_date = date(2026, 6, 30)

        headers = [
            _header(company_id, header_id, date(2026, 6, 10)),
            _header(company_id, uuid4(), date(2026, 7, 1)),
            _header(company_id, uuid4(), date(2026, 6, 5), approval_status="draft"),
        ]
        lines = [
            _line(header_id, account_id, "debit", "100"),
            _line(header_id, other_account_id, "credit", "100"),
            _line(headers[1].journal_header_id, account_id, "debit", "999"),
            _line(headers[2].journal_header_id, account_id, "debit", "50"),
        ]
        balances = [
            _balance(company_id, account_id, 2026, 6, "100", "0"),
            _balance(company_id, other_account_id, 2026, 6, "0", "100"),
        ]

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=target_date,
            journal_headers=headers,
            journal_lines=lines,
            monthly_balances=balances,
        )

        assert result.status == "ok"
        assert result.balance_check.headers_checked == 1
        assert result.balance_check.imbalanced_count == 0
        assert result.balance_check.total_debit == Decimal("100")
        assert result.balance_check.total_credit == Decimal("100")
        assert result.cache_drift_check.rows_checked == 2
        assert result.cache_drift_check.drift_count == 0

    def test_check_reports_imbalanced_header(self):
        company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()
        target_date = date(2026, 6, 30)

        headers = [_header(company_id, header_id, date(2026, 6, 10))]
        lines = [
            _line(header_id, account_id, "debit", "120"),
            _line(header_id, account_id, "credit", "100"),
        ]

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=target_date,
            journal_headers=headers,
            journal_lines=lines,
            monthly_balances=[],
        )

        assert result.status == "drift_detected"
        assert result.balance_check.headers_checked == 1
        assert result.balance_check.imbalanced_count == 1
        assert result.balance_check.imbalanced_entries[0].journal_header_id == header_id
        assert result.balance_check.imbalanced_entries[0].difference == Decimal("20")
        assert result.balance_check.total_debit == Decimal("120")
        assert result.balance_check.total_credit == Decimal("100")

    def test_check_reports_cache_drift_for_mismatched_and_missing_rows(self):
        company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()
        missing_account_id = uuid4()
        extra_account_id = uuid4()
        target_date = date(2026, 6, 30)

        headers = [_header(company_id, header_id, date(2026, 6, 10))]
        lines = [
            _line(header_id, account_id, "debit", "70"),
            _line(header_id, account_id, "credit", "20"),
            _line(header_id, missing_account_id, "credit", "50"),
        ]
        balances = [
            _balance(company_id, account_id, 2026, 6, "70", "10"),
            _balance(company_id, extra_account_id, 2026, 6, "5", "5"),
        ]

        result = LedgerConsistencyService.check(
            company_id=company_id,
            target_date=target_date,
            journal_headers=headers,
            journal_lines=lines,
            monthly_balances=balances,
        )

        assert result.status == "drift_detected"
        assert result.balance_check.imbalanced_count == 0
        assert result.cache_drift_check.drift_count == 3

        drift_keys = {
            (entry.account_id, entry.year, entry.month): entry
            for entry in result.cache_drift_check.drift_entries
        }
        assert drift_keys[(account_id, 2026, 6)].expected_debit == Decimal("70")
        assert drift_keys[(account_id, 2026, 6)].expected_credit == Decimal("20")
        assert drift_keys[(account_id, 2026, 6)].cached_credit == Decimal("10")
        assert drift_keys[(missing_account_id, 2026, 6)].cached_debit == Decimal("0")
        assert drift_keys[(missing_account_id, 2026, 6)].cached_credit == Decimal("0")
        assert drift_keys[(extra_account_id, 2026, 6)].expected_debit == Decimal("0")
        assert drift_keys[(extra_account_id, 2026, 6)].expected_credit == Decimal("0")
