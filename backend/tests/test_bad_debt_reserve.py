from decimal import Decimal

import pytest

from app.services.bad_debt_reserve import BadDebtReserveService


def test_wholesale_retail_rate():
    result = BadDebtReserveService.compute(
        receivables=Decimal("10000000"),
        industry="wholesale_retail",
    )
    assert result.statutory_rate == Decimal("0.010")
    assert result.base_amount == Decimal("10000000")
    assert result.reserve_limit == Decimal("100000")


def test_manufacturing_rate():
    result = BadDebtReserveService.compute(
        receivables=Decimal("5000000"),
        industry="manufacturing",
    )
    assert result.reserve_limit == Decimal("40000")


def test_non_receivable_deducted():
    result = BadDebtReserveService.compute(
        receivables=Decimal("10000000"),
        industry="wholesale_retail",
        non_receivable_amount=Decimal("2000000"),
    )
    assert result.base_amount == Decimal("8000000")
    assert result.reserve_limit == Decimal("80000")


def test_rounds_down():
    result = BadDebtReserveService.compute(
        receivables=Decimal("1234567"),
        industry="other",
    )
    # 1234567 * 0.006 = 7407.402 -> 7407
    assert result.reserve_limit == Decimal("7407")


def test_rate_override():
    result = BadDebtReserveService.compute(
        receivables=Decimal("1000000"),
        industry="other",
        statutory_rate=Decimal("0.013"),
    )
    assert result.statutory_rate == Decimal("0.013")
    assert result.reserve_limit == Decimal("13000")


def test_non_receivable_exceeds_base():
    result = BadDebtReserveService.compute(
        receivables=Decimal("1000000"),
        industry="other",
        non_receivable_amount=Decimal("2000000"),
    )
    assert result.base_amount == Decimal("0")
    assert result.reserve_limit == Decimal("0")


def test_invalid_industry_raises():
    with pytest.raises(ValueError):
        BadDebtReserveService.compute(
            receivables=Decimal("1000000"),
            industry="unknown",
        )


def test_negative_receivables_raises():
    with pytest.raises(ValueError):
        BadDebtReserveService.compute(
            receivables=Decimal("-1"),
            industry="other",
        )
