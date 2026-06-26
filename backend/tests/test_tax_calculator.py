from decimal import Decimal

import pytest

from app.services.tax_calculator import TaxCalculator


class TestTaxCalculator:
    def test_inclusive_10(self):
        tax_excluded, tax_amount = TaxCalculator.calculate_inclusive_10(Decimal("11000"))
        assert tax_excluded == Decimal("10000")
        assert tax_amount == Decimal("1000")

    def test_exclusive_10(self):
        tax_excluded, tax_amount = TaxCalculator.calculate_exclusive_10(Decimal("10000"))
        assert tax_excluded == Decimal("10000")
        assert tax_amount == Decimal("1000")

    def test_inclusive_8(self):
        tax_excluded, tax_amount = TaxCalculator.calculate_inclusive_8(Decimal("1080"))
        assert tax_excluded == Decimal("1000")
        assert tax_amount == Decimal("80")

    def test_exclusive_8(self):
        tax_excluded, tax_amount = TaxCalculator.calculate_exclusive_8(Decimal("1000"))
        assert tax_excluded == Decimal("1000")
        assert tax_amount == Decimal("80")

    def test_rounding_truncation(self):
        """333 yen with 10% inclusive should truncate to 30 yen tax."""
        tax_excluded, tax_amount = TaxCalculator.calculate_inclusive_10(Decimal("333"))
        assert tax_amount == Decimal("30")

    def test_zero_amount(self):
        tax_excluded, tax_amount = TaxCalculator.calculate_exclusive_10(Decimal("0"))
        assert tax_excluded == Decimal("0")
        assert tax_amount == Decimal("0")

    def test_non_taxable(self):
        """Non-taxable: tax amount should be 0."""
        tax_excluded, tax_amount = TaxCalculator.calculate_tax(
            Decimal("10000"), Decimal("0"), is_inclusive=False
        )
        assert tax_excluded == Decimal("10000")
        assert tax_amount == Decimal("0")
