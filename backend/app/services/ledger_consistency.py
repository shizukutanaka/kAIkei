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
class LedgerCheckResult:
    status: str
    balance_check: LedgerBalanceCheckResult


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
            and not header.is_deleted
            and not getattr(header, "is_voided", False)
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

    @classmethod
    def check(
        cls,
        *,
        company_id: UUID,
        target_date: date,
        journal_headers: list[object],
        journal_lines: list[object],
    ) -> LedgerCheckResult:
        balance_check = cls.balance_check(
            company_id=company_id,
            target_date=target_date,
            journal_headers=journal_headers,
            journal_lines=journal_lines,
        )
        status = "ok" if balance_check.imbalanced_count == 0 else "imbalanced"
        return LedgerCheckResult(status=status, balance_check=balance_check)
