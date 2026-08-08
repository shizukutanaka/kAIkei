from decimal import Decimal

import pytest

from app.services.high_age_benefit import HighAgeEmploymentBenefitService


def test_flat_rate_below_61_percent():
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=120,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("180000"),
    )
    assert result.eligible is True
    assert result.reduction_ratio == Decimal("0.6000")
    assert result.benefit_amount == Decimal("27000")


def test_declining_rate_between_61_and_75():
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=120,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("210000"),
    )
    assert result.eligible is True
    assert result.reduction_ratio == Decimal("0.7000")
    # 137.25/280*300000 - 183/280*210000 = 2745000/280 = 9803.57 -> floor 9803
    assert result.benefit_amount == Decimal("9803")


def test_ratio_at_or_above_75_not_payable():
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=120,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("240000"),
    )
    assert result.eligible is False
    assert "75%" in result.reason
    assert result.benefit_amount == Decimal("0")


def test_age_out_of_range():
    result = HighAgeEmploymentBenefitService.compute(
        age=66,
        insured_months=120,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("180000"),
    )
    assert result.eligible is False
    assert "60歳以上65歳未満" in result.reason


def test_insufficient_insured_months():
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=40,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("180000"),
    )
    assert result.eligible is False
    assert "被保険者期間" in result.reason


def test_below_minimum_benefit():
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=120,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("223500"),
    )
    assert result.eligible is False
    assert "最低限度額" in result.reason


def test_supply_limit_reduces_benefit():
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=120,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("180000"),
        supply_limit=Decimal("200000"),
    )
    assert result.eligible is True
    assert result.benefit_amount == Decimal("20000")


def test_current_wage_at_or_above_supply_limit():
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=120,
        wage_at_60=Decimal("300000"),
        current_wage=Decimal("210000"),
        supply_limit=Decimal("200000"),
    )
    assert result.eligible is False
    assert "支給限度額" in result.reason


def test_wage_at_60_capped():
    # wage_at_60 above cap -> clamped to 486300, changing the ratio
    result = HighAgeEmploymentBenefitService.compute(
        age=62,
        insured_months=120,
        wage_at_60=Decimal("600000"),
        current_wage=Decimal("290000"),
    )
    # ratio = 290000/486300 = 0.5963 -> flat 15%
    assert result.reduction_ratio == Decimal("0.5963")
    assert result.benefit_amount == Decimal("43500")


def test_invalid_wage_raises():
    with pytest.raises(ValueError):
        HighAgeEmploymentBenefitService.compute(
            age=62,
            insured_months=120,
            wage_at_60=Decimal("0"),
            current_wage=Decimal("180000"),
        )
