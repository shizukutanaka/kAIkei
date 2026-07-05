from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.special_20_percent_consumption_tax import SpecialTwentyPercentConsumptionTaxService


class TestSpecialTwentyPercentConsumptionTaxService:
    def test_clean_example(self):
        result = SpecialTwentyPercentConsumptionTaxService.compute(Decimal("1000000"))
        assert result.payable_tax == Decimal("200000")
        assert result.special_deduction == Decimal("800000")

    def test_flooring_case(self):
        sales_consumption_tax = Decimal("1234567")
        result = SpecialTwentyPercentConsumptionTaxService.compute(sales_consumption_tax)
        expected = (sales_consumption_tax * Decimal("0.20")).quantize(Decimal("1"), rounding=ROUND_DOWN)
        assert result.payable_tax == expected
        assert result.special_deduction == sales_consumption_tax - expected

    def test_zero(self):
        result = SpecialTwentyPercentConsumptionTaxService.compute(Decimal("0"))
        assert result.payable_tax == Decimal("0")
        assert result.special_deduction == Decimal("0")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            SpecialTwentyPercentConsumptionTaxService.compute(Decimal("-1"))
