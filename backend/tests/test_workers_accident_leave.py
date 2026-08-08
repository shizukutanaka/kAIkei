from decimal import Decimal

import pytest

from app.services.workers_accident_leave import WorkersAccidentLeaveService


def test_basic_with_waiting_period():
    result = WorkersAccidentLeaveService.compute(
        daily_wage_base=Decimal("10000"),
        absent_days=10,
    )
    assert result.daily_compensation == Decimal("6000")
    assert result.daily_special == Decimal("2000")
    assert result.payable_days == 7  # 10 - 3 waiting
    assert result.total_compensation == Decimal("42000")
    assert result.total_special == Decimal("14000")
    assert result.total_benefit == Decimal("56000")


def test_waiting_completed():
    result = WorkersAccidentLeaveService.compute(
        daily_wage_base=Decimal("10000"),
        absent_days=10,
        waiting_completed=True,
    )
    assert result.payable_days == 10
    assert result.total_benefit == Decimal("80000")


def test_within_waiting_period_no_payment():
    result = WorkersAccidentLeaveService.compute(
        daily_wage_base=Decimal("10000"),
        absent_days=3,
    )
    assert result.payable_days == 0
    assert result.total_benefit == Decimal("0")
    assert result.daily_compensation == Decimal("6000")


def test_partial_work_deducts_wage():
    result = WorkersAccidentLeaveService.compute(
        daily_wage_base=Decimal("10000"),
        absent_days=5,
        waiting_completed=True,
        daily_partial_wage=Decimal("4000"),
    )
    # base = 6000 -> 60%=3600, 20%=1200
    assert result.daily_compensation == Decimal("3600")
    assert result.daily_special == Decimal("1200")
    assert result.total_benefit == Decimal("24000")


def test_rounding_down_daily_amounts():
    result = WorkersAccidentLeaveService.compute(
        daily_wage_base=Decimal("9999"),
        absent_days=4,
    )
    # 9999*0.6=5999.4 -> 5999, 9999*0.2=1999.8 -> 1999
    assert result.daily_compensation == Decimal("5999")
    assert result.daily_special == Decimal("1999")
    assert result.payable_days == 1
    assert result.total_benefit == Decimal("7998")


def test_partial_wage_at_or_above_base_yields_zero():
    result = WorkersAccidentLeaveService.compute(
        daily_wage_base=Decimal("8000"),
        absent_days=5,
        waiting_completed=True,
        daily_partial_wage=Decimal("8000"),
    )
    assert result.daily_compensation == Decimal("0")
    assert result.total_benefit == Decimal("0")


def test_invalid_daily_wage_base_raises():
    with pytest.raises(ValueError):
        WorkersAccidentLeaveService.compute(
            daily_wage_base=Decimal("0"),
            absent_days=5,
        )


def test_negative_absent_days_raises():
    with pytest.raises(ValueError):
        WorkersAccidentLeaveService.compute(
            daily_wage_base=Decimal("10000"),
            absent_days=-1,
        )
