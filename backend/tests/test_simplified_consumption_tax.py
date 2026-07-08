from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.simplified_consumption_tax import (
    SIMPLIFIED_CONSUMPTION_TAX_RATES,
    SimplifiedConsumptionTaxService,
)


class TestSimplifiedConsumptionTaxService:
    def test_all_categories_map_to_correct_rates(self):
        expected = {
            1: Decimal("0.90"),
            2: Decimal("0.80"),
            3: Decimal("0.70"),
            4: Decimal("0.60"),
            5: Decimal("0.50"),
            6: Decimal("0.40"),
        }
        assert expected == SIMPLIFIED_CONSUMPTION_TAX_RATES

        for category, rate in expected.items():
            result = SimplifiedConsumptionTaxService.compute(Decimal("1000000"), category)
            assert result.business_category == category
            assert result.deemed_purchase_rate == rate

    def test_category_one_and_five_examples(self):
        result_one = SimplifiedConsumptionTaxService.compute(Decimal("1000000"), 1)
        assert result_one.deductible_tax == Decimal("900000")
        assert result_one.net_tax == Decimal("100000")

        result_five = SimplifiedConsumptionTaxService.compute(Decimal("1000000"), 5)
        assert result_five.deductible_tax == Decimal("500000")
        assert result_five.net_tax == Decimal("500000")

    def test_rounds_down_fractional_yen(self):
        sales_tax = Decimal("12345.67")
        rate = SIMPLIFIED_CONSUMPTION_TAX_RATES[4]
        expected_deductible = (sales_tax * rate).quantize(Decimal("1"), rounding=ROUND_DOWN)

        result = SimplifiedConsumptionTaxService.compute(sales_tax, 4)

        assert result.deductible_tax == expected_deductible
        assert result.net_tax == sales_tax - expected_deductible
        assert expected_deductible == Decimal("7407")

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError):
            SimplifiedConsumptionTaxService.compute(Decimal("1000"), 0)
        with pytest.raises(ValueError):
            SimplifiedConsumptionTaxService.compute(Decimal("1000"), 7)

    def test_negative_sales_tax_raises(self):
        with pytest.raises(ValueError):
            SimplifiedConsumptionTaxService.compute(Decimal("-1"), 1)
