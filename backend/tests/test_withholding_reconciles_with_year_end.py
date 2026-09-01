"""源泉徴収の合計が年末調整の年税額と一致すること。

月次・賞与の源泉徴収は法定の「月額表」「算出率表」ではなく、検証済みの部品から
組み立てた概算になっている（改善7）。**概算であることが許されるのは、年間で
精算されて過不足が消えるから**であって、そうでなければ単に誤った金額を
毎月徴収していることになる。

この性質は月次側・賞与側・年末調整側の3つに跨っており、どれか1つを触った
瞬間に静かに壊れる。個別のテストは各部品が正しいことしか言わないので、
**3つを繋いだときに辻褄が合う**ことをここで固定する。

許容差は端数処理の分だけ:

- 年税額は百円未満切捨（所得税法施行規則）で最大 99円
- 月次は1円未満切捨を12回で最大 12円
- 賞与も1円未満切捨で最大 1円

合計 112円未満に収まらなければ、端数ではなく計算の食い違い。
"""
from decimal import Decimal

import pytest

from app.services.income_deduction import basic_deduction, dependent_deduction
from app.services.monthly_withholding import (
    estimate_bonus_withholding,
    estimate_monthly_withholding,
)
from app.services.salary_deduction import SalaryIncomeDeductionService
from app.services.year_end_adjustment import YearEndAdjustmentService

# 端数処理だけで説明できる上限。これを超えたら定義がずれている。
ROUNDING_TOLERANCE = Decimal("112")


def _year_tax(annual_gross: Decimal, annual_social_insurance: Decimal, dependents: int, withheld: Decimal):
    """年末調整を、月次と同じ控除の組み立てで実行する。"""
    salary_income = annual_gross - SalaryIncomeDeductionService.compute(annual_gross)
    deductions = (
        annual_social_insurance
        + basic_deduction(salary_income)
        + dependent_deduction(dependents)
    )
    return YearEndAdjustmentService.compute(
        annual_gross_salary=annual_gross,
        total_income_deductions=deductions,
        withheld_tax_total=withheld,
    )


@pytest.mark.parametrize(
    "monthly_gross,monthly_si,dependents",
    [
        (Decimal("300000"), Decimal("45000"), 0),
        (Decimal("400000"), Decimal("60000"), 2),
        (Decimal("250000"), Decimal("37000"), 1),
        (Decimal("800000"), Decimal("100000"), 0),
        (Decimal("180000"), Decimal("27000"), 3),
        (Decimal("80000"), Decimal("12000"), 0),
    ],
)
def test_monthly_withholding_adds_up_to_the_year_tax(monthly_gross, monthly_si, dependents):
    """給与だけの年。月次×12 が年税額と端数の範囲で一致すること。"""
    withheld = estimate_monthly_withholding(monthly_gross, monthly_si, dependents) * 12

    result = _year_tax(monthly_gross * 12, monthly_si * 12, dependents, withheld)

    assert abs(withheld - result.year_tax) < ROUNDING_TOLERANCE, (
        f"月次×12={withheld} と年税額={result.year_tax} の差が端数で説明できない"
    )


@pytest.mark.parametrize(
    "monthly_gross,monthly_si,bonus,bonus_si,dependents",
    [
        (Decimal("300000"), Decimal("45000"), Decimal("600000"), Decimal("90000"), 0),
        (Decimal("400000"), Decimal("60000"), Decimal("800000"), Decimal("120000"), 2),
        (Decimal("200000"), Decimal("30000"), Decimal("400000"), Decimal("60000"), 1),
        (Decimal("1000000"), Decimal("120000"), Decimal("2000000"), Decimal("200000"), 0),
    ],
)
def test_bonus_withholding_adds_up_to_the_year_tax(
    monthly_gross, monthly_si, bonus, bonus_si, dependents
):
    """賞与のある年。月次×12＋賞与 が年税額と端数の範囲で一致すること。

    賞与は「賞与を含む年税額 − 含まない年税額」で求めているので、
    足し戻せば年税額になるはず。ならなければ差分の取り方が間違っている。
    """
    withheld = (
        estimate_monthly_withholding(monthly_gross, monthly_si, dependents) * 12
        + estimate_bonus_withholding(monthly_gross, monthly_si, bonus, bonus_si, dependents)
    )

    result = _year_tax(
        monthly_gross * 12 + bonus, monthly_si * 12 + bonus_si, dependents, withheld
    )

    assert abs(withheld - result.year_tax) < ROUNDING_TOLERANCE, (
        f"徴収計={withheld} と年税額={result.year_tax} の差が端数で説明できない"
    )


def test_the_year_end_settlement_is_therefore_near_zero():
    """結果として、年末調整の過不足がほぼ0になること。

    利用者から見て意味があるのはこの数字。毎月きちんと徴収できていれば、
    12月に大きな追徴や還付は出ない。
    """
    monthly, si = Decimal("350000"), Decimal("52000")
    withheld = estimate_monthly_withholding(monthly, si, 1) * 12

    result = _year_tax(monthly * 12, si * 12, 1, withheld)

    settlement = result.refund + result.additional_collection

    assert settlement < ROUNDING_TOLERANCE, (
        f"年末調整で 還付{result.refund}円 / 追徴{result.additional_collection}円 が出ている"
    )


def test_a_broken_monthly_calculation_would_be_caught():
    """このテストが本当に食い違いを検出できること。

    一律5%だった旧実装（改善7で是正済み）を再現すると、年税額と大きくずれる。
    ずれを検出できなければ、上のテストは何も守っていない。
    """
    monthly, si = Decimal("400000"), Decimal("60000")
    flat_rate_withheld = (monthly - si) * Decimal("0.05") * 12

    result = _year_tax(monthly * 12, si * 12, 0, flat_rate_withheld)

    assert abs(flat_rate_withheld - result.year_tax) >= ROUNDING_TOLERANCE, (
        "一律5%でも許容差に収まってしまう。許容差が広すぎる。"
    )
