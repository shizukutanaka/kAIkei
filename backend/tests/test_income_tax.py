from decimal import Decimal

import pytest

from app.services.income_tax import IncomeTaxService


class TestIncomeTaxService:
    def test_bracket_values(self):
        assert IncomeTaxService.compute(Decimal("1950000")) == Decimal("97500")
        assert IncomeTaxService.compute(Decimal("3000000")) == Decimal("202500")
        assert IncomeTaxService.compute(Decimal("7000000")) == Decimal("974000")
        assert IncomeTaxService.compute(Decimal("50000000")) == Decimal("17704000")

    def test_thousand_yen_floor(self):
        expected = IncomeTaxService.compute(Decimal("3000000"))
        assert IncomeTaxService.compute(Decimal("3000999")) == expected

    def test_zero(self):
        assert IncomeTaxService.compute(Decimal("0")) == Decimal("0")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            IncomeTaxService.compute(Decimal("-1"))
