from decimal import Decimal

import pytest

from app.services.caregiver_leave_benefit import CaregiverLeaveBenefitService


def test_basic_67_percent():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=24,
    )
    assert result.eligible is True
    assert result.daily_wage == Decimal("10000")
    assert result.payable_days == 30
    assert result.benefit_amount == Decimal("201000")


def test_daily_wage_cap():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("3600000"),
        insured_months=24,
    )
    assert result.daily_wage == Decimal("17270")
    # 17270*30*0.67 = 347127 = supply limit
    assert result.benefit_amount == Decimal("347127")


def test_daily_wage_floor():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("360000"),
        insured_months=24,
    )
    assert result.daily_wage == Decimal("2869")
    # 2869*30*0.67 = 57666.9 -> floor 57666
    assert result.benefit_amount == Decimal("57666")


def test_remaining_days_capped_at_93():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=24,
        cumulative_days_before=80,
    )
    assert result.payable_days == 13
    # 10000*13*0.67 = 87100
    assert result.benefit_amount == Decimal("87100")


def test_ineligible_when_total_days_exhausted():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=24,
        cumulative_days_before=93,
    )
    assert result.eligible is False
    assert "93日" in result.reason


def test_no_payment_when_wage_over_80_percent():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=24,
        wage_paid_during_leave=Decimal("240000"),
    )
    assert result.eligible is False
    assert "80%" in result.reason


def test_reduced_when_wage_between_floor_and_80_percent():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=24,
        wage_paid_during_leave=Decimal("100000"),
    )
    assert result.eligible is True
    # min(201000, 240000 - 100000 = 140000) = 140000
    assert result.benefit_amount == Decimal("140000")


def test_full_benefit_when_wage_below_reduction_floor():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=24,
        wage_paid_during_leave=Decimal("30000"),
    )
    assert result.eligible is True
    assert result.benefit_amount == Decimal("201000")


def test_ineligible_when_insured_months_below_12():
    result = CaregiverLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=6,
    )
    assert result.eligible is False
    assert "12か月" in result.reason


def test_invalid_wage_total_raises():
    with pytest.raises(ValueError):
        CaregiverLeaveBenefitService.compute(
            wage_total_6m=Decimal("0"),
            insured_months=24,
        )
