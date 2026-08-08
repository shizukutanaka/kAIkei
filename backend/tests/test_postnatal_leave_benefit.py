from decimal import Decimal

import pytest

from app.services.postnatal_leave_benefit import PostnatalLeaveBenefitService


def test_basic_28_days_at_67_percent():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=12,
        leave_days=28,
    )
    assert result.eligible is True
    assert result.daily_wage == Decimal("10000")
    assert result.payable_days == 28
    # 10000*28*0.67 = 187600
    assert result.benefit_amount == Decimal("187600")


def test_daily_wage_cap():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("6000000"),
        insured_months=24,
        leave_days=28,
    )
    assert result.daily_wage == Decimal("15430")


def test_daily_wage_floor():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("100000"),
        insured_months=12,
        leave_days=10,
    )
    assert result.daily_wage == Decimal("2869")


def test_remaining_days_capped_at_28():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=12,
        leave_days=28,
        cumulative_days_before=20,
    )
    assert result.payable_days == 8
    # 10000*8*0.67 = 53600
    assert result.benefit_amount == Decimal("53600")


def test_exhausted_days_ineligible():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=12,
        leave_days=5,
        cumulative_days_before=28,
    )
    assert result.eligible is False


def test_no_payment_at_80_percent_wage():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=12,
        leave_days=28,
        wage_paid_during_leave=Decimal("224000"),
    )
    assert result.eligible is False


def test_reduced_payment_between_thresholds():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=12,
        leave_days=28,
        wage_paid_during_leave=Decimal("100000"),
    )
    # 280000*0.8 - 100000 = 124000 < gross 187600
    assert result.benefit_amount == Decimal("124000")


def test_full_payment_below_lower_threshold():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=12,
        leave_days=28,
        wage_paid_during_leave=Decimal("30000"),
    )
    assert result.benefit_amount == Decimal("187600")


def test_insufficient_insured_months():
    result = PostnatalLeaveBenefitService.compute(
        wage_total_6m=Decimal("1800000"),
        insured_months=6,
        leave_days=28,
    )
    assert result.eligible is False


def test_invalid_wage_raises():
    with pytest.raises(ValueError):
        PostnatalLeaveBenefitService.compute(
            wage_total_6m=Decimal("0"),
            insured_months=12,
            leave_days=28,
        )
