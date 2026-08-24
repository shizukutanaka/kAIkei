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

賞与も同じ考え方で扱う（`estimate_bonus_withholding`）。本来は「賞与に対する
源泉徴収税額の算出率表」を前月給与と扶養親族等の数で引くが、表が無いので
「賞与を含む年税額 − 含まない年税額」を賞与分の税額とする。
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from app.services.income_deduction import basic_deduction, dependent_deduction
from app.services.income_tax import IncomeTaxService
from app.services.salary_deduction import SalaryIncomeDeductionService

MONTHS_PER_YEAR = Decimal("12")
# 復興特別所得税（復興財源確保法28条）。源泉徴収税額に2.1%を上乗せする。
RECONSTRUCTION_MULTIPLIER = Decimal("1.021")


def _annual_tax(
    annual_gross: Decimal,
    annual_social_insurance: Decimal,
    dependents: int,
) -> Decimal:
    """年間の給与収入に対する所得税額（復興特別所得税込み・端数処理前）。"""
    salary_income = annual_gross - SalaryIncomeDeductionService.compute(annual_gross)
    deductions = (
        annual_social_insurance + basic_deduction(salary_income) + dependent_deduction(dependents)
    )
    taxable_income = max(salary_income - deductions, Decimal("0"))
    return IncomeTaxService.compute(taxable_income) * RECONSTRUCTION_MULTIPLIER


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

    annual_tax = _annual_tax(
        monthly_gross * MONTHS_PER_YEAR,
        monthly_social_insurance * MONTHS_PER_YEAR,
        dependents,
    )
    # 1円未満は切り捨てる（国税通則法119条1項）。
    return (annual_tax / MONTHS_PER_YEAR).quantize(Decimal("1"), rounding=ROUND_DOWN)


def estimate_bonus_withholding(
    monthly_gross: Decimal,
    monthly_social_insurance: Decimal,
    bonus_gross: Decimal,
    bonus_social_insurance: Decimal,
    dependents: int = 0,
) -> Decimal:
    """賞与の源泉所得税額（概算）。

    本来は「賞与に対する源泉徴収税額の算出率表」を、前月の社会保険料等控除後
    給与と扶養親族等の数で引いて率を求める。表が無いため、賞与を含む年税額と
    含まない年税額の差額（＝賞与に対応する限界税額）を用いる。

    一律 10.21% を掛けていた旧実装は両方向に誤っていた。累進を無視するため、
    低所得者からは取りすぎ（月給20万・賞与40万で実測3.6倍）、扶養が多く
    課税所得が無い人からも徴収し、高所得者からは取り足りない。
    """
    for name, value in (
        ("monthly_gross", monthly_gross),
        ("monthly_social_insurance", monthly_social_insurance),
        ("bonus_gross", bonus_gross),
        ("bonus_social_insurance", bonus_social_insurance),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if dependents < 0:
        raise ValueError("dependents must be non-negative")
    if bonus_gross <= 0:
        return Decimal("0")

    annual_salary = monthly_gross * MONTHS_PER_YEAR
    annual_social = monthly_social_insurance * MONTHS_PER_YEAR

    without_bonus = _annual_tax(annual_salary, annual_social, dependents)
    with_bonus = _annual_tax(
        annual_salary + bonus_gross,
        annual_social + bonus_social_insurance,
        dependents,
    )

    difference = with_bonus - without_bonus
    if difference <= 0:
        return Decimal("0")
    # 1円未満は切り捨てる（国税通則法119条1項）。
    return difference.quantize(Decimal("1"), rounding=ROUND_DOWN)
