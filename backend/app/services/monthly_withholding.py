"""月次の源泉所得税を、年税額から按分して求める。

本来は「給与所得の源泉徴収税額表（月額表）」を、その月の社会保険料等控除後の
給与と扶養親族等の数で引く。この表そのものは未実装で、代わりに総支給の5%を
掛けていたため、実測でおよそ2倍を天引きしていた（月給40万・社保6万で
20,000円 / 妥当な水準は約10,400円）。

ここでは表を推測で作らず、**検証済みの法定計算を年額で組み立てて12で割る**。

    年間給与収入 → 給与所得控除（所得税法28条）
                 → 社会保険料控除・基礎控除（86条）・扶養控除（84条）
                 → 速算表（89条）→ 復興特別所得税 2.1% → ÷12

月額表は同じ考え方を表に落としたものなので、結果は近い値になる。ただし表の
丸めや区分の刻みまでは一致しないため、**月額表そのものではない**。年末調整で
精算される前提の概算として扱い、その旨は応答と画面で明示する。

賞与は算出率表（前月給与を基準にする別の仕組み）なので、ここでは扱わない。
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from app.services.income_deduction import basic_deduction, dependent_deduction
from app.services.income_tax import IncomeTaxService
from app.services.salary_deduction import SalaryIncomeDeductionService

MONTHS_PER_YEAR = Decimal("12")
# 復興特別所得税（復興財源確保法28条）。源泉徴収税額に2.1%を上乗せする。
RECONSTRUCTION_MULTIPLIER = Decimal("1.021")


def estimate_monthly_withholding(
    monthly_gross: Decimal,
    monthly_social_insurance: Decimal,
    dependents: int = 0,
) -> Decimal:
    """その月の源泉所得税額（概算）。

    月額表ではなく年税額の12分の1。年末調整で精算されるため、年間で見れば
    過不足は解消する。
    """
    if monthly_gross < 0 or monthly_social_insurance < 0:
        raise ValueError("amounts must be non-negative")
    if dependents < 0:
        raise ValueError("dependents must be non-negative")
    if monthly_gross <= 0:
        return Decimal("0")

    annual_gross = monthly_gross * MONTHS_PER_YEAR
    salary_income = annual_gross - SalaryIncomeDeductionService.compute(annual_gross)

    deductions = (
        monthly_social_insurance * MONTHS_PER_YEAR
        + basic_deduction(salary_income)
        + dependent_deduction(dependents)
    )
    taxable_income = max(salary_income - deductions, Decimal("0"))

    annual_tax = IncomeTaxService.compute(taxable_income) * RECONSTRUCTION_MULTIPLIER
    # 1円未満は切り捨てる（国税通則法119条1項）。
    return (annual_tax / MONTHS_PER_YEAR).quantize(Decimal("1"), rounding=ROUND_DOWN)
