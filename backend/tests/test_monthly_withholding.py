"""月次の源泉所得税（年税額の12分の1による概算）。

従来は総支給の5%を掛けており、実測でおよそ2倍を天引きしていた。
一律の率は累進にならないため、低所得者から取りすぎ、高所得者から取り足りない
という両方向の誤りになる。
"""
from decimal import Decimal

import pytest

from app.services.monthly_withholding import estimate_monthly_withholding


def test_low_income_owes_nothing():
    """給与所得控除と基礎控除の範囲内なら税額は0。

    旧実装（総支給の5%）は、納税義務のない人からも毎月徴収していた。
    """
    assert estimate_monthly_withholding(Decimal("80000"), Decimal("0")) == 0


def test_zero_gross_is_zero():
    assert estimate_monthly_withholding(Decimal("0"), Decimal("0")) == 0


def test_dependents_reduce_the_tax():
    without = estimate_monthly_withholding(Decimal("400000"), Decimal("60000"), 0)
    with_two = estimate_monthly_withholding(Decimal("400000"), Decimal("60000"), 2)

    assert with_two < without


def test_social_insurance_reduces_the_tax():
    """社会保険料は所得控除なので、多いほど税額は下がる。"""
    less = estimate_monthly_withholding(Decimal("400000"), Decimal("30000"))
    more = estimate_monthly_withholding(Decimal("400000"), Decimal("90000"))

    assert more < less


def test_is_progressive():
    """収入が2倍でも税額は2倍を超える（累進）。

    一律の率ではこの性質が出ないため、旧実装との違いが最も表れる。
    """
    low = estimate_monthly_withholding(Decimal("300000"), Decimal("45000"))
    high = estimate_monthly_withholding(Decimal("600000"), Decimal("90000"))

    assert high > low * 2


def test_differs_from_the_old_flat_rate():
    """旧実装（総支給の5%）とは大きく異なること。

    月給40万・社保6万で、旧: 20,000円 / 新: 約10,400円。
    """
    actual = estimate_monthly_withholding(Decimal("400000"), Decimal("60000"))
    old = Decimal("400000") * Decimal("0.05")

    assert actual < old / Decimal("1.5"), f"5%の概算に近すぎる（{actual}）"


def test_matches_the_annual_calculation():
    """年税額の12分の1であること（年末調整と整合する）。"""
    from app.services.income_deduction import basic_deduction, dependent_deduction
    from app.services.income_tax import IncomeTaxService
    from app.services.salary_deduction import SalaryIncomeDeductionService

    gross, social, dep = Decimal("500000"), Decimal("70000"), 1
    annual_gross = gross * 12
    salary_income = annual_gross - SalaryIncomeDeductionService.compute(annual_gross)
    taxable = salary_income - social * 12 - basic_deduction(salary_income) - dependent_deduction(dep)
    expected = (IncomeTaxService.compute(taxable) * Decimal("1.021") / 12).to_integral_value(
        rounding="ROUND_DOWN"
    )

    assert estimate_monthly_withholding(gross, social, dep) == expected


@pytest.mark.parametrize(
    ("gross", "social", "dependents"),
    [(Decimal("-1"), Decimal("0"), 0), (Decimal("1"), Decimal("-1"), 0), (Decimal("1"), Decimal("0"), -1)],
)
def test_rejects_negative_inputs(gross, social, dependents):
    with pytest.raises(ValueError):
        estimate_monthly_withholding(gross, social, dependents)
