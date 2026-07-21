from decimal import Decimal

import pytest

from app.services.business_tax import BusinessTaxService


def test_three_brackets():
    result = BusinessTaxService.compute(taxable_income=Decimal("10000000"))
    assert result.low_base == Decimal("4000000")
    assert result.middle_base == Decimal("4000000")
    assert result.high_base == Decimal("2000000")
    # 140,000 + 212,000 + 140,000
    assert result.tax_amount == Decimal("492000")


def test_within_low_bracket():
    result = BusinessTaxService.compute(taxable_income=Decimal("3000000"))
    assert result.low_base == Decimal("3000000")
    assert result.middle_base == Decimal("0")
    assert result.high_base == Decimal("0")
    assert result.tax_amount == Decimal("105000")


def test_middle_bracket():
    result = BusinessTaxService.compute(taxable_income=Decimal("6000000"))
    assert result.middle_base == Decimal("2000000")
    # 140,000 + 106,000
    assert result.tax_amount == Decimal("246000")


def test_short_fiscal_year_prorates_brackets():
    result = BusinessTaxService.compute(taxable_income=Decimal("5000000"), months=6)
    assert result.low_base == Decimal("2000000")
    assert result.middle_base == Decimal("2000000")
    assert result.high_base == Decimal("1000000")
    # 70,000 + 106,000 + 70,000
    assert result.tax_amount == Decimal("246000")


def test_income_rounded_down_to_thousand():
    result = BusinessTaxService.compute(taxable_income=Decimal("1003999"))
    assert result.rounded_income == Decimal("1003000")


def test_tax_truncated_to_hundred():
    result = BusinessTaxService.compute(taxable_income=Decimal("1003000"))
    # 1,003,000 * 3.5% = 35,105 -> floor to 100 = 35,100
    assert result.tax_amount == Decimal("35100")


def test_negative_income_raises():
    with pytest.raises(ValueError):
        BusinessTaxService.compute(taxable_income=Decimal("-1"))


def test_invalid_months_raises():
    with pytest.raises(ValueError):
        BusinessTaxService.compute(taxable_income=Decimal("1000000"), months=0)
