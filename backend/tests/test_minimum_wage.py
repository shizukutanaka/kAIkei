from decimal import Decimal

import pytest

from app.services.minimum_wage import MinimumWageService


def test_hourly_meets_minimum():
    result = MinimumWageService.check(
        minimum_hourly_wage=Decimal("1113"), wage_type="hourly", hourly_wage=Decimal("1200")
    )
    assert result.meets_minimum is True
    assert result.shortfall_per_hour == Decimal("0")
    assert result.effective_hourly_wage == Decimal("1200")


def test_hourly_below_minimum():
    result = MinimumWageService.check(
        minimum_hourly_wage=Decimal("1113"), wage_type="hourly", hourly_wage=Decimal("1000")
    )
    assert result.meets_minimum is False
    assert result.shortfall_per_hour == Decimal("113")


def test_monthly_conversion_meets():
    result = MinimumWageService.check(
        minimum_hourly_wage=Decimal("1113"),
        wage_type="monthly",
        monthly_wage=Decimal("200000"),
        monthly_scheduled_hours=Decimal("160"),
    )
    assert result.effective_hourly_wage == Decimal("1250.00")
    assert result.meets_minimum is True


def test_monthly_conversion_below():
    result = MinimumWageService.check(
        minimum_hourly_wage=Decimal("1113"),
        wage_type="monthly",
        monthly_wage=Decimal("170000"),
        monthly_scheduled_hours=Decimal("160"),
    )
    assert result.effective_hourly_wage == Decimal("1062.50")
    assert result.meets_minimum is False
    assert result.shortfall_per_hour == Decimal("50.50")


def test_exactly_at_minimum():
    result = MinimumWageService.check(
        minimum_hourly_wage=Decimal("1113"), wage_type="hourly", hourly_wage=Decimal("1113")
    )
    assert result.meets_minimum is True


def test_missing_hourly_raises():
    with pytest.raises(ValueError):
        MinimumWageService.check(minimum_hourly_wage=Decimal("1113"), wage_type="hourly")


def test_missing_monthly_inputs_raises():
    with pytest.raises(ValueError):
        MinimumWageService.check(
            minimum_hourly_wage=Decimal("1113"), wage_type="monthly", monthly_wage=Decimal("200000")
        )


def test_zero_scheduled_hours_raises():
    with pytest.raises(ValueError):
        MinimumWageService.check(
            minimum_hourly_wage=Decimal("1113"),
            wage_type="monthly",
            monthly_wage=Decimal("200000"),
            monthly_scheduled_hours=Decimal("0"),
        )


def test_unsupported_wage_type_raises():
    with pytest.raises(ValueError):
        MinimumWageService.check(minimum_hourly_wage=Decimal("1113"), wage_type="daily")
