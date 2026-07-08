from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 租税特別措置法61条の4 / 交際費等の損金算入限度額
ENTERTAINMENT_EXPENSE_SMALL_CORPORATION_THRESHOLD = Decimal("100000000")
ENTERTAINMENT_EXPENSE_FLAT_DEDUCTION_LIMIT = Decimal("8000000")
ENTERTAINMENT_EXPENSE_DINING_RATE = Decimal("0.50")


@dataclass(frozen=True)
class EntertainmentExpenseResult:
    deductible_limit: Decimal
    deductible_amount: Decimal
    non_deductible_amount: Decimal
    basis: str


class EntertainmentExpenseService:
    @staticmethod
    def _floor_yen(amount: Decimal) -> Decimal:
        return amount.quantize(Decimal("1"), rounding=ROUND_DOWN)

    @classmethod
    def compute(cls, total_entertainment: Decimal, dining_expense: Decimal, capital: Decimal) -> EntertainmentExpenseResult:
        if total_entertainment < 0 or dining_expense < 0 or capital < 0:
            raise ValueError("inputs must be non-negative")
        if dining_expense > total_entertainment:
            raise ValueError("dining_expense must not exceed total_entertainment")

        dining_limit = cls._floor_yen(dining_expense * ENTERTAINMENT_EXPENSE_DINING_RATE)
        if capital <= ENTERTAINMENT_EXPENSE_SMALL_CORPORATION_THRESHOLD:
            if dining_limit <= ENTERTAINMENT_EXPENSE_FLAT_DEDUCTION_LIMIT:
                deductible_limit = ENTERTAINMENT_EXPENSE_FLAT_DEDUCTION_LIMIT
                basis = "flat_8m"
            else:
                deductible_limit = dining_limit
                basis = "dining_50pct"
        else:
            deductible_limit = dining_limit
            basis = "dining_50pct"

        deductible_amount = total_entertainment if total_entertainment <= deductible_limit else deductible_limit
        non_deductible_amount = total_entertainment - deductible_limit
        if non_deductible_amount < 0:
            non_deductible_amount = Decimal("0")

        return EntertainmentExpenseResult(
            deductible_limit=deductible_limit,
            deductible_amount=deductible_amount,
            non_deductible_amount=non_deductible_amount,
            basis=basis,
        )
