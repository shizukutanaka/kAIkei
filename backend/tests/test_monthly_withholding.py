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


class TestBonusWithholding:
    """賞与の源泉所得税（年税額の差額による概算）。

    一律10.21%は累進を無視するため両方向に誤る。低所得者からは取りすぎ、
    課税所得の無い人からも徴収し、高所得者からは取り足りない。
    """

    def test_low_income_is_not_overcharged(self):
        """月給20万・賞与40万では一律10.21%が実測3.6倍だった。"""
        from app.services.monthly_withholding import estimate_bonus_withholding

        actual = estimate_bonus_withholding(
            monthly_gross=Decimal("200000"),
            monthly_social_insurance=Decimal("30000"),
            bonus_gross=Decimal("400000"),
            bonus_social_insurance=Decimal("60000"),
        )
        flat = Decimal("400000") * Decimal("0.1021")

        assert actual < flat / 2, f"一律10.21%に近すぎる（{actual} / {flat}）"

    def test_no_tax_when_there_is_no_taxable_income(self):
        """扶養が多く課税所得が無ければ徴収しない。"""
        from app.services.monthly_withholding import estimate_bonus_withholding

        assert (
            estimate_bonus_withholding(
                monthly_gross=Decimal("200000"),
                monthly_social_insurance=Decimal("30000"),
                bonus_gross=Decimal("400000"),
                bonus_social_insurance=Decimal("60000"),
                dependents=3,
            )
            == 0
        )

    def test_high_income_is_not_undercharged(self):
        """高所得者では一律10.21%が徴収不足になる。"""
        from app.services.monthly_withholding import estimate_bonus_withholding

        actual = estimate_bonus_withholding(
            monthly_gross=Decimal("1000000"),
            monthly_social_insurance=Decimal("100000"),
            bonus_gross=Decimal("2000000"),
            bonus_social_insurance=Decimal("150000"),
        )
        flat = Decimal("2000000") * Decimal("0.1021")

        assert actual > flat, f"累進が効いていない（{actual} / {flat}）"

    def test_zero_bonus_is_zero(self):
        from app.services.monthly_withholding import estimate_bonus_withholding

        assert (
            estimate_bonus_withholding(
                monthly_gross=Decimal("400000"),
                monthly_social_insurance=Decimal("60000"),
                bonus_gross=Decimal("0"),
                bonus_social_insurance=Decimal("0"),
            )
            == 0
        )

    def test_is_the_marginal_tax_of_the_bonus(self):
        """賞与を含む年税額と含まない年税額の差であること。"""
        from app.services.monthly_withholding import _annual_tax, estimate_bonus_withholding

        m, ms, b, bs = Decimal("400000"), Decimal("60000"), Decimal("800000"), Decimal("120000")
        expected = (
            _annual_tax(m * 12 + b, ms * 12 + bs, 0) - _annual_tax(m * 12, ms * 12, 0)
        ).to_integral_value(rounding="ROUND_DOWN")

        assert estimate_bonus_withholding(m, ms, b, bs) == expected

    def test_rejects_negative(self):
        from app.services.monthly_withholding import estimate_bonus_withholding

        with pytest.raises(ValueError):
            estimate_bonus_withholding(
                monthly_gross=Decimal("-1"),
                monthly_social_insurance=Decimal("0"),
                bonus_gross=Decimal("1"),
                bonus_social_insurance=Decimal("0"),
            )
