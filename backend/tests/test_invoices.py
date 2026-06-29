import pytest
from decimal import Decimal, ROUND_HALF_UP


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return _round2(quantity * unit_price)


def _calc_invoice_totals(lines: list[tuple[Decimal, Decimal]], tax_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Replicate invoice subtotal/tax/total calculation."""
    subtotal = sum(_calc_line_total(q, p) for q, p in lines)
    tax_amount = _round2(subtotal * tax_rate / Decimal("100"))
    total = subtotal + tax_amount
    return subtotal, tax_amount, total


def _calc_tax_return_general(taxable_sales: Decimal, purchases_subject_to_tax: Decimal, tax_adjustment: Decimal = Decimal("0")) -> tuple[Decimal, Decimal, Decimal]:
    """General filing: output_tax = taxable_sales * 10%, input_tax = purchases * 10%."""
    output_tax = _round2(taxable_sales * Decimal("10") / Decimal("100"))
    input_tax = _round2(purchases_subject_to_tax * Decimal("10") / Decimal("100"))
    tax_payable = output_tax - input_tax + tax_adjustment
    return output_tax, input_tax, tax_payable


def _calc_tax_return_simplified(taxable_sales: Decimal, deemed_rate: Decimal = Decimal("0.90"), tax_adjustment: Decimal = Decimal("0")) -> tuple[Decimal, Decimal, Decimal]:
    """Simplified filing: deemed purchases = taxable_sales * rate."""
    deemed_purchases = _round2(taxable_sales * deemed_rate)
    output_tax = _round2(taxable_sales * Decimal("10") / Decimal("100"))
    input_tax = _round2(deemed_purchases * Decimal("10") / Decimal("100"))
    tax_payable = output_tax - input_tax + tax_adjustment
    return output_tax, input_tax, tax_payable


class TestInvoiceLineTotal:
    def test_basic(self):
        assert _calc_line_total(Decimal("2"), Decimal("1500")) == Decimal("3000")

    def test_fractional_quantity(self):
        assert _calc_line_total(Decimal("1.5"), Decimal("1000")) == Decimal("1500")

    def test_zero_quantity(self):
        assert _calc_line_total(Decimal("0"), Decimal("1000")) == Decimal("0")

    def test_rounding(self):
        result = _calc_line_total(Decimal("3.333"), Decimal("100"))
        assert result == Decimal("333")


class TestInvoiceTotals:
    def test_single_line(self):
        subtotal, tax, total = _calc_invoice_totals([(Decimal("1"), Decimal("10000"))], Decimal("10"))
        assert subtotal == Decimal("10000")
        assert tax == Decimal("1000")
        assert total == Decimal("11000")

    def test_multiple_lines(self):
        lines = [(Decimal("2"), Decimal("5000")), (Decimal("1"), Decimal("3000")), (Decimal("5"), Decimal("800"))]
        subtotal, tax, total = _calc_invoice_totals(lines, Decimal("10"))
        assert subtotal == Decimal("17000")
        assert tax == Decimal("1700")
        assert total == Decimal("18700")

    def test_zero_tax_rate(self):
        subtotal, tax, total = _calc_invoice_totals([(Decimal("1"), Decimal("10000"))], Decimal("0"))
        assert subtotal == Decimal("10000")
        assert tax == Decimal("0")
        assert total == Decimal("10000")

    def test_reduced_tax_rate(self):
        subtotal, tax, total = _calc_invoice_totals([(Decimal("1"), Decimal("1000"))], Decimal("8"))
        assert subtotal == Decimal("1000")
        assert tax == Decimal("80")
        assert total == Decimal("1080")

    def test_empty_lines(self):
        subtotal, tax, total = _calc_invoice_totals([], Decimal("10"))
        assert subtotal == Decimal("0")
        assert tax == Decimal("0")
        assert total == Decimal("0")


class TestInvoiceStatusTransitions:
    VALID_TRANSITIONS = {
        "draft": {"issued"},
        "issued": {"paid", "cancelled"},
        "paid": set(),
        "cancelled": set(),
    }

    def test_draft_to_issued(self):
        assert "issued" in self.VALID_TRANSITIONS["draft"]

    def test_issued_to_paid(self):
        assert "paid" in self.VALID_TRANSITIONS["issued"]

    def test_issued_to_cancelled(self):
        assert "cancelled" in self.VALID_TRANSITIONS["issued"]

    def test_draft_to_paid_not_allowed(self):
        assert "paid" not in self.VALID_TRANSITIONS["draft"]

    def test_draft_to_cancelled_not_allowed(self):
        assert "cancelled" not in self.VALID_TRANSITIONS["draft"]

    def test_paid_no_transitions(self):
        assert len(self.VALID_TRANSITIONS["paid"]) == 0

    def test_cancelled_no_transitions(self):
        assert len(self.VALID_TRANSITIONS["cancelled"]) == 0


class TestTaxReturnGeneralFiling:
    def test_basic(self):
        output, input_, payable = _calc_tax_return_general(Decimal("10000000"), Decimal("6000000"))
        assert output == Decimal("1000000")
        assert input_ == Decimal("600000")
        assert payable == Decimal("400000")

    def test_with_adjustment(self):
        output, input_, payable = _calc_tax_return_general(Decimal("5000000"), Decimal("3000000"), Decimal("50000"))
        assert output == Decimal("500000")
        assert input_ == Decimal("300000")
        assert payable == Decimal("250000")

    def test_zero_sales(self):
        output, input_, payable = _calc_tax_return_general(Decimal("0"), Decimal("1000000"))
        assert output == Decimal("0")
        assert input_ == Decimal("100000")
        assert payable == Decimal("-100000")

    def test_rounding(self):
        output, input_, payable = _calc_tax_return_general(Decimal("333333"), Decimal("111111"))
        assert output == Decimal("33333")
        assert input_ == Decimal("11111")
        assert payable == Decimal("22222")


class TestTaxReturnSimplifiedFiling:
    def test_default_rate_90(self):
        output, input_, payable = _calc_tax_return_simplified(Decimal("10000000"))
        assert output == Decimal("1000000")
        assert input_ == Decimal("900000")
        assert payable == Decimal("100000")

    def test_retail_rate_50(self):
        output, input_, payable = _calc_tax_return_simplified(Decimal("10000000"), Decimal("0.50"))
        assert output == Decimal("1000000")
        assert input_ == Decimal("500000")
        assert payable == Decimal("500000")

    def test_with_adjustment(self):
        output, input_, payable = _calc_tax_return_simplified(Decimal("8000000"), Decimal("0.90"), Decimal("-20000"))
        assert output == Decimal("800000")
        assert input_ == Decimal("720000")
        assert payable == Decimal("60000")

    def test_zero_sales(self):
        output, input_, payable = _calc_tax_return_simplified(Decimal("0"))
        assert output == Decimal("0")
        assert input_ == Decimal("0")
        assert payable == Decimal("0")


class TestTaxReturnStatusTransitions:
    VALID_TRANSITIONS = {
        "calculated": {"filed"},
        "filed": set(),
    }

    def test_calculated_to_filed(self):
        assert "filed" in self.VALID_TRANSITIONS["calculated"]

    def test_filed_no_transitions(self):
        assert len(self.VALID_TRANSITIONS["filed"]) == 0

    def test_calculated_to_invalid(self):
        assert "approved" not in self.VALID_TRANSITIONS["calculated"]
        assert "cancelled" not in self.VALID_TRANSITIONS["calculated"]


class TestFilingTypeValidation:
    VALID_TYPES = {"general", "simplified"}

    def test_general_valid(self):
        assert "general" in self.VALID_TYPES

    def test_simplified_valid(self):
        assert "simplified" in self.VALID_TYPES

    def test_invalid_types(self):
        assert "special" not in self.VALID_TYPES
        assert "" not in self.VALID_TYPES
        assert "GENERAL" not in self.VALID_TYPES
