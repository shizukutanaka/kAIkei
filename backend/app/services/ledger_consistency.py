from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True)
class LedgerImbalanceEntry:
    journal_header_id: UUID
    debit_sum: Decimal
    credit_sum: Decimal
    difference: Decimal


@dataclass(frozen=True)
class LedgerBalanceCheckResult:
    headers_checked: int
    imbalanced_count: int
    total_debit: Decimal
    total_credit: Decimal
    imbalanced_entries: list[LedgerImbalanceEntry]


@dataclass(frozen=True)
class LedgerCacheDriftEntry:
    account_id: UUID
    year: int
    month: int
    expected_debit: Decimal
    expected_credit: Decimal
    cached_debit: Decimal
    cached_credit: Decimal


@dataclass(frozen=True)
class LedgerCacheDriftResult:
    rows_checked: int
    drift_count: int
    drift_entries: list[LedgerCacheDriftEntry]


@dataclass(frozen=True)
class LedgerCheckResult:
    status: str
    balance_check: LedgerBalanceCheckResult
    cache_drift_check: LedgerCacheDriftResult


class LedgerConsistencyService:
    @staticmethod
    def balance_check(
        *,
        company_id: UUID,
        target_date: date,
        journal_headers: list[object],
        journal_lines: list[object],
    ) -> LedgerBalanceCheckResult:
        checked_headers = {
            header.journal_header_id: header
            for header in journal_headers
            if header.company_id == company_id
            and header.approval_status == "approved"
            and not header.is_deleted
            and header.transaction_date <= target_date
        }

        per_header: dict[UUID, dict[str, Decimal]] = {
            header_id: {"debit": Decimal("0"), "credit": Decimal("0")}
            for header_id in checked_headers
        }
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        for line in journal_lines:
            if line.is_deleted or line.journal_header_id not in checked_headers:
                continue
            bucket = per_header[line.journal_header_id]
            amount = _decimal(line.amount)
            if line.debit_credit == "debit":
                bucket["debit"] += amount
                total_debit += amount
            elif line.debit_credit == "credit":
                bucket["credit"] += amount
                total_credit += amount

        imbalanced_entries: list[LedgerImbalanceEntry] = []
        for header_id, sums in sorted(per_header.items(), key=lambda item: str(item[0])):
            if sums["debit"] == sums["credit"]:
                continue
            imbalanced_entries.append(
                LedgerImbalanceEntry(
                    journal_header_id=header_id,
                    debit_sum=sums["debit"],
                    credit_sum=sums["credit"],
                    difference=sums["debit"] - sums["credit"],
                )
            )

        return LedgerBalanceCheckResult(
            headers_checked=len(checked_headers),
            imbalanced_count=len(imbalanced_entries),
            total_debit=total_debit,
            total_credit=total_credit,
            imbalanced_entries=imbalanced_entries,
        )

    @staticmethod
    def cache_drift_check(
        *,
        company_id: UUID,
        target_date: date,
        journal_headers: list[object],
        journal_lines: list[object],
        monthly_balances: list[object],
    ) -> LedgerCacheDriftResult:
        checked_headers = {
            header.journal_header_id: header
            for header in journal_headers
            if header.company_id == company_id
            and header.approval_status == "approved"
            and not header.is_deleted
            and header.transaction_date <= target_date
        }

        recomputed: dict[tuple[UUID, int, int], dict[str, Decimal]] = {}
        for line in journal_lines:
            if line.is_deleted:
                continue
            header = checked_headers.get(line.journal_header_id)
            if header is None:
                continue
            key = (
                line.account_id,
                header.transaction_date.year,
                header.transaction_date.month,
            )
            bucket = recomputed.setdefault(
                key, {"debit": Decimal("0"), "credit": Decimal("0")}
            )
            amount = _decimal(line.amount)
            if line.debit_credit == "debit":
                bucket["debit"] += amount
            elif line.debit_credit == "credit":
                bucket["credit"] += amount

        cached: dict[tuple[UUID, int, int], dict[str, Decimal]] = {}
        for row in monthly_balances:
            if row.company_id != company_id or row.is_deleted:
                continue
            if (row.year, row.month) > (target_date.year, target_date.month):
                continue
            cached[(row.account_id, row.year, row.month)] = {
                "debit": _decimal(row.debit_total),
                "credit": _decimal(row.credit_total),
            }

        keys = sorted(
            set(recomputed) | set(cached),
            key=lambda key: (str(key[0]), key[1], key[2]),
        )
        drift_entries: list[LedgerCacheDriftEntry] = []
        for account_id, year, month in keys:
            expected = recomputed.get((account_id, year, month), {})
            cached_values = cached.get((account_id, year, month), {})
            expected_debit = expected.get("debit", Decimal("0"))
            expected_credit = expected.get("credit", Decimal("0"))
            cached_debit = cached_values.get("debit", Decimal("0"))
            cached_credit = cached_values.get("credit", Decimal("0"))
            if expected_debit != cached_debit or expected_credit != cached_credit:
                drift_entries.append(
                    LedgerCacheDriftEntry(
                        account_id=account_id,
                        year=year,
                        month=month,
                        expected_debit=expected_debit,
                        expected_credit=expected_credit,
                        cached_debit=cached_debit,
                        cached_credit=cached_credit,
                    )
                )

        return LedgerCacheDriftResult(
            rows_checked=len(keys),
            drift_count=len(drift_entries),
            drift_entries=drift_entries,
        )

    @classmethod
    def check(
        cls,
        *,
        company_id: UUID,
        target_date: date,
        journal_headers: list[object],
        journal_lines: list[object],
        monthly_balances: list[object],
    ) -> LedgerCheckResult:
        balance_check = cls.balance_check(
            company_id=company_id,
            target_date=target_date,
            journal_headers=journal_headers,
            journal_lines=journal_lines,
        )
        cache_drift_check = cls.cache_drift_check(
            company_id=company_id,
            target_date=target_date,
            journal_headers=journal_headers,
            journal_lines=journal_lines,
            monthly_balances=monthly_balances,
        )
        status = (
            "ok"
            if balance_check.imbalanced_count == 0
            and cache_drift_check.drift_count == 0
            else "drift_detected"
        )
        return LedgerCheckResult(
            status=status,
            balance_check=balance_check,
            cache_drift_check=cache_drift_check,
        )
