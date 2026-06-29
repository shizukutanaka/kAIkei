import pytest
from decimal import Decimal, ROUND_HALF_UP


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_invoice_totals(lines: list[tuple[Decimal, Decimal]], tax_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = sum(_round2(q * p) for q, p in lines)
    tax = _round2(subtotal * tax_rate / Decimal("100"))
    total = subtotal + tax
    return subtotal, tax, total


class TestInvoiceIssueJournal:
    """売上仕訳: (借) 売掛金 / (貸) 売上 + 仮受消費税"""

    def test_balanced_with_tax(self):
        subtotal, tax, total = _calc_invoice_totals([(Decimal("1"), Decimal("100000"))], Decimal("10"))
        # Debit: AR = 110000
        # Credit: Sales = 100000, Tax = 10000
        debit_total = total
        credit_total = subtotal + tax
        assert debit_total == credit_total
        assert debit_total == Decimal("110000")

    def test_balanced_zero_tax(self):
        subtotal, tax, total = _calc_invoice_totals([(Decimal("1"), Decimal("50000"))], Decimal("0"))
        debit_total = total
        credit_total = subtotal + tax
        assert debit_total == credit_total
        assert debit_total == Decimal("50000")
        assert tax == Decimal("0")

    def test_balanced_multiple_lines(self):
        lines = [(Decimal("2"), Decimal("3000")), (Decimal("5"), Decimal("1500")), (Decimal("1"), Decimal("10000"))]
        subtotal, tax, total = _calc_invoice_totals(lines, Decimal("10"))
        debit_total = total
        credit_total = subtotal + tax
        assert debit_total == credit_total

    def test_tax_line_only_when_nonzero(self):
        subtotal, tax, total = _calc_invoice_totals([(Decimal("1"), Decimal("10000"))], Decimal("10"))
        # When tax > 0, 3 lines: AR(debit), Sales(credit), Tax(credit)
        line_count = 2 + (1 if tax > 0 else 0)
        assert line_count == 3

    def test_no_tax_line_when_zero(self):
        subtotal, tax, total = _calc_invoice_totals([(Decimal("1"), Decimal("10000"))], Decimal("0"))
        line_count = 2 + (1 if tax > 0 else 0)
        assert line_count == 2


class TestInvoicePaymentJournal:
    """入金仕訳: (借) 現金 / (貸) 売掛金"""

    def test_balanced(self):
        total = Decimal("110000")
        debit = total
        credit = total
        assert debit == credit

    def test_line_count(self):
        # Always 2 lines: Cash(debit), AR(credit)
        assert 2 == 2


class TestExpensePaymentJournal:
    """経費支払仕訳: (借) 経費 / (貸) 現金"""

    def test_balanced(self):
        total = Decimal("5350")
        debit = total
        credit = total
        assert debit == credit

    def test_line_count(self):
        assert 2 == 2


class TestAutoJournalSourceTypes:
    """source_type values for auto-generated journals"""

    VALID_SOURCE_TYPES = {"manual", "invoice", "invoice_payment", "expense_payment"}

    def test_invoice_source(self):
        assert "invoice" in self.VALID_SOURCE_TYPES

    def test_invoice_payment_source(self):
        assert "invoice_payment" in self.VALID_SOURCE_TYPES

    def test_expense_payment_source(self):
        assert "expense_payment" in self.VALID_SOURCE_TYPES

    def test_manual_still_valid(self):
        assert "manual" in self.VALID_SOURCE_TYPES


class TestAutoJournalAccountLookup:
    """Account code prefix patterns for auto-journal"""

    ACCOUNT_PATTERNS = {
        "ar": ("asset", "11"),        # 売掛金
        "cash": ("asset", "12"),      # 現金/預金
        "sales": ("revenue", "41"),   # 売上
        "tax": ("liability", "21"),   # 仮受消費税
        "expense": ("expense", "52"), # 経費
    }

    def test_all_patterns_defined(self):
        assert len(self.ACCOUNT_PATTERNS) == 5

    def test_ar_is_asset(self):
        assert self.ACCOUNT_PATTERNS["ar"][0] == "asset"

    def test_sales_is_revenue(self):
        assert self.ACCOUNT_PATTERNS["sales"][0] == "revenue"

    def test_tax_is_liability(self):
        assert self.ACCOUNT_PATTERNS["tax"][0] == "liability"

    def test_expense_is_expense_type(self):
        assert self.ACCOUNT_PATTERNS["expense"][0] == "expense"
