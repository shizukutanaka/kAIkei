from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.withholding_tax import (
    WITHHOLDING_TAX_RATE_UP_TO_THRESHOLD,
    WithholdingTaxService,
)


class TestWithholdingTaxService:
    def test_amount_100000(self):
        assert WithholdingTaxService.compute_professional_fee(Decimal("100000")) == Decimal("10210")

    def test_amount_exactly_one_million(self):
        assert WithholdingTaxService.compute_professional_fee(Decimal("1000000")) == Decimal("102100")

    def test_amount_1200000(self):
        assert WithholdingTaxService.compute_professional_fee(Decimal("1200000")) == Decimal("142940")

    def test_rounds_down_fractional_yen(self):
        amount = Decimal("12345.67")
        raw_tax = amount * WITHHOLDING_TAX_RATE_UP_TO_THRESHOLD
        expected = raw_tax.quantize(Decimal("1"), rounding=ROUND_DOWN)

        assert WithholdingTaxService.compute_professional_fee(amount) == expected
        assert expected == Decimal("1260")

    def test_amount_zero(self):
        assert WithholdingTaxService.compute_professional_fee(Decimal("0")) == Decimal("0")

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError):
            WithholdingTaxService.compute_professional_fee(Decimal("-1"))
