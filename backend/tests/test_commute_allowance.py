from decimal import Decimal

import pytest

from app.services.commute_allowance import CommuteAllowanceService


def test_transit_within_limit_fully_non_taxable():
    result = CommuteAllowanceService.compute(mode="transit", monthly_allowance=Decimal("100000"))
    assert result.non_taxable_limit == Decimal("150000")
    assert result.non_taxable == Decimal("100000")
    assert result.taxable == Decimal("0")


def test_transit_over_limit_excess_taxable():
    result = CommuteAllowanceService.compute(mode="transit", monthly_allowance=Decimal("160000"))
    assert result.non_taxable == Decimal("150000")
    assert result.taxable == Decimal("10000")


def test_car_distance_bracket():
    result = CommuteAllowanceService.compute(
        mode="car", monthly_allowance=Decimal("10000"), one_way_distance_km=Decimal("12")
    )
    assert result.non_taxable_limit == Decimal("7100")
    assert result.non_taxable == Decimal("7100")
    assert result.taxable == Decimal("2900")


def test_car_under_2km_fully_taxable():
    result = CommuteAllowanceService.compute(
        mode="car", monthly_allowance=Decimal("5000"), one_way_distance_km=Decimal("1.5")
    )
    assert result.non_taxable_limit == Decimal("0")
    assert result.non_taxable == Decimal("0")
    assert result.taxable == Decimal("5000")


def test_car_top_bracket():
    result = CommuteAllowanceService.compute(
        mode="car", monthly_allowance=Decimal("40000"), one_way_distance_km=Decimal("60")
    )
    assert result.non_taxable_limit == Decimal("31600")


def test_car_boundary_inclusive_lower():
    result = CommuteAllowanceService.compute(
        mode="car", monthly_allowance=Decimal("40000"), one_way_distance_km=Decimal("55")
    )
    assert result.non_taxable_limit == Decimal("31600")


def test_car_requires_distance():
    with pytest.raises(ValueError):
        CommuteAllowanceService.compute(mode="car", monthly_allowance=Decimal("10000"))


def test_unsupported_mode_raises():
    with pytest.raises(ValueError):
        CommuteAllowanceService.compute(mode="walk", monthly_allowance=Decimal("0"))


def test_negative_allowance_raises():
    with pytest.raises(ValueError):
        CommuteAllowanceService.compute(mode="transit", monthly_allowance=Decimal("-1"))
