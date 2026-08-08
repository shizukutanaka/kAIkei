from decimal import Decimal

import pytest

from app.services.bad_debt_consumption_tax import BadDebtConsumptionTaxService


def test_standard_rate():
    result = BadDebtConsumptionTaxService.compute(
        bad_debt_amount=Decimal("110000"),
        tax_rate=Decimal("0.10"),
    )
    assert result.deductible_tax == Decimal("10000")
    assert result.taxable_base == Decimal("100000")


def test_reduced_rate():
    result = BadDebtConsumptionTaxService.compute(
        bad_debt_amount=Decimal("108000"),
        tax_rate=Decimal("0.08"),
    )
    assert result.deductible_tax == Decimal("8000")
    assert result.taxable_base == Decimal("100000")


def test_default_rate_is_standard():
    result = BadDebtConsumptionTaxService.compute(
        bad_debt_amount=Decimal("110000"),
    )
    assert result.tax_rate == Decimal("0.10")
    assert result.deductible_tax == Decimal("10000")


def test_rounds_down():
    result = BadDebtConsumptionTaxService.compute(
        bad_debt_amount=Decimal("333"),
    )
    # 333*0.1/1.1 = 30.27 -> 30
    assert result.deductible_tax == Decimal("30")


def test_zero_amount():
    result = BadDebtConsumptionTaxService.compute(
        bad_debt_amount=Decimal("0"),
    )
    assert result.deductible_tax == Decimal("0")
    assert result.taxable_base == Decimal("0")


def test_unsupported_rate_raises():
    with pytest.raises(ValueError):
        BadDebtConsumptionTaxService.compute(
            bad_debt_amount=Decimal("110000"),
            tax_rate=Decimal("0.05"),
        )


def test_negative_amount_raises():
    with pytest.raises(ValueError):
        BadDebtConsumptionTaxService.compute(
            bad_debt_amount=Decimal("-1"),
        )
