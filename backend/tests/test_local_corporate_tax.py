from decimal import Decimal

import pytest

from app.services.local_corporate_tax import LocalCorporateTaxService


def test_basic():
    result = LocalCorporateTaxService.compute(corporate_tax_amount=Decimal("1664000"))
    assert result.tax_base == Decimal("1664000")
    assert result.rate == Decimal("0.103")
    # 1,664,000 * 0.103 = 171,392 -> floor to 100 = 171,300
    assert result.tax_amount == Decimal("171300")


def test_tax_base_rounded_down_to_thousand():
    result = LocalCorporateTaxService.compute(corporate_tax_amount=Decimal("1664999"))
    assert result.tax_base == Decimal("1664000")


def test_zero():
    result = LocalCorporateTaxService.compute(corporate_tax_amount=Decimal("0"))
    assert result.tax_amount == Decimal("0")


def test_negative_raises():
    with pytest.raises(ValueError):
        LocalCorporateTaxService.compute(corporate_tax_amount=Decimal("-1"))
