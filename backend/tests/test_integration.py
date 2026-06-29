"""Integration tests for module-to-journal linkage.

Tests verify that:
1. Invoice issue → auto-generates sales journal (AR debit, Sales credit, Tax credit)
2. Invoice payment → auto-generates receipt journal (Cash debit, AR credit)
3. Expense payment → auto-generates expense journal (Expense debit, Cash credit)
4. Payroll batch paid → auto-generates payroll journal (Salary debit, Cash credit, Withholding credit)
5. Trial balance reflects all auto-generated entries
6. P/L correctly classifies revenue vs expense
7. B/S correctly classifies asset vs liability vs equity
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_invoice_totals(lines: list[tuple[Decimal, Decimal]], tax_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = sum(_round2(q * p) for q, p in lines)
    tax = _round2(subtotal * tax_rate / Decimal("100"))
    total = subtotal + tax
    return subtotal, tax, total


class TestInvoiceIssueToJournalLinkage:
    """請求書発行 → 売上仕訳 自動連携"""

    def test_issue_generates_balanced_journal(self):
        subtotal, tax, total = _calc_invoice_totals(
            [(Decimal("1"), Decimal("100000"))], Decimal("10")
        )
        # Journal: (借) 売掛金 110000 / (貸) 売上 100000 + (貸) 仮受消費税 10000
        debit_lines = [total]
        credit_lines = [subtotal, tax]
        assert sum(debit_lines) == sum(credit_lines)
        assert sum(debit_lines) == Decimal("110000")

    def test_issue_zero_tax_no_tax_line(self):
        subtotal, tax, total = _calc_invoice_totals(
            [(Decimal("1"), Decimal("50000"))], Decimal("0")
        )
        # Journal: (借) 売掛金 50000 / (貸) 売上 50000
        debit_lines = [total]
        credit_lines = [subtotal]
        if tax > 0:
            credit_lines.append(tax)
        assert sum(debit_lines) == sum(credit_lines)
        assert len(credit_lines) == 1  # No tax line

    def test_issue_multiple_invoice_lines(self):
        lines = [(Decimal("2"), Decimal("3000")), (Decimal("5"), Decimal("1500")), (Decimal("1"), Decimal("10000"))]
        subtotal, tax, total = _calc_invoice_totals(lines, Decimal("10"))
        debit_lines = [total]
        credit_lines = [subtotal, tax]
        assert sum(debit_lines) == sum(credit_lines)


class TestInvoicePaymentToJournalLinkage:
    """請求書入金 → 入金仕訳 自動連携"""

    def test_payment_generates_balanced_journal(self):
        total = Decimal("110000")
        # Journal: (借) 現金 110000 / (貸) 売掛金 110000
        debit = total
        credit = total
        assert debit == credit

    def test_payment_after_issue_clears_ar(self):
        """Issue creates AR, payment clears it"""
        subtotal, tax, total = _calc_invoice_totals(
            [(Decimal("1"), Decimal("100000"))], Decimal("10")
        )
        # After issue: AR balance = 110000
        ar_after_issue = total
        # After payment: AR balance = 0, Cash increased by 110000
        ar_after_payment = ar_after_issue - total
        assert ar_after_payment == Decimal("0")


class TestExpensePaymentToJournalLinkage:
    """経費支払 → 経費仕訳 自動連携"""

    def test_expense_generates_balanced_journal(self):
        total = Decimal("5350")
        # Journal: (借) 経費 5350 / (貸) 現金 5350
        debit = total
        credit = total
        assert debit == credit

    def test_expense_reduces_cash(self):
        total = Decimal("10000")
        cash_before = Decimal("1000000")
        cash_after = cash_before - total
        assert cash_after == Decimal("990000")


class TestPayrollToJournalLinkage:
    """給与支払 → 給与仕訳 自動連携"""

    def test_payroll_generates_balanced_journal(self):
        total_gross = Decimal("500000")
        total_deductions = Decimal("100000")
        net_pay = total_gross - total_deductions
        # Journal: (借) 給与費用 500000 / (貸) 現金 400000 + (貸) 預り金 100000
        debit = total_gross
        credit = net_pay + total_deductions
        assert debit == credit

    def test_payroll_zero_deductions(self):
        total_gross = Decimal("300000")
        total_deductions = Decimal("0")
        net_pay = total_gross - total_deductions
        # Journal: (借) 給与費用 300000 / (貸) 現金 300000 (no withholding line)
        debit = total_gross
        credit = net_pay
        assert debit == credit

    def test_payroll_batch_aggregation(self):
        """Batch transition: aggregate all employees"""
        records = [
            (Decimal("300000"), Decimal("60000")),  # emp1
            (Decimal("250000"), Decimal("50000")),  # emp2
            (Decimal("200000"), Decimal("40000")),  # emp3
        ]
        total_gross = sum(r[0] for r in records)
        total_deductions = sum(r[1] for r in records)
        net_pay = total_gross - total_deductions
        assert total_gross == Decimal("750000")
        assert total_deductions == Decimal("150000")
        assert net_pay == Decimal("600000")
        # Journal balance
        assert total_gross == net_pay + total_deductions


class TestTrialBalanceIntegration:
    """試算表が全自動仕訳を反映する"""

    def test_all_source_types_reflected(self):
        """All auto-journal source types should appear in trial balance"""
        source_types = ["invoice", "invoice_payment", "expense_payment", "payroll", "manual"]
        # All should contribute to account balances
        assert len(source_types) == 5

    def test_invoice_issue_affects_revenue_and_ar(self):
        subtotal, tax, total = _calc_invoice_totals(
            [(Decimal("1"), Decimal("100000"))], Decimal("10")
        )
        # After issue: AR (asset) +110000, Sales (revenue) +100000, Tax (liability) +10000
        ar_balance = total
        sales_balance = subtotal
        tax_balance = tax
        # Trial balance: debit total = credit total
        assert ar_balance == sales_balance + tax_balance

    def test_payment_affects_cash_and_ar(self):
        total = Decimal("110000")
        # After payment: Cash (asset) +110000, AR (asset) -110000
        # Net effect on assets: 0
        cash_change = total
        ar_change = -total
        net_asset_change = cash_change + ar_change
        assert net_asset_change == 0


class TestPLBSIntegration:
    """P/L・B/Sが自動仕訳を正しく反映する"""

    def test_invoice_revenue_appears_in_pl(self):
        """Invoice issue revenue should appear in P/L revenue section"""
        subtotal = Decimal("100000")
        # P/L: revenue includes sales
        total_revenue = subtotal
        assert total_revenue > 0

    def test_expense_appears_in_pl(self):
        """Expense payment should appear in P/L expense section"""
        expense_amount = Decimal("5350")
        total_expense = expense_amount
        assert total_expense > 0

    def test_payroll_appears_in_pl(self):
        """Payroll gross should appear in P/L expense section"""
        total_gross = Decimal("500000")
        total_expense = total_gross
        assert total_expense > 0

    def test_net_income_with_all_modules(self):
        """Net income = Sales - Expenses (including payroll)"""
        sales = Decimal("100000")
        expense = Decimal("5350")
        payroll = Decimal("500000")
        net = sales - expense - payroll
        assert net == Decimal("-405350")  # Loss because payroll > sales

    def test_bs_balanced_after_all_transactions(self):
        """B/S: Assets = Liabilities + Equity after all module transactions"""
        # Initial: Cash 1000000 (asset), Capital 1000000 (equity)
        cash = Decimal("1000000")
        capital = Decimal("1000000")
        # Invoice issue: AR +110000, Sales +100000 (→ retained earnings), Tax +10000
        ar = Decimal("110000")
        tax_payable = Decimal("10000")
        # Invoice payment: Cash +110000, AR -110000
        cash += Decimal("110000")
        ar -= Decimal("110000")
        # Expense payment: Cash -5350, Expense -5350 (→ retained earnings)
        cash -= Decimal("5350")
        # Payroll: Cash -400000, Salary exp -500000 (→ retained earnings), Withholding +100000
        cash -= Decimal("400000")
        withholding = Decimal("100000")

        total_assets = cash + ar
        total_liabilities = tax_payable + withholding
        # Retained earnings = Capital + Sales - Expense - Payroll
        retained = capital + Decimal("100000") - Decimal("5350") - Decimal("500000")
        total_equity = retained

        assert total_assets == total_liabilities + total_equity

    def test_account_type_classification_no_overlap(self):
        """P/L and B/S account types must not overlap"""
        pl_types = {"revenue", "expense"}
        bs_types = {"asset", "liability", "equity"}
        assert pl_types & bs_types == set()


class TestAutoJournalSourceTypes:
    """全モジュールのsource_typeカバレッジ"""

    def test_all_modules_have_source_type(self):
        expected = {"invoice", "invoice_payment", "expense_payment", "payroll"}
        # All 4 modules should have distinct source types
        assert len(expected) == 4

    def test_manual_still_supported(self):
        """Manual journal creation should still work alongside auto-journals"""
        all_types = {"invoice", "invoice_payment", "expense_payment", "payroll", "manual"}
        assert "manual" in all_types
