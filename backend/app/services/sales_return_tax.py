"""売上げに係る対価の返還等に係る消費税額の控除(消費税法38条)。

課税売上について、返品・値引き・割戻し(売上割戻)等により対価の返還等を行った
場合、その返還額に含まれる消費税額を、売上に対する消費税額から控除できる。

控除税額(税率区分ごとに集計してから抽出):
    区分ごとの控除税額 = 区分別の返還額合計(税込) × 税率 / (1 + 税率)

税率は課税売上の適用税率(標準10% / 軽減8%)。端数処理は国税庁ルール(円未満切捨)に
従い、既存の TaxCalculator に委譲する。返還等の事実・区分は別途判定する前提で、
本サービスは確定した返還額(税込)と適用税率から控除税額を算定する。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.services.tax_calculator import TaxCalculator

STANDARD_RATE = Decimal("0.10")
REDUCED_RATE = Decimal("0.08")
ALLOWED_RATES: tuple[Decimal, ...] = (STANDARD_RATE, REDUCED_RATE)


@dataclass(frozen=True)
class SalesReturnLine:
    amount: Decimal
    tax_rate: Decimal


@dataclass(frozen=True)
class SalesReturnRateBreakdown:
    tax_rate: Decimal
    return_amount: Decimal
    deductible_tax: Decimal


@dataclass(frozen=True)
class SalesReturnTaxResult:
    by_rate: list[SalesReturnRateBreakdown]
    total_return: Decimal
    total_deductible_tax: Decimal


class SalesReturnTaxService:
    """売上対価の返還等に係る控除税額を算定する純粋サービス。"""

    @classmethod
    def compute(cls, returns: list[SalesReturnLine]) -> SalesReturnTaxResult:
        if not returns:
            raise ValueError("returns must not be empty")

        grouped: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0"))
        for line in returns:
            if line.amount < 0:
                raise ValueError("amount must not be negative")
            if line.tax_rate not in ALLOWED_RATES:
                raise ValueError("unsupported tax_rate")
            grouped[line.tax_rate] += line.amount

        by_rate: list[SalesReturnRateBreakdown] = []
        total_return = Decimal("0")
        total_deductible_tax = Decimal("0")

        for tax_rate in sorted(grouped):
            return_amount = grouped[tax_rate]
            _, deductible_tax = TaxCalculator.calculate_tax(
                return_amount, tax_rate, is_inclusive=True
            )
            by_rate.append(
                SalesReturnRateBreakdown(
                    tax_rate=tax_rate,
                    return_amount=return_amount,
                    deductible_tax=deductible_tax,
                )
            )
            total_return += return_amount
            total_deductible_tax += deductible_tax

        return SalesReturnTaxResult(
            by_rate=by_rate,
            total_return=total_return,
            total_deductible_tax=total_deductible_tax,
        )
