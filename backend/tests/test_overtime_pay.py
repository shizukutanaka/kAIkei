from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.overtime_pay import OvertimePayService


class TestOvertimePayService:
    def test_single_bucket_checks(self):
        result = OvertimePayService.compute(Decimal("2000"), overtime_hours=Decimal("10"))
        assert result.overtime_pay == Decimal("25000")
        assert result.overtime_over_60_pay == Decimal("0")
        assert result.late_night_pay == Decimal("0")
        assert result.holiday_pay == Decimal("0")
        assert result.total_premium == Decimal("25000")

        result = OvertimePayService.compute(Decimal("2000"), overtime_over_60_hours=Decimal("5"))
        assert result.overtime_over_60_pay == Decimal("15000")

        result = OvertimePayService.compute(Decimal("2000"), late_night_hours=Decimal("8"))
        assert result.late_night_pay == Decimal("4000")

        result = OvertimePayService.compute(Decimal("2000"), holiday_hours=Decimal("7"))
        assert result.holiday_pay == Decimal("18900")

    def test_combined_case(self):
        result = OvertimePayService.compute(
            Decimal("1800"),
            overtime_hours=Decimal("3"),
            overtime_over_60_hours=Decimal("2"),
            late_night_hours=Decimal("4"),
            holiday_hours=Decimal("1.5"),
        )
        assert result.total_premium == (
            result.overtime_pay + result.overtime_over_60_pay + result.late_night_pay + result.holiday_pay
        )

    def test_flooring_case(self):
        hourly_wage = Decimal("1234")
        hours = Decimal("1")
        result = OvertimePayService.compute(hourly_wage, overtime_hours=hours)
        expected = (hourly_wage * hours * Decimal("1.25")).quantize(Decimal("1"), rounding=ROUND_DOWN)
        assert result.overtime_pay == expected

    def test_negative_values_raise(self):
        with pytest.raises(ValueError):
            OvertimePayService.compute(Decimal("-1"))
        with pytest.raises(ValueError):
            OvertimePayService.compute(Decimal("1000"), overtime_hours=Decimal("-1"))
