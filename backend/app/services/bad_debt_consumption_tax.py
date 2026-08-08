"""貸倒れに係る消費税額の控除(消費税法39条)。

課税資産の譲渡等に係る売掛金その他の債権が貸倒れとなり、その税込価額を領収でき
なくなった場合、貸倒れとなった金額に含まれる消費税額を、その貸倒れの発生した課税
期間の売上に対する消費税額から控除できる。

控除税額:
    貸倒れに係る消費税額 = 貸倒れとなった税込金額 × 税率 / (1 + 税率)

税率は課税売上の適用税率(標準10% / 軽減8%)。消費税額の抽出は国税庁の端数処理
(円未満切捨)に従い、既存の TaxCalculator に委譲する。

貸倒れの範囲(更生計画・特別清算・債務免除・回収不能等)は法令・通達に従って別途
判定する前提で、本サービスは確定した貸倒れ税込金額と適用税率から控除税額を算定する。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.tax_calculator import TaxCalculator

STANDARD_RATE = Decimal("0.10")
REDUCED_RATE = Decimal("0.08")
ALLOWED_RATES: tuple[Decimal, ...] = (STANDARD_RATE, REDUCED_RATE)


@dataclass(frozen=True)
class BadDebtConsumptionTaxResult:
    bad_debt_amount: Decimal
    tax_rate: Decimal
    taxable_base: Decimal
    deductible_tax: Decimal


class BadDebtConsumptionTaxService:
    """貸倒れに係る消費税額の控除額を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        bad_debt_amount: Decimal,
        tax_rate: Decimal = STANDARD_RATE,
    ) -> BadDebtConsumptionTaxResult:
        if bad_debt_amount < 0:
            raise ValueError("bad_debt_amount must not be negative")
        if tax_rate not in ALLOWED_RATES:
            raise ValueError("unsupported tax_rate")

        taxable_base, deductible_tax = TaxCalculator.calculate_tax(
            bad_debt_amount, tax_rate, is_inclusive=True
        )

        return BadDebtConsumptionTaxResult(
            bad_debt_amount=bad_debt_amount,
            tax_rate=tax_rate,
            taxable_base=taxable_base,
            deductible_tax=deductible_tax,
        )
