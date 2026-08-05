from decimal import Decimal

import pytest

from app.services.corporate_tax import CorporateTaxService


def test_small_business_over_bracket():
    result = CorporateTaxService.compute(taxable_income=Decimal("10000000"))
    assert result.reduced_bracket == Decimal("8000000")
    assert result.reduced_tax == Decimal("1200000")  # 8,000,000 * 15%
    assert result.standard_tax == Decimal("464000")  # 2,000,000 * 23.2%
    assert result.total_tax == Decimal("1664000")


def test_small_business_within_bracket():
    result = CorporateTaxService.compute(taxable_income=Decimal("5000000"))
    assert result.reduced_tax == Decimal("750000")
    assert result.standard_tax == Decimal("0")
    assert result.total_tax == Decimal("750000")


def test_excluded_business_uses_19_percent():
    result = CorporateTaxService.compute(
        taxable_income=Decimal("10000000"),
        excluded_business=True,
    )
    assert result.reduced_rate == Decimal("0.19")
    assert result.total_tax == Decimal("1984000")  # 1,520,000 + 464,000


def test_large_business_all_standard():
    result = CorporateTaxService.compute(
        taxable_income=Decimal("10000000"),
        small_business=False,
    )
    assert result.reduced_bracket == Decimal("0")
    assert result.total_tax == Decimal("2320000")


def test_short_fiscal_year_prorates_bracket():
    result = CorporateTaxService.compute(
        taxable_income=Decimal("10000000"),
        months=6,
    )
    assert result.reduced_bracket == Decimal("4000000")
    # 4,000,000*15% + 6,000,000*23.2% = 600,000 + 1,392,000
    assert result.total_tax == Decimal("1992000")


def test_income_rounded_down_to_thousand():
    result = CorporateTaxService.compute(taxable_income=Decimal("5000999"))
    assert result.rounded_income == Decimal("5000000")


def test_total_tax_truncated_to_hundred():
    result = CorporateTaxService.compute(taxable_income=Decimal("1111000"))
    # 1,111,000 * 15% = 166,650 -> floor to 100 = 166,600
    assert result.total_tax == Decimal("166600")


def test_negative_income_raises():
    with pytest.raises(ValueError):
        CorporateTaxService.compute(taxable_income=Decimal("-1"))


def test_invalid_months_raises():
    with pytest.raises(ValueError):
        CorporateTaxService.compute(taxable_income=Decimal("1000000"), months=0)
    with pytest.raises(ValueError):
        CorporateTaxService.compute(taxable_income=Decimal("1000000"), months=13)
