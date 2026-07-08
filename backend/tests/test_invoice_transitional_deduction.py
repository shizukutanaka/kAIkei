from datetime import date
from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.invoice_transitional_deduction import InvoiceTransitionalDeductionService


class TestInvoiceTransitionalDeductionService:
    def test_80_percent_window(self):
        result = InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2024, 6, 1))
        assert result.deduction_rate == Decimal("0.80")
        assert result.deductible_tax == Decimal("8000")
        assert result.non_deductible_tax == Decimal("2000")

    def test_50_percent_window(self):
        result = InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2027, 6, 1))
        assert result.deduction_rate == Decimal("0.50")
        assert result.deductible_tax == Decimal("5000")
        assert result.non_deductible_tax == Decimal("5000")

    def test_boundaries(self):
        assert InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2023, 9, 30)).deduction_rate == Decimal(
            "1.00"
        )
        assert InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2023, 10, 1)).deduction_rate == Decimal(
            "0.80"
        )
        assert InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2026, 9, 30)).deduction_rate == Decimal(
            "0.80"
        )
        assert InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2026, 10, 1)).deduction_rate == Decimal(
            "0.50"
        )
        assert InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2029, 9, 30)).deduction_rate == Decimal(
            "0.50"
        )
        assert InvoiceTransitionalDeductionService.compute(Decimal("10000"), date(2029, 10, 1)).deduction_rate == Decimal(
            "0.00"
        )

    def test_flooring_case(self):
        purchase_tax = Decimal("1234.56")
        result = InvoiceTransitionalDeductionService.compute(purchase_tax, date(2024, 6, 1))
        expected = (purchase_tax * Decimal("0.80")).quantize(Decimal("1"), rounding=ROUND_DOWN)
        assert result.deductible_tax == expected
        assert result.non_deductible_tax == purchase_tax - expected

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            InvoiceTransitionalDeductionService.compute(Decimal("-1"), date(2024, 6, 1))
