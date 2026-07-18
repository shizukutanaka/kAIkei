from decimal import Decimal

import pytest

from app.services.short_time_insurance import ShortTimeWorkerInsuranceService


def _base(**overrides):
    kwargs = dict(
        weekly_hours=Decimal("20"),
        monthly_wage=Decimal("88000"),
        employment_over_2_months=True,
        is_student=False,
        company_insured_count=51,
        labor_agreement=False,
        meets_three_quarters_standard=False,
    )
    kwargs.update(overrides)
    return kwargs


def test_all_criteria_met():
    result = ShortTimeWorkerInsuranceService.judge(**_base())
    assert result.covered is True
    assert result.is_specified_workplace is True
    assert result.reasons == ()


def test_hours_below_threshold():
    result = ShortTimeWorkerInsuranceService.judge(**_base(weekly_hours=Decimal("19.5")))
    assert result.covered is False
    assert result.meets_hours is False
    assert "週所定労働時間が20時間未満" in result.reasons


def test_wage_below_threshold():
    result = ShortTimeWorkerInsuranceService.judge(**_base(monthly_wage=Decimal("87999")))
    assert result.covered is False
    assert result.meets_wage is False
    assert "月額賃金が88,000円未満" in result.reasons


def test_student_excluded():
    result = ShortTimeWorkerInsuranceService.judge(**_base(is_student=True))
    assert result.covered is False
    assert result.not_student is False
    assert "学生である" in result.reasons


def test_short_employment():
    result = ShortTimeWorkerInsuranceService.judge(**_base(employment_over_2_months=False))
    assert result.covered is False
    assert "2か月を超える雇用見込みがない" in result.reasons


def test_not_specified_workplace():
    result = ShortTimeWorkerInsuranceService.judge(**_base(company_insured_count=50))
    assert result.is_specified_workplace is False
    assert result.covered is False
    assert "特定適用事業所でない" in result.reasons


def test_labor_agreement_makes_specified():
    result = ShortTimeWorkerInsuranceService.judge(
        **_base(company_insured_count=30, labor_agreement=True)
    )
    assert result.is_specified_workplace is True
    assert result.covered is True


def test_three_quarters_standard_covers_regardless():
    result = ShortTimeWorkerInsuranceService.judge(
        **_base(
            weekly_hours=Decimal("30"),
            company_insured_count=10,
            meets_three_quarters_standard=True,
        )
    )
    assert result.covered is True
    assert result.reasons == ()


def test_multiple_reasons():
    result = ShortTimeWorkerInsuranceService.judge(
        **_base(
            weekly_hours=Decimal("10"),
            monthly_wage=Decimal("50000"),
            company_insured_count=5,
        )
    )
    assert result.covered is False
    assert len(result.reasons) >= 3


def test_negative_hours_raises():
    with pytest.raises(ValueError):
        ShortTimeWorkerInsuranceService.judge(**_base(weekly_hours=Decimal("-1")))
