from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.local_consumption_tax import LocalConsumptionTaxService


class TestLocalConsumptionTaxService:
    def test_clean_example(self):
        result = LocalConsumptionTaxService.compute(Decimal("780000"))
        assert result.local_tax == Decimal("220000")
        assert result.total_tax == Decimal("1000000")

    def test_flooring_case(self):
        national_tax = Decimal("1")
        result = LocalConsumptionTaxService.compute(national_tax)
        expected = (national_tax * Decimal("22") / Decimal("78")).quantize(Decimal("1"), rounding=ROUND_DOWN)
        assert result.local_tax == expected
        assert result.total_tax == national_tax + expected

    def test_zero(self):
        result = LocalConsumptionTaxService.compute(Decimal("0"))
        assert result.local_tax == Decimal("0")
        assert result.total_tax == Decimal("0")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            LocalConsumptionTaxService.compute(Decimal("-1"))
