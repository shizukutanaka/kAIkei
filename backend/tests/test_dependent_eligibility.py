from decimal import Decimal

import pytest

from app.services.dependent_eligibility import DependentEligibilityService


def test_cohabiting_eligible():
    result = DependentEligibilityService.check(
        annual_income=Decimal("1000000"), cohabiting=True, insured_annual_income=Decimal("5000000")
    )
    assert result.income_limit == Decimal("1300000")
    assert result.eligible is True
    assert result.reason == "eligible"


def test_income_over_limit():
    result = DependentEligibilityService.check(
        annual_income=Decimal("1300000"), cohabiting=True, insured_annual_income=Decimal("5000000")
    )
    assert result.income_requirement_met is False
    assert result.eligible is False
    assert result.reason == "annual_income_over_limit"


def test_senior_higher_limit():
    result = DependentEligibilityService.check(
        annual_income=Decimal("1500000"),
        is_senior_or_disabled=True,
        cohabiting=True,
        insured_annual_income=Decimal("6000000"),
    )
    assert result.income_limit == Decimal("1800000")
    assert result.eligible is True


def test_cohabiting_half_income_failed():
    result = DependentEligibilityService.check(
        annual_income=Decimal("1200000"), cohabiting=True, insured_annual_income=Decimal("2000000")
    )
    # 1,200,000 >= 2,000,000/2 -> relationship fails
    assert result.income_requirement_met is True
    assert result.relationship_requirement_met is False
    assert result.reason == "cohabiting_half_income_failed"


def test_separate_remittance_met():
    result = DependentEligibilityService.check(
        annual_income=Decimal("800000"), cohabiting=False, remittance_amount=Decimal("900000")
    )
    assert result.eligible is True


def test_separate_remittance_failed():
    result = DependentEligibilityService.check(
        annual_income=Decimal("800000"), cohabiting=False, remittance_amount=Decimal("700000")
    )
    assert result.relationship_requirement_met is False
    assert result.reason == "remittance_requirement_failed"


def test_cohabiting_missing_insured_income_raises():
    with pytest.raises(ValueError):
        DependentEligibilityService.check(annual_income=Decimal("1000000"), cohabiting=True)


def test_separate_missing_remittance_raises():
    with pytest.raises(ValueError):
        DependentEligibilityService.check(annual_income=Decimal("1000000"), cohabiting=False)


def test_negative_income_raises():
    with pytest.raises(ValueError):
        DependentEligibilityService.check(
            annual_income=Decimal("-1"), cohabiting=True, insured_annual_income=Decimal("5000000")
        )
