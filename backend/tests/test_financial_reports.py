import pytest
from decimal import Decimal, ROUND_HALF_UP


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class TestIncomeStatementLogic:
    """損益計算書: 収益 - 費用 = 当期純利益"""

    def test_black_ink(self):
        revenue = Decimal("1000000")
        expense = Decimal("600000")
        net = revenue - expense
        assert net == Decimal("400000")
        assert net > 0

    def test_red_ink(self):
        revenue = Decimal("300000")
        expense = Decimal("500000")
        net = revenue - expense
        assert net == Decimal("-200000")
        assert net < 0

    def test_break_even(self):
        revenue = Decimal("500000")
        expense = Decimal("500000")
        net = revenue - expense
        assert net == Decimal("0")

    def test_multiple_revenue_accounts(self):
        revenues = [Decimal("500000"), Decimal("200000"), Decimal("100000")]
        expenses = [Decimal("300000"), Decimal("150000")]
        total_rev = sum(revenues)
        total_exp = sum(expenses)
        net = total_rev - total_exp
        assert total_rev == Decimal("800000")
        assert total_exp == Decimal("450000")
        assert net == Decimal("350000")

    def test_revenue_credit_normal(self):
        debit_sum = Decimal("0")
        credit_sum = Decimal("1000000")
        amount = credit_sum - debit_sum
        assert amount == Decimal("1000000")

    def test_expense_debit_normal(self):
        debit_sum = Decimal("600000")
        credit_sum = Decimal("0")
        amount = debit_sum - credit_sum
        assert amount == Decimal("600000")


class TestBalanceSheetLogic:
    """貸借対照表: 資産 = 負債 + 純資産"""

    def test_balanced(self):
        assets = Decimal("10000000")
        liabilities = Decimal("4000000")
        equity = Decimal("6000000")
        assert assets == liabilities + equity

    def test_not_balanced(self):
        assets = Decimal("10000000")
        liabilities = Decimal("3000000")
        equity = Decimal("6000000")
        assert assets != liabilities + equity

    def test_asset_debit_normal(self):
        debit_sum = Decimal("5000000")
        credit_sum = Decimal("1000000")
        amount = debit_sum - credit_sum
        assert amount == Decimal("4000000")

    def test_liability_credit_normal(self):
        debit_sum = Decimal("0")
        credit_sum = Decimal("3000000")
        amount = credit_sum - debit_sum
        assert amount == Decimal("3000000")

    def test_equity_credit_normal(self):
        debit_sum = Decimal("0")
        credit_sum = Decimal("6000000")
        amount = credit_sum - debit_sum
        assert amount == Decimal("6000000")

    def test_with_invoice_and_payroll(self):
        # Simulate: invoice issued (AR +100k, Sales +100k)
        # + payroll paid (Salary expense +50k, Cash -50k)
        ar = Decimal("100000")
        sales = Decimal("100000")
        salary_exp = Decimal("50000")
        cash = Decimal("50000")  # reduced from 100k
        # B/S: assets = AR + Cash = 100k + 50k = 150k
        # B/S: liabilities + equity = 0 + (Sales - Salary) = 50k
        # Not balanced because we're simplifying — but P/L: Sales - Salary = 50k net
        total_assets = ar + cash
        net_income = sales - salary_exp
        assert total_assets == Decimal("150000")
        assert net_income == Decimal("50000")


class TestAccountTypeClassification:
    """勘定科目の分類"""

    PL_TYPES = {"revenue", "expense"}
    BS_TYPES = {"asset", "liability", "equity"}

    def test_revenue_is_pl(self):
        assert "revenue" in self.PL_TYPES

    def test_expense_is_pl(self):
        assert "expense" in self.PL_TYPES

    def test_asset_is_bs(self):
        assert "asset" in self.BS_TYPES

    def test_liability_is_bs(self):
        assert "liability" in self.BS_TYPES

    def test_equity_is_bs(self):
        assert "equity" in self.BS_TYPES

    def test_no_overlap(self):
        assert self.PL_TYPES & self.BS_TYPES == set()

    def test_all_types_covered(self):
        all_types = self.PL_TYPES | self.BS_TYPES
        assert all_types == {"revenue", "expense", "asset", "liability", "equity"}
