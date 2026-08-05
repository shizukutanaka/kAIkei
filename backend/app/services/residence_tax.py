"""住民税 特別徴収税額の月割計算。

地方税法321条の3〜321条の5: 給与所得者の個人住民税は特別徴収により、
市町村から通知された年税額を6月〜翌年5月の12回に分けて毎月の給与から徴収する。
年税額を12等分し、100円未満の端数は最初の月（6月分）にまとめて徴収する。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 特別徴収の徴収月: 6月分〜翌年5月分（暦月）
SPECIAL_COLLECTION_MONTHS: tuple[int, ...] = (6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5)
# 端数整理単位（100円未満は初月に合算）
ROUNDING_UNIT = Decimal("100")


@dataclass(frozen=True)
class ResidenceTaxMonthlyAmount:
    month: int
    amount: Decimal


@dataclass(frozen=True)
class ResidenceTaxResult:
    annual_tax: Decimal
    first_month_amount: Decimal
    ordinary_month_amount: Decimal
    monthly_amounts: tuple[ResidenceTaxMonthlyAmount, ...]
    total: Decimal


class ResidenceTaxSpecialCollectionService:
    @staticmethod
    def _floor_to_unit(amount: Decimal) -> Decimal:
        units = (amount / ROUNDING_UNIT).quantize(Decimal("1"), rounding=ROUND_DOWN)
        return units * ROUNDING_UNIT

    @classmethod
    def compute(cls, annual_tax: Decimal) -> ResidenceTaxResult:
        if annual_tax < 0:
            raise ValueError("annual_tax must be non-negative")

        ordinary = cls._floor_to_unit(annual_tax / Decimal("12"))
        first_month = annual_tax - ordinary * Decimal("11")

        monthly = []
        for index, month in enumerate(SPECIAL_COLLECTION_MONTHS):
            amount = first_month if index == 0 else ordinary
            monthly.append(ResidenceTaxMonthlyAmount(month=month, amount=amount))

        return ResidenceTaxResult(
            annual_tax=annual_tax,
            first_month_amount=first_month,
            ordinary_month_amount=ordinary,
            monthly_amounts=tuple(monthly),
            total=first_month + ordinary * Decimal("11"),
        )
