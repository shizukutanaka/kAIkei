from decimal import Decimal

import pytest

from app.services.residence_tax import ResidenceTaxSpecialCollectionService


def test_residence_tax_first_month_absorbs_remainder():
    result = ResidenceTaxSpecialCollectionService.compute(Decimal("250000"))
    assert result.ordinary_month_amount == Decimal("20800")
    assert result.first_month_amount == Decimal("21200")
    assert result.total == Decimal("250000")
    assert len(result.monthly_amounts) == 12
    assert result.monthly_amounts[0].month == 6
    assert result.monthly_amounts[0].amount == Decimal("21200")
    assert result.monthly_amounts[1].month == 7
    assert result.monthly_amounts[1].amount == Decimal("20800")
    assert result.monthly_amounts[-1].month == 5
    assert sum((m.amount for m in result.monthly_amounts), Decimal("0")) == Decimal("250000")


def test_residence_tax_evenly_divisible():
    result = ResidenceTaxSpecialCollectionService.compute(Decimal("120000"))
    assert result.ordinary_month_amount == Decimal("10000")
    assert result.first_month_amount == Decimal("10000")
    assert result.total == Decimal("120000")


def test_residence_tax_zero():
    result = ResidenceTaxSpecialCollectionService.compute(Decimal("0"))
    assert result.first_month_amount == Decimal("0")
    assert all(m.amount == Decimal("0") for m in result.monthly_amounts)


def test_residence_tax_negative_raises():
    with pytest.raises(ValueError):
        ResidenceTaxSpecialCollectionService.compute(Decimal("-1"))
