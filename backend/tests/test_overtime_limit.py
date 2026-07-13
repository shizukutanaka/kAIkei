from decimal import Decimal

import pytest

from app.services.overtime_limit import MonthlyOvertime, OvertimeLimitService


def _months(overtime, holiday=0, n=12):
    return [MonthlyOvertime(overtime_hours=Decimal(str(overtime)), holiday_work_hours=Decimal(str(holiday))) for _ in range(n)]


def test_all_compliant():
    result = OvertimeLimitService.check(_months(40))
    assert result.compliant is True
    assert result.violations == ()
    assert result.annual_overtime_total == Decimal("480")


def test_annual_limit_exceeded():
    result = OvertimeLimitService.check(_months(61))
    assert result.annual_limit_exceeded is True
    assert "annual_overtime_over_720" in result.violations


def test_over_45_more_than_six_months():
    months = _months(46, n=7) + _months(40, n=5)
    result = OvertimeLimitService.check(months)
    assert result.months_over_45_count == 7
    assert result.months_over_45_limit_exceeded is True
    assert "over_45_more_than_6_months" in result.violations


def test_single_month_combined_100():
    months = _months(40, n=11) + [MonthlyOvertime(overtime_hours=Decimal("90"), holiday_work_hours=Decimal("15"))]
    result = OvertimeLimitService.check(months)
    assert result.single_month_combined_exceeded is True
    assert "single_month_combined_100_or_more" in result.violations


def test_multi_month_average_over_80():
    months = [
        MonthlyOvertime(overtime_hours=Decimal("40"), holiday_work_hours=Decimal("45")),
        MonthlyOvertime(overtime_hours=Decimal("40"), holiday_work_hours=Decimal("45")),
    ] + _months(30, n=10)
    result = OvertimeLimitService.check(months)
    assert result.multi_month_average_exceeded is True
    assert "multi_month_average_over_80" in result.violations


def test_exactly_80_average_is_compliant():
    months = [
        MonthlyOvertime(overtime_hours=Decimal("40"), holiday_work_hours=Decimal("40")),
        MonthlyOvertime(overtime_hours=Decimal("40"), holiday_work_hours=Decimal("40")),
    ]
    result = OvertimeLimitService.check(months)
    assert result.multi_month_average_exceeded is False


def test_empty_raises():
    with pytest.raises(ValueError):
        OvertimeLimitService.check([])


def test_negative_raises():
    with pytest.raises(ValueError):
        OvertimeLimitService.check([MonthlyOvertime(overtime_hours=Decimal("-1"))])
