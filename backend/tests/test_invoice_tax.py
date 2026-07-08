from decimal import Decimal

import pytest

from app.services.invoice_tax import InvoiceTaxService


class TestInvoiceTaxService:
    def test_single_rounding_invariant(self):
        result = InvoiceTaxService.compute_invoice_tax(
            [
                (Decimal("105"), Decimal("0.10")),
                (Decimal("105"), Decimal("0.10")),
                (Decimal("105"), Decimal("0.10")),
            ]
        )

        assert result.by_rate[0].tax_rate == Decimal("0.10")
        assert result.by_rate[0].taxable_base == Decimal("315")
        assert result.by_rate[0].tax == Decimal("31")
        assert result.total_tax == Decimal("31")
        assert result.total_amount == Decimal("346")

    def test_mixed_rates_and_totals(self):
        result = InvoiceTaxService.compute_invoice_tax(
            [
                (Decimal("1000"), Decimal("0.10")),
                (Decimal("500"), Decimal("0.10")),
                (Decimal("2000"), Decimal("0.08")),
                (Decimal("500"), Decimal("0.08")),
                (Decimal("300"), Decimal("0.00")),
            ]
        )

        assert [entry.tax_rate for entry in result.by_rate] == [Decimal("0.00"), Decimal("0.08"), Decimal("0.10")]
        assert result.by_rate[0].taxable_base == Decimal("300")
        assert result.by_rate[0].tax == Decimal("0")
        assert result.by_rate[1].taxable_base == Decimal("2500")
        assert result.by_rate[1].tax == Decimal("200")
        assert result.by_rate[2].taxable_base == Decimal("1500")
        assert result.by_rate[2].tax == Decimal("150")
        assert result.total_taxable == Decimal("4300")
        assert result.total_tax == Decimal("350")
        assert result.total_amount == Decimal("4650")
        assert result.total_taxable + result.total_tax == result.total_amount
        assert result.total_tax == sum(entry.tax for entry in result.by_rate)

    def test_sorting_and_total_amount_relation(self):
        result = InvoiceTaxService.compute_invoice_tax(
            [
                (Decimal("1"), Decimal("0.08")),
                (Decimal("2"), Decimal("0.10")),
                (Decimal("3"), Decimal("0.00")),
            ]
        )

        assert [entry.tax_rate for entry in result.by_rate] == [Decimal("0.00"), Decimal("0.08"), Decimal("0.10")]
        assert result.total_amount == result.total_taxable + result.total_tax

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            InvoiceTaxService.compute_invoice_tax([])

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError):
            InvoiceTaxService.compute_invoice_tax([(Decimal("-1"), Decimal("0.10"))])

    def test_unsupported_rate_raises(self):
        with pytest.raises(ValueError):
            InvoiceTaxService.compute_invoice_tax([(Decimal("100"), Decimal("0.05"))])
