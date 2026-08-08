from decimal import Decimal

import pytest

from app.services.health_insurance_benefit import HealthInsuranceBenefitService


def test_daily_benefit_rounding():
    result = HealthInsuranceBenefitService.daily_benefit(
        avg_standard_monthly=Decimal("300000"), insured_months=12
    )
    assert result.daily_base == Decimal("10000")
    assert result.daily_benefit == Decimal("6667")


def test_daily_benefit_under_12_months_uses_lower():
    result = HealthInsuranceBenefitService.daily_benefit(
        avg_standard_monthly=Decimal("400000"), insured_months=6
    )
    # capped to standard_average 300000 -> daily 6667
    assert result.daily_benefit == Decimal("6667")


def test_injury_with_waiting_period():
    result = HealthInsuranceBenefitService.injury_allowance(
        avg_standard_monthly=Decimal("300000"),
        insured_months=12,
        absent_days=30,
    )
    assert result.payable_days == 27
    assert result.daily_benefit == Decimal("6667")
    assert result.total_amount == Decimal("180009")


def test_injury_waiting_completed():
    result = HealthInsuranceBenefitService.injury_allowance(
        avg_standard_monthly=Decimal("300000"),
        insured_months=12,
        absent_days=30,
        waiting_completed=True,
    )
    assert result.payable_days == 30
    assert result.total_amount == Decimal("200010")


def test_injury_with_remuneration_offset():
    result = HealthInsuranceBenefitService.injury_allowance(
        avg_standard_monthly=Decimal("300000"),
        insured_months=12,
        absent_days=10,
        waiting_completed=True,
        daily_remuneration=Decimal("5000"),
    )
    assert result.effective_daily_benefit == Decimal("1667")
    assert result.total_amount == Decimal("16670")


def test_injury_remuneration_exceeds_benefit():
    result = HealthInsuranceBenefitService.injury_allowance(
        avg_standard_monthly=Decimal("300000"),
        insured_months=12,
        absent_days=10,
        waiting_completed=True,
        daily_remuneration=Decimal("8000"),
    )
    assert result.effective_daily_benefit == Decimal("0")
    assert result.total_amount == Decimal("0")


def test_maternity_single_full_window():
    result = HealthInsuranceBenefitService.maternity_allowance(
        avg_standard_monthly=Decimal("300000"),
        insured_months=12,
        days_before_birth=42,
        days_after_birth=56,
    )
    assert result.payable_days == 98
    assert result.total_amount == Decimal("653366")


def test_maternity_before_capped_single():
    result = HealthInsuranceBenefitService.maternity_allowance(
        avg_standard_monthly=Decimal("300000"),
        insured_months=12,
        days_before_birth=50,
        days_after_birth=56,
    )
    assert result.payable_days == 98


def test_maternity_multiple_pregnancy_window():
    result = HealthInsuranceBenefitService.maternity_allowance(
        avg_standard_monthly=Decimal("300000"),
        insured_months=12,
        days_before_birth=100,
        days_after_birth=60,
        multiple_pregnancy=True,
    )
    assert result.payable_days == 98 + 56


def test_invalid_avg_raises():
    with pytest.raises(ValueError):
        HealthInsuranceBenefitService.injury_allowance(
            avg_standard_monthly=Decimal("0"),
            insured_months=12,
            absent_days=10,
        )
