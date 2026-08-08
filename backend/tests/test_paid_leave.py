from decimal import Decimal

import pytest

from app.services.paid_leave import PaidLeaveService


def test_full_time_initial_grant():
    result = PaidLeaveService.grant_days(
        months_of_service=6, weekly_working_days=5, weekly_working_hours=Decimal("40"), attendance_rate=Decimal("0.9")
    )
    assert result.granted_days == 10
    assert result.is_proportional is False
    assert result.mandatory_5day_designation is True


def test_full_time_max_grant():
    result = PaidLeaveService.grant_days(
        months_of_service=78, weekly_working_days=5, weekly_working_hours=Decimal("40"), attendance_rate=Decimal("1")
    )
    assert result.granted_days == 20


def test_full_time_mid_grant():
    result = PaidLeaveService.grant_days(
        months_of_service=42, weekly_working_days=5, weekly_working_hours=Decimal("40"), attendance_rate=Decimal("1")
    )
    assert result.granted_days == 14


def test_not_yet_eligible_under_six_months():
    result = PaidLeaveService.grant_days(
        months_of_service=5, weekly_working_days=5, weekly_working_hours=Decimal("40"), attendance_rate=Decimal("1")
    )
    assert result.granted_days == 0


def test_attendance_requirement_not_met():
    result = PaidLeaveService.grant_days(
        months_of_service=12, weekly_working_days=5, weekly_working_hours=Decimal("40"), attendance_rate=Decimal("0.7")
    )
    assert result.granted_days == 0
    assert result.meets_attendance_requirement is False


def test_proportional_grant_four_days_initial():
    result = PaidLeaveService.grant_days(
        months_of_service=6, weekly_working_days=4, weekly_working_hours=Decimal("20"), attendance_rate=Decimal("1")
    )
    assert result.granted_days == 7
    assert result.is_proportional is True
    assert result.mandatory_5day_designation is False


def test_proportional_reaches_mandatory_threshold():
    result = PaidLeaveService.grant_days(
        months_of_service=42, weekly_working_days=4, weekly_working_hours=Decimal("20"), attendance_rate=Decimal("1")
    )
    assert result.granted_days == 10
    assert result.mandatory_5day_designation is True


def test_proportional_one_day():
    result = PaidLeaveService.grant_days(
        months_of_service=6, weekly_working_days=1, weekly_working_hours=Decimal("6"), attendance_rate=Decimal("1")
    )
    assert result.granted_days == 1


def test_thirty_plus_hours_is_full_time_even_with_few_days():
    result = PaidLeaveService.grant_days(
        months_of_service=6, weekly_working_days=4, weekly_working_hours=Decimal("32"), attendance_rate=Decimal("1")
    )
    assert result.granted_days == 10
    assert result.is_proportional is False


def test_negative_months_raises():
    with pytest.raises(ValueError):
        PaidLeaveService.grant_days(
            months_of_service=-1,
            weekly_working_days=5,
            weekly_working_hours=Decimal("40"),
            attendance_rate=Decimal("1"),
        )
